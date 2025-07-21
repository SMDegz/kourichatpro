"""
消息处理模块
负责处理聊天消息，包括:
- 消息队列管理
- 消息分发处理
- API响应处理
- 多媒体消息处理
"""
import logging
import threading
import time
import re
import tempfile
from datetime import datetime
from typing import Dict, List, Optional
from openai import OpenAI
from wxauto import WeChat
from src.services.database import Session, ChatMessage
import random
import os
from src.services.ai.llm_service import LLMService
from src.services.ai.network_search_service import NetworkSearchService
from src.config import config, WEBLENS_ENABLED, NETWORK_SEARCH_ENABLED
from modules.memory.memory_service import MemoryService
from modules.memory.content_generator import ContentGenerator
from modules.reminder.time_recognition import TimeRecognitionService
from modules.reminder import ReminderService
from .debug import DebugCommandHandler
from src.handlers.db import DBHandler

# 导入emoji库用于处理表情符号
import emoji

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')

class MessageHandler:
    def __init__(self, root_dir, api_key, base_url, model, max_token, temperature,
                 max_groups, robot_name, prompt_content, image_handler, emoji_handler, voice_handler, memory_service, content_generator=None):
        self.root_dir = root_dir
        self.api_key = api_key
        self.model = model
        self.max_token = max_token
        self.temperature = temperature
        self.max_groups = max_groups
        self.robot_name = robot_name
        self.prompt_content = prompt_content

        # 不再需要对话计数器，改为按时间总结

        # 使用 DeepSeekAI 替换直接的 OpenAI 客户端
        self.deepseek = LLMService(
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_token=max_token,
            temperature=temperature,
            max_groups=max_groups
        )

        # 消息队列相关
        self.message_queues = {}  # 存储每个用户的消息队列，格式：{queue_key: queue_data}
        self.queue_timers = {}    # 存储每个用户的定时器，格式：{queue_key: timer}
        # 从全局导入的config中获取队列等待时间（秒）
        from src.config import config
        self.QUEUE_TIMEOUT = config.behavior.message_queue.timeout
        self.queue_lock = threading.Lock()
        self.chat_contexts = {}

        # 微信实例
        self.wx = WeChat()

        # 添加 handlers
        self.image_handler = image_handler
        self.emoji_handler = emoji_handler
        self.voice_handler = voice_handler
        # 使用新的记忆服务
        self.memory_service = memory_service
        # 保存当前角色名
        avatar_path = os.path.join(self.root_dir, config.behavior.context.avatar_dir)
        self.current_avatar = os.path.basename(avatar_path)
        
        # 从人设文件中提取真实名字
        self.avatar_real_names = self._extract_avatar_names(avatar_path)
        logger.info(f"当前使用角色: {self.current_avatar}, 识别名字: {self.avatar_real_names}")

        # 使用传入的内容生成器实例，或创建新实例
        self.content_generator = content_generator

        # 如果没有提供内容生成器，尝试创建新实例
        if self.content_generator is None:
            try:
                from modules.memory.content_generator import ContentGenerator
                from src.config import config
                self.content_generator = ContentGenerator(
                    root_dir=root_dir,
                    api_key=config.llm.api_key,
                    base_url=config.llm.base_url,
                    model=config.llm.model,
                    max_token=config.llm.max_tokens,
                    temperature=config.llm.temperature
                )
                logger.info("已创建内容生成器实例")
            except Exception as e:
                logger.error(f"创建内容生成器实例失败: {str(e)}")
                self.content_generator = None

        # 初始化调试命令处理器
        self.debug_handler = DebugCommandHandler(
            root_dir=root_dir,
            memory_service=memory_service,
            llm_service=self.deepseek,
            content_generator=self.content_generator
        )

        # 需要保留原始格式的命令列表
        # 包含 None 以处理网页内容提取等非命令的特殊情况
        self.preserve_format_commands = [None, '/diary', '/state', '/letter', '/list', '/pyq', '/gift', '/shopping']
        logger.info("调试命令处理器已初始化")

        # 初始化时间识别服务（使用已有的 deepseek 实例）
        self.time_recognition = TimeRecognitionService(self.deepseek)
        logger.info("时间识别服务已初始化")

        # 初始化提醒服务（传入自身实例）
        self.reminder_service = ReminderService(self)
        logger.info("提醒服务已初始化")

        # 初始化网络搜索服务
        self.network_search_service = NetworkSearchService(self.deepseek)
        logger.info("网络搜索服务已初始化")

    def switch_avatar(self, avatar_path: str):
        """切换人设"""
        try:
            from src.config import config
            
            # 更新当前人设路径
            config.behavior.context.avatar_dir = avatar_path
            
            # 重新加载人设文件
            full_avatar_path = os.path.join(self.root_dir, avatar_path)
            prompt_path = os.path.join(full_avatar_path, "avatar.md")
            
            if os.path.exists(prompt_path):
                with open(prompt_path, "r", encoding="utf-8") as file:
                    self.prompt_content = file.read()
                
                # 更新当前人设名
                self.current_avatar = os.path.basename(full_avatar_path)
                
                # 重新提取人设名字
                self.avatar_real_names = self._extract_avatar_names(full_avatar_path)
                
                logger.info(f"成功切换人设到: {self.current_avatar}, 识别名字: {self.avatar_real_names}")
            else:
                logger.error(f"人设文件不存在: {prompt_path}")
                
        except Exception as e:
            logger.error(f"切换人设失败: {str(e)}")

    def _extract_avatar_names(self, avatar_path: str) -> list:
        """从人设文件中提取可能的名字"""
        names = []  # 不包含目录名，避免ATRI这样的英文名干扰
        
        try:
            avatar_file = os.path.join(avatar_path, "avatar.md")
            if os.path.exists(avatar_file):
                with open(avatar_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # 使用正则表达式提取可能的名字
                import re
                
                # 提取"你是xxx"模式的名字（最重要的模式）
                matches = re.findall(r'你是([^，,。！!？?\s]+)', content)
                for match in matches:
                    # 过滤掉明显不是名字的词
                    if match not in names and len(match) <= 6 and '机器' not in match:
                        names.append(match)
                
                # 提取"名字[：:]\s*xxx"模式的名字
                matches = re.findall(r'名字[：:]\s*([^，,。！!？?\s\n]+)', content)
                for match in matches:
                    if match not in names and len(match) <= 6:
                        names.append(match)
                        
                # 提取"扮演xxx"模式的名字
                matches = re.findall(r'扮演([^，,。！!？?\s]+)', content)
                for match in matches:
                    # 只要中文名字，过滤掉长词
                    if match not in names and len(match) <= 6 and any('\u4e00' <= c <= '\u9fff' for c in match):
                        names.append(match)
                        
        except Exception as e:
            logger.warning(f"提取人设名字失败: {str(e)}")
            
        # 如果没有提取到任何名字，使用目录名作为备选
        if not names:
            names = [self.current_avatar]
            
        return names

    def _get_queue_key(self, chat_id: str, sender_name: str, is_group: bool) -> str:
        """生成队列键值
        在群聊中使用 chat_id + sender_name 作为键，在私聊中仅使用 chat_id"""
        return f"{chat_id}_{sender_name}" if is_group else chat_id

    def save_message(self, sender_id: str, sender_name: str, message: str, reply: str, is_system_message: bool = False):
        """保存聊天记录到数据库和短期记忆"""
        try:
            # 清理回复中的@前缀，防止幻觉
            clean_reply = reply
            if reply.startswith(f"@{sender_name} "):
                clean_reply = reply[len(f"@{sender_name} "):]

            # 保存到数据库
            session = Session()
            chat_message = ChatMessage(
                sender_id=sender_id,
                sender_name=sender_name,
                message=message,
                reply=reply
            )
            session.add(chat_message)
            session.commit()
            session.close()



            avatar_name = self.current_avatar
            # 添加到记忆，传递系统消息标志和用户ID
            self.memory_service.add_conversation(avatar_name, message, clean_reply, sender_id, is_system_message)

        except Exception as e:
            logger.error(f"保存消息失败: {str(e)}")

    def get_api_response(self, message: str, user_id: str, is_group: bool = False) -> str:
        """获取 API 回复"""
        avatar_dir = os.path.join(self.root_dir, config.behavior.context.avatar_dir)
        prompt_path = os.path.join(avatar_dir, "avatar.md")
        # 使用类中已初始化的当前角色名
        avatar_name = self.current_avatar

        try:
            #读取原始提示内容
            with open(prompt_path, "r", encoding="utf-8") as f:
                avatar_content = f.read()
                logger.debug(f"角色提示文件大小: {len(avatar_content)} bytes")

            # 步骤2：获取核心记忆 - 使用用户ID获取对应的记忆
            core_memory = self.memory_service.get_core_memory(avatar_name, user_id=user_id)
            core_memory_prompt = f"# 核心记忆\n{core_memory}" if core_memory else ""
            logger.debug(f"核心记忆长度: {len(core_memory)}")

            # 获取历史上下文（仅在程序重启时）
            # 检查是否已经为该用户加载过上下文
            recent_context = None
            if user_id not in self.deepseek.chat_contexts:
                recent_context = self.memory_service.get_recent_context(avatar_name, user_id)
                if recent_context:
                    logger.info(f"程序启动：为用户 {user_id} 加载 {len(recent_context)} 条历史上下文消息")
                    logger.debug(f"用户 {user_id} 的历史上下文: {recent_context}")

            # 如果是群聊场景，添加群聊环境提示
            if is_group:
                group_prompt_path = os.path.join(self.root_dir, "data", "base", "group.md")
                with open(group_prompt_path, "r", encoding="utf-8") as f:
                    group_chat_prompt = f.read().strip()

                combined_system_prompt = f"{group_chat_prompt}\n\n{avatar_content}"
            else:
                combined_system_prompt = avatar_content

            # 获取系统提示词（如果有）
            if hasattr(self, 'system_prompts') and user_id in self.system_prompts and self.system_prompts[user_id]:
                # 将最近的系统提示词合并为一个字符串
                additional_prompt = "\n\n".join(self.system_prompts[user_id])
                logger.info(f"使用系统提示词: {additional_prompt[:100]}...")

                # 将系统提示词添加到角色提示词中
                combined_system_prompt = f"{combined_system_prompt}\n\n参考信息:\n{additional_prompt}"

                # 使用后清除系统提示词，避免重复使用
                self.system_prompts[user_id] = []


            response = self.deepseek.get_response(
                message=message,
                user_id=user_id,
                system_prompt=combined_system_prompt,
                previous_context=recent_context,
                core_memory=core_memory_prompt
            )
            return response

        except Exception as e:
            logger.error(f"获取API响应失败: {str(e)}")
            # 降级处理：使用原始提示，不添加记忆
            return self.deepseek.get_response(message, user_id, self.prompt_content)

    def handle_user_message(self, content: str, chat_id: str, sender_name: str,
                     username: str, is_group: bool = False, is_image_recognition: bool = False):
        """统一的消息处理入口"""
        try:
            logger.info(f"收到消息 - 来自: {sender_name}" + (" (群聊)" if is_group else ""))
            logger.debug(f"消息内容: {content}")

            # 处理调试命令
            if self.debug_handler.is_debug_command(content):
                logger.info(f"检测到调试命令: {content}")
                # 定义回调函数，用于异步处理生成的内容
                def command_callback(command, reply, chat_id):
                    try:
                        if is_group:
                            reply = f"@{sender_name} {reply}"

                        # 使用命令响应发送方法
                        self._send_command_response(command, reply, chat_id)
                        logger.info(f"异步处理命令完成: {command}")
                    except Exception as e:
                        logger.error(f"异步处理命令失败: {str(e)}")

                intercept, response = self.debug_handler.process_command(
                    command=content,
                    current_avatar=self.current_avatar,
                    user_id=chat_id,
                    chat_id=chat_id,
                    callback=command_callback
                )

                if intercept:
                    # 只有当有响应时才发送（异步生成内容的命令不会有初始响应）
                    if response:
                        if is_group:
                            response = f"@{sender_name} {response}"
                        # self.wx.SendMsg(msg=response, who=chat_id)
                        self._send_raw_message(response, chat_id)

                    # 不记录调试命令的对话
                    logger.info(f"已处理调试命令: {content}")
                    return None

            # 无论消息中是否包含链接，都将消息添加到队列
            # 如果有链接，在队列处理过程中提取内容并替换
            self._add_to_message_queue(content, chat_id, sender_name, username, is_group, is_image_recognition)

        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}", exc_info=True)
            return None

    def _add_to_message_queue(self, content: str, chat_id: str, sender_name: str,
                            username: str, is_group: bool, is_image_recognition: bool):
        """添加消息到队列并设置定时器"""
        # 检测消息中是否包含链接，但不立即处理
        has_link = False
        if WEBLENS_ENABLED:
            urls = self.network_search_service.detect_urls(content)
            if urls:
                has_link = True
                logger.info(f"[消息队列] 检测到链接: {urls[0]}，将在队列处理时提取内容")

        with self.queue_lock:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            queue_key = self._get_queue_key(chat_id, sender_name, is_group)

            # 初始化或更新队列
            if queue_key not in self.message_queues:
                logger.info(f"[消息队列] 创建新队列 - 用户: {sender_name}" + (" (群聊)" if is_group else ""))
                self.message_queues[queue_key] = {
                    'messages': [f"[{current_time}]\n{content}"],  # 第一条消息带时间戳
                    'chat_id': chat_id,  # 保存原始chat_id用于发送消息
                    'sender_name': sender_name,
                    'username': username,
                    'is_group': is_group,
                    'is_image_recognition': is_image_recognition,
                    'last_update': time.time(),
                    'has_link': has_link,  # 标记消息中是否包含链接
                    'urls': urls if has_link else []  # 如果有链接，保存URL列表
                }
                logger.debug(f"[消息队列] 首条消息: {content[:50]}...")
            else:
                # 添加新消息到现有队列，后续消息不带时间戳
                self.message_queues[queue_key]['messages'].append(content)
                self.message_queues[queue_key]['last_update'] = time.time()
                self.message_queues[queue_key]['has_link'] = (has_link | self.message_queues[queue_key]['has_link'])
                if has_link:
                    self.message_queues[queue_key]['urls'].append(urls[0])
                msg_count = len(self.message_queues[queue_key]['messages'])
                logger.info(f"[消息队列] 追加消息 - 用户: {sender_name}, 当前消息数: {msg_count}")
                logger.debug(f"[消息队列] 新增消息: {content[:50]}...")

            # 取消现有的定时器
            if queue_key in self.queue_timers and self.queue_timers[queue_key]:
                try:
                    self.queue_timers[queue_key].cancel()
                    logger.debug(f"[消息队列] 重置定时器 - 用户: {sender_name}")
                except Exception as e:
                    logger.error(f"[消息队列] 取消定时器失败: {str(e)}")
                self.queue_timers[queue_key] = None

            # 创建新的定时器
            timer = threading.Timer(
                self.QUEUE_TIMEOUT,
                self._process_message_queue,
                args=[queue_key]
            )
            timer.daemon = True
            timer.start()
            self.queue_timers[queue_key] = timer
            logger.info(f"[消息队列] 设置新定时器 - 用户: {sender_name}, {self.QUEUE_TIMEOUT}秒后处理")

    def _process_message_queue(self, queue_key: str):
        """处理消息队列"""
        avatar_name = self.current_avatar
        try:
            with self.queue_lock:
                if queue_key not in self.message_queues:
                    logger.debug("[消息队列] 队列不存在，跳过处理")
                    return

                # 检查是否到达处理时间
                current_time = time.time()
                queue_data = self.message_queues[queue_key]
                last_update = queue_data['last_update']
                sender_name = queue_data['sender_name']

                if current_time - last_update < self.QUEUE_TIMEOUT - 0.1:
                    logger.info(f"[消息队列] 等待更多消息 - 用户: {sender_name}, 剩余时间: {self.QUEUE_TIMEOUT - (current_time - last_update):.1f}秒")
                    return

                # 获取并清理队列数据
                queue_data = self.message_queues.pop(queue_key)
                if queue_key in self.queue_timers:
                    self.queue_timers.pop(queue_key)

                messages = queue_data['messages']
                chat_id = queue_data['chat_id']  # 使用保存的原始chat_id
                username = queue_data['username']
                sender_name = queue_data['sender_name']
                is_group = queue_data['is_group']
                is_image_recognition = queue_data['is_image_recognition']

                # 合并消息
                combined_message = "\n".join(messages)

                # 打印日志信息
                logger.info(f"[消息队列] 开始处理 - 用户: {sender_name}, 消息数: {len(messages)}")
                logger.info("----------------------------------------")
                logger.info("原始消息列表:")
                for idx, msg in enumerate(messages, 1):
                    logger.info(f"{idx}. {msg}")
                logger.info("\n合并后的消息:")
                logger.info(f"{combined_message}")
                logger.info("----------------------------------------")

                # 处理队列中的链接
                processed_message = combined_message
                if queue_data.get('has_link', False) and WEBLENS_ENABLED:
                    urls = queue_data.get('urls', [])
                    if urls:
                        logger.info(f"处理队列中的链接: {urls[0]}")
                        # 提取网页内容
                        web_results = self.network_search_service.extract_web_content(urls[0])
                        if web_results and web_results['original']:
                            # 将网页内容添加到消息中
                            processed_message = f"{combined_message}\n\n{web_results['original']}"
                            logger.info("已获取URL内容并添加至本次Prompt中")    
                            logger.info(processed_message)

                # 检查合并后的消息是否包含时间提醒和联网搜索需求
                # 如果已处理搜索需求，则不需要继续处理消息
                search_handled = self._check_time_reminder_and_search(processed_message, sender_name)
                if search_handled:
                    logger.info(f"搜索需求已处理，直接回复")
                    return self._handle_text_message(processed_message, chat_id, sender_name, username, is_group)

                # 在处理消息前，如果启用了联网搜索，先检查是否需要联网搜索
                search_results = None

                if NETWORK_SEARCH_ENABLED:
                    # 使用时间识别服务检测搜索意图
                    search_intent = self.time_recognition.recognize_time_and_search(
                        message=combined_message,
                        user_name=sender_name,
                        avatar_name=self.current_avatar,
                        network_search_enabled=True
                    )

                    # 如果检测到搜索需求，先执行搜索
                    if search_intent['search_required'] and search_intent['search_query']:
                        logger.info(f"在timeout期间检测到搜索需求 - 查询: {search_intent['search_query']}")

                        # 获取对话上下文
                        # conversation_context = self.memory_service.get_recent_context(self.current_avatar, user_id)

                        # 执行搜索
                        search_results = self.network_search_service.search_internet(
                            query=search_intent['search_query'],
                            #conversation_context=conversation_context
                        )

                        # 如果搜索成功，将结果添加到消息中
                        if search_results and search_results['original']:
                            logger.info("搜索成功，将结果添加到消息中")
                            processed_message = f"{combined_message}\n\n{search_results['original']}"
                            logger.info(processed_message)
                        else:
                            logger.warning("搜索失败或结果为空，继续正常处理请求")

                # 检查是否为特殊请求(注释掉了生图功能)
                if self.voice_handler.is_voice_request(processed_message):
                    return self._handle_voice_request(processed_message, chat_id, sender_name, username, is_group)
                elif self.image_handler.is_random_image_request(processed_message):
                    return self._handle_random_image_request(processed_message, chat_id, sender_name, username, is_group)
               # elif not is_image_recognition and self.image_handler.is_image_generation_request(combined_message):
                    #return self._handle_image_generation_request(combined_message, chat_id, sender_name, username, is_group)
                else:
                    return self._handle_text_message(processed_message, chat_id, sender_name, username, is_group)

        except Exception as e:
            logger.error(f"处理消息队列失败: {str(e)}")
            return None

    def _process_text_for_display(self, text: str) -> str:
        """处理文本以确保表情符号正确显示"""
        try:
            # 先将Unicode表情符号转换为别名再转回，确保标准化
            return emoji.emojize(emoji.demojize(text))
        except Exception:
            return text

    def _filter_user_tags(self, text: str) -> str:
        """过滤消息中的用户标签
        
        Args:
            text: 原始文本
            
        Returns:
            str: 过滤后的文本
        """
        import re
        # 过滤掉 <用户 xxx> 和 </用户> 标签
        text = re.sub(r'<用户\s+[^>]+>\s*', '', text)
        text = re.sub(r'\s*</用户>', '', text)
        return text.strip()

    def _send_message_with_dollar(self, reply, chat_id):
        """以$为分隔符分批发送回复"""
        # 过滤用户标签
        reply = self._filter_user_tags(reply)
        
        # 首先处理文本中的emoji表情符号
        reply = self._process_text_for_display(reply)

        if '$' in reply or '＄' in reply:
            parts = [p.strip() for p in reply.replace("＄", "$").split("$") if p.strip()]
            for part in parts:
                # 检查当前部分是否包含表情标签
                emotion_tags = self.emoji_handler.extract_emotion_tags(part)
                if emotion_tags:
                    logger.debug(f"消息片段包含表情: {emotion_tags}")

                # 清理表情标签并发送文本
                clean_part = part
                for tag in emotion_tags:
                    clean_part = clean_part.replace(f'[{tag}]', '')

                if clean_part.strip():
                    self.wx.SendMsg(msg=clean_part.strip(), who=chat_id)
                    logger.debug(f"发送消息: {clean_part[:20]}...")

                # 发送该部分包含的表情
                for emotion_type in emotion_tags:
                    try:
                        emoji_path = self.emoji_handler.get_emoji_for_emotion(emotion_type)
                        if emoji_path:
                            self.wx.SendFiles(filepath=emoji_path, who=chat_id)
                            logger.debug(f"已发送表情: {emotion_type}")
                            time.sleep(1)
                    except Exception as e:
                        logger.error(f"发送表情失败 - {emotion_type}: {str(e)}")

                time.sleep(random.randint(2, 4))
        else:
            # 处理不包含分隔符的消息
            emotion_tags = self.emoji_handler.extract_emotion_tags(reply)
            if emotion_tags:
                logger.debug(f"消息包含表情: {emotion_tags}")

            clean_reply = reply
            for tag in emotion_tags:
                clean_reply = clean_reply.replace(f'[{tag}]', '')

            if clean_reply.strip():
                self.wx.SendMsg(msg=clean_reply.strip(), who=chat_id)
                logger.debug(f"发送消息: {clean_reply[:20]}...")

            # 发送表情
            for emotion_type in emotion_tags:
                try:
                    emoji_path = self.emoji_handler.get_emoji_for_emotion(emotion_type)
                    if emoji_path:
                        self.wx.SendFiles(filepath=emoji_path, who=chat_id)
                        logger.debug(f"已发送表情: {emotion_type}")
                        time.sleep(1)
                except Exception as e:
                    logger.error(f"发送表情失败 - {emotion_type}: {str(e)}")

    def _send_raw_message(self, text: str, chat_id: str):
        """直接发送原始文本消息，保留所有换行符和格式

        Args:
            text: 要发送的原始文本
            chat_id: 接收消息的聊天ID
        """
        try:
            # 过滤用户标签
            text = self._filter_user_tags(text)
            
            # 只处理表情符号，不做其他格式处理
            text = self._process_text_for_display(text)

            # 提取表情标签
            emotion_tags = self.emoji_handler.extract_emotion_tags(text)

            # 清理表情标签
            clean_text = text
            for tag in emotion_tags:
                clean_text = clean_text.replace(f'[{tag}]', '')

            # 直接发送消息，只做必要的处理
            if clean_text:
                clean_text = clean_text.replace('$', '')
                clean_text = clean_text.replace('＄', '')  # 全角$符号
                clean_text = clean_text.replace(r'\n', '\r\n\r\n')
                #logger.info(clean_text)
                self.wx.SendMsg(msg=clean_text, who=chat_id)
                #logger.info(f"已发送经过处理的文件内容: {file_content}")

        except Exception as e:
            logger.error(f"发送原始格式消息失败: {str(e)}")

    def _clear_tts_text(self, text: str) -> str:
        """用于清洗回复,使得其适合进行TTS"""
        # 完全移除emoji表情符号
        try:
            # 将emoji转换为空字符串
            text = emoji.replace_emoji(text, replace='')
        except Exception:
            pass

        text = text.replace('$',',')
        text = re.sub(r'\[.*?\]','', text)
        return text.strip()

    def _handle_voice_request(self, content, chat_id, sender_name, username, is_group):
        """处理语音请求"""
        logger.info("处理语音请求")
        # 对于群聊消息，使用更清晰的对话格式
        if is_group:
            api_content = f"<用户 {sender_name}>\n{content}\n</用户>"
        else:
            api_content = content

        reply = self.get_api_response(api_content, chat_id, is_group)
        logger.info(f"AI回复: {reply}")
        logger.info(f"TTS内容: {self._clear_tts_text(reply)}")

        # 处理回复中的思考过程
        if "</think>" in reply:
            think_content, reply = reply.split("</think>", 1)
            logger.debug(f"思考过程: {think_content.strip()}")

        # 群聊环境下添加@标签
        if is_group:
            reply = f"@{sender_name} {reply}"
            logger.debug("群聊环境下发送消息，已添加@标签")
            self._send_message_with_dollar(reply, chat_id)
        else:
            reply = reply.strip()
            voice_path = self.voice_handler.generate_voice(self._clear_tts_text(reply))
            if voice_path:
                try:
                    self.wx.SendFiles(filepath=voice_path, who=chat_id)
                except Exception as e:
                    logger.error(f"发送语音失败: {str(e)}")
                    self._send_message_with_dollar(reply, chat_id)
                finally:
                    try:
                        os.remove(voice_path)
                    except Exception as e:
                        logger.error(f"删除临时语音文件失败: {str(e)}")
            else:
                self._send_message_with_dollar(reply, chat_id)

        # 判断是否是系统消息
        is_system_message = sender_name == "System" or username == "System"

        # 异步保存消息记录
        # 保存实际用户发送的内容，群聊中保留发送者信息
        save_content = api_content if is_group else content
        threading.Thread(target=self.save_message,
                       args=(chat_id, sender_name, save_content, reply, is_system_message)).start()
        return reply

    def _handle_random_image_request(self, content, chat_id, sender_name, username, is_group):
        """处理随机图片请求"""
        logger.info("处理随机图片请求")
        # 对于群聊消息，使用更清晰的对话格式   
        if is_group:
            api_content = f"<用户 {sender_name}>\n{content}\n</用户>"
        else:
            api_content = content

        image_path = self.image_handler.get_random_image()
        if image_path:
            try:
                self.wx.SendFiles(filepath=image_path, who=chat_id)
                reply = "给主人你找了一张好看的图片哦~"
            except Exception as e:
                logger.error(f"发送图片失败: {str(e)}")
                reply = "抱歉主人，图片发送失败了..."
            finally:
                try:
                    if os.path.exists(image_path):
                        os.remove(image_path)
                except Exception as e:
                    logger.error(f"删除临时图片失败: {str(e)}")

            # 群聊环境下添加@标签
            if is_group:
                reply = f"@{sender_name} {reply}"
            # 过滤用户标签再发送
            filtered_reply = self._filter_user_tags(reply)
            self.wx.SendMsg(msg=filtered_reply, who=chat_id)

            # 判断是否是系统消息
            is_system_message = sender_name == "System" or username == "System"

            # 异步保存消息记录
            # 保存实际用户发送的内容，群聊中保留发送者信息
            save_content = api_content if is_group else content
            threading.Thread(target=self.save_message,
                           args=(chat_id, sender_name, save_content, reply, is_system_message)).start()
            return reply
        return None

    def _handle_image_generation_request(self, content, chat_id, sender_name, username, is_group):
        """处理图像生成请求"""
        logger.info("处理画图请求")
        # 对于群聊消息，使用更清晰的对话格式
        if is_group:
            api_content = f"<用户 {sender_name}>\n{content}\n</用户>"
        else:
            api_content = content

        image_path = self.image_handler.generate_image(content)
        if image_path:
            try:
                self.wx.SendFiles(filepath=image_path, who=chat_id)
                reply = "这是按照主人您的要求生成的图片\\(^o^)/~"
            except Exception as e:
                logger.error(f"发送生成图片失败: {str(e)}")
                reply = "抱歉主人，图片生成失败了..."
            finally:
                try:
                    if os.path.exists(image_path):
                        os.remove(image_path)
                except Exception as e:
                    logger.error(f"删除临时图片失败: {str(e)}")

            # 群聊环境下添加@标签
            if is_group:
                reply = f"@{sender_name} {reply}"
            # 过滤用户标签再发送
            filtered_reply = self._filter_user_tags(reply)
            self.wx.SendMsg(msg=filtered_reply, who=chat_id)

            # 判断是否是系统消息
            is_system_message = sender_name == "System" or username == "System"

            # 异步保存消息记录
            # 保存实际用户发送的内容，群聊中保留发送者信息
            save_content = api_content if is_group else content
            threading.Thread(target=self.save_message,
                           args=(chat_id, sender_name, save_content, reply, is_system_message)).start()
            return reply
        return None

    def _send_command_response(self, command: str, reply: str, chat_id: str):
        """发送命令响应，根据命令类型决定是否保留原始格式

        Args:
            command: 命令名称，如 '/state'
            reply: 要发送的回复内容
            chat_id: 聊天ID
        """
        if not reply:
            return

        # 检查是否是需要保留原始格式的命令
        if command in self.preserve_format_commands:
            # 使用原始格式发送消息
            logger.info(f"使用原始格式发送命令响应: {command}")
            self._send_raw_message(reply, chat_id)
        else:
            # 使用正常的消息发送方式
            self._send_message_with_dollar(reply, chat_id)

    def _handle_text_message(self, content, chat_id, sender_name, username, is_group):
        """处理普通文本消息"""
        # 检查是否是命令
        command = None
        if content.startswith('/'):
            command = content.split(' ')[0].lower()
            logger.debug(f"检测到命令: {command}")

        if "取件码" in content:
            timeStr = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            output = f"📅 日期：{timeStr} \n\n"
            # 连接数据库并插入数据
            db_handler = DBHandler("测试")
            if db_handler is not None:
                conn = db_handler.connect_to_db()
                # conditions_phone={
                #     "groupname": "5栋706服务群(何)"
                # },
                conditions_phone=[("groupname", chat_id)]
                print(conditions_phone)
                data_phone = db_handler.select_data(conn, "CoreCmsPhoneCompare",conditions_phone,
            extract_field="hidephone")
                print(data_phone)
            
                if len(data_phone) > 0:
                    conditions_code=[("phone_number", data_phone),("parcel_status", 0),("storage_time", '2025-07-01 01:47:00.000')]
                    print(conditions_code)
                    data_reesult = db_handler.select_data(conn, "CoreCmsParcelStorage",conditions_code,
                group_by="phone_number",extract_field="pickupcode")
                    print(data_reesult)
                    if len(data_reesult) > 0:
                        db_handler.update_status_by_phone_and_code(conn,data_reesult,"CoreCmsParcelStorage")
                        
                        for i, (phone, parcels) in enumerate(data_reesult.items(), 1):
                            conditions_name=[("phone_number", phone)]
                            name_result = db_handler.select_data(conn, "CoreCmsParcelStorage",conditions_name,
                    extract_field="name",limit=1)
                            
                            
                            print(name_result)
                            nameStr = ""
                            if not name_result:  # 列表为空
                                nameStr = "匿名"
                            nameStr = name_result[0] if isinstance(name_result[0], str) else "匿名"
                            
                            output += f"【收件人 {nameStr}】\n"
                            output += f"📱 手机：{phone}\n"
                            output += f"📦 包裹：{len(parcels)}个\n"
                            
                            for j, parcel in enumerate(parcels, 1):
                                output += f"  └─  {parcel}\n"
                            
                            output += "────────────\n"
                            
                        output += "\n尊敬的用户：试运行期间诚邀您提出建议，我们将据此完善功能与服务,如未找到快递请联系客服\n"
                        print(output)
                        current_dir = os.path.dirname(os.path.abspath(__file__))
                        file_path = os.path.join(current_dir, "1.png")  # 拼接路径
                        print(file_path)
                        # self.wx.SendFiles(filepath=file_path, who=chat_id)
                        self._send_message_with_dollar(output, chat_id)
            return content

        '''
        # 使用网络搜索服务处理消息（只检测 URL）
        processed, results, process_type = self.network_search_service.process_message(content)
        if processed and process_type == "weblens":
            # 不发送"正在处理"的提示消息

            if results['original']:
                # 处理群聊中的回复
                original_content = results['original']
                if is_group:
                    original_content = f"@{sender_name}\n{original_content}"

                # 不发送原始内容给用户，而是将其添加到上下文中
                logger.info("将网页内容添加到上下文中，不发送给用户")

                # 异步生成总结并添加到系统提示词中
                # 使用线程异步处理，不占用当前对话的时间
                urls = self.network_search_service.detect_urls(content)
                if urls:
                    url = urls[0]  # 只处理第一个 URL
                    # 使用用户配置的模型
                    threading.Thread(
                        target=self._async_generate_summary,
                        args=(chat_id, url, original_content, None),  # 传入None，使用用户配置的模型
                        daemon=True
                    ).start()
                    logger.info(f"已启动异步线程生成网页内容总结，使用用户配置的模型")

                # 判断是否是系统消息
                is_system_message = sender_name == "System" or username == "System"

                # 异步保存消息记录
                # 从消息中移除链接
                urls = self.network_search_service.detect_urls(content)
                save_content = content
                if urls:
                    for url in urls:
                        save_content = save_content.replace(url, "")

                # 将原始内容添加到上下文中，但不直接返回给用户
                threading.Thread(target=self.save_message,
                                args=(chat_id, sender_name, save_content, save_content, is_system_message)).start()

                # 将原始内容作为上下文添加到当前消息中
                content_with_context = f"{content}\n\n{original_content}"

                # 处理添加了上下文的消息
                api_response = self.get_api_response(content_with_context, chat_id, is_group)

                # 发送API响应给用户
                self._send_raw_message(api_response, chat_id)

                # 返回响应以便保存到历史记录
                return api_response
            else:
                # 如果处理失败，不发送错误消息，直接正常处理请求
                logger.info("提取网页内容失败，继续正常处理请求")
        '''

        # 对于群聊消息，使用更清晰的对话格式
        if is_group:
            api_content = f"<用户 {sender_name}>\n{content}\n</用户>"
        else:
            api_content = content

        reply = self.get_api_response(api_content, chat_id, is_group)
        logger.info(f"AI回复: {reply}")

        # 处理回复中的思考过程
        if "</think>" in reply:
            think_content, reply = reply.split("</think>", 1)
            logger.debug(f"思考过程: {think_content.strip()}")

        # 处理群聊中的回复
        if is_group:
            reply = f"@{sender_name} {reply}"
            logger.debug("已添加群聊@")

        # 判断是否是系统消息
        is_system_message = sender_name == "System" or username == "System"

        # 发送文本消息和表情
        if command and command in self.preserve_format_commands:
            # 如果是需要保留原始格式的命令，使用原始格式发送
            self._send_command_response(command, reply, chat_id)
        else:
            # 否则使用正常的消息发送方式
            self._send_message_with_dollar(reply, chat_id)

        # 异步保存消息记录
        # 保存实际用户发送的内容，群聊中保留发送者信息
        save_content = api_content if is_group else content
        threading.Thread(target=self.save_message,
                        args=(chat_id, sender_name, save_content, reply, is_system_message)).start()
        return reply

    def _add_to_system_prompt(self, chat_id: str, content: str) -> None:
        """
        将内容添加到系统提示词中

        Args:
            chat_id: 聊天ID
            content: 要添加的内容
        """
        try:
            # 初始化聊天的系统提示词字典（如果不存在）
            if not hasattr(self, 'system_prompts'):
                self.system_prompts = {}

            # 初始化当前聊天的系统提示词（如果不存在）
            if chat_id not in self.system_prompts:
                self.system_prompts[chat_id] = []

            # 添加内容到系统提示词列表
            self.system_prompts[chat_id].append(content)

            # 限制系统提示词列表的长度（保留最新的 5 条）
            if len(self.system_prompts[chat_id]) > 5:
                self.system_prompts[chat_id] = self.system_prompts[chat_id][-5:]

            logger.info(f"已将内容添加到聊天 {chat_id} 的系统提示词中")
        except Exception as e:
            logger.error(f"添加内容到系统提示词失败: {str(e)}")

    # 已在类的开头初始化对话计数器

    def _remove_search_content_from_context(self, chat_id: str, content: str) -> None:
        """
        从上下文中删除搜索内容，并添加到系统提示词中

        Args:
            chat_id: 聊天ID
            content: 要删除的搜索内容
        """
        try:
            # 从内存中的对话历史中删除搜索内容
            if hasattr(self, 'memory_service') and self.memory_service:
                # 尝试从内存中删除搜索内容
                # 注意：这里只是一个示例，实际实现可能需要根据 memory_service 的实际接口调整
                try:
                    # 如果 memory_service 有删除内容的方法，可以调用它
                    # 这里只是记录日志，实际实现可能需要根据具体情况调整
                    logger.info(f"尝试从内存中删除搜索内容: {content[:50]}...")
                except Exception as e:
                    logger.error(f"从内存中删除搜索内容失败: {str(e)}")

            # 如果有其他上下文存储机制，也可以在这里处理

            logger.info(f"已从上下文中删除搜索内容: {content[:50]}...")
        except Exception as e:
            logger.error(f"从上下文中删除搜索内容失败: {str(e)}")

    def _async_generate_summary(self, chat_id: str, url: str, content: str, model: str = None) -> None:
        """
        异步生成总结并添加到系统提示词中
        按照时间而不是对话计数来执行总结

        Args:
            chat_id: 聊天ID
            url: 链接或搜索查询
            content: 要总结的内容
            model: 使用的模型（可选，如果不提供则使用用户配置的模型）
        """
        try:
            # 等待一段时间后再执行总结，确保不占用当前对话的时间
            # 这里设置为30秒，足够让用户进行下一次对话
            logger.info(f"开始等待总结生成时间: {url}")
            time.sleep(30)  # 等待 30 秒

            logger.info(f"开始异步生成总结: {url}")

            # 使用用户配置的模型，如果没有指定模型
            from src.config import MODEL
            summary_model = model if model else MODEL

            # 使用 network_search_service 中的 llm_service
            # 生成总结版本，用于系统提示词
            summary_messages = [
                {
                    "role": "user",
                    "content": f"请将以下内容总结为简洁的要点，以便在系统提示词中使用：\n\n{content}\n\n原始链接或查询: {url}"
                }
            ]

            # 调用 network_search_service 中的 llm_service 获取总结版本
            # 使用用户配置的模型
            logger.info(f"异步总结使用模型: {summary_model}")
            summary_result = self.network_search_service.llm_service.chat(
                messages=summary_messages,
                model=summary_model
            )

            if summary_result:
                # 生成最终的总结内容
                if "http" in url:
                    final_summary = f"关于链接 {url} 的信息：{summary_result}"
                else:
                    final_summary = f"关于\"{url}\"的信息：{summary_result}"

                # 从上下文中删除搜索内容
                self._remove_search_content_from_context(chat_id, content)

                # 添加到系统提示词中，但不发送给用户
                self._add_to_system_prompt(chat_id, final_summary)
                logger.info(f"已将异步生成的总结添加到系统提示词中，并从上下文中删除搜索内容: {url}")
            else:
                logger.warning(f"异步生成总结失败: {url}")
        except Exception as e:
            logger.error(f"异步生成总结失败: {str(e)}")

    #def _check_time_reminder_and_search(self, content: str, user_id: str, chat_id: str, sender_name: str, is_group: bool) -> bool:
    def _check_time_reminder_and_search(self, content: str, sender_name: str) -> bool:
        """
        检查和处理时间提醒和联网搜索需求

        Args:
            content: 消息内容
            chat_id: 聊天ID
            sender_name: 发送者名称

        Returns:
            bool: 是否已处理搜索需求（如果已处理，则不需要继续处理消息）
        """
        # 避免处理系统消息
        if sender_name == "System" or sender_name.lower() == "system" :
            logger.debug(f"跳过时间提醒和搜索识别：{sender_name}发送的消息不处理")
            return False

        try:
            if "可作为你的回复参考" in content:
                logger.info(f"已联网获取过信息，直接获取回复")
                return True
            '''
            # 使用 time_recognition 服务同时识别时间和搜索需求
            # 传递用户名和角色名，用于替换提示词中的变量
            # 传递网络搜索启用状态
            from src.config import NETWORK_SEARCH_ENABLED

            result = self.time_recognition.recognize_time_and_search(
                message=content,
                user_name=sender_name,
                avatar_name=self.current_avatar,
                network_search_enabled=NETWORK_SEARCH_ENABLED
            )

            # 处理提醒
            if result['reminders']:
                for target_time, reminder_content in result['reminders']:
                    logger.info(f"检测到提醒请求 - 用户: {sender_name}")
                    logger.info(f"提醒时间: {target_time}, 内容: {reminder_content}")

                    # 使用 reminder_service 创建提醒
                    success = self.reminder_service.add_reminder(
                        chat_id=chat_id,
                        target_time=target_time,
                        content=reminder_content,
                        sender_name=sender_name,
                        silent=True
                    )

                    if success:
                        logger.info("提醒任务创建成功")
                    else:
                        logger.error("提醒任务创建失败")

            # 处理搜索需求 - 只在没有在timeout期间处理过的情况下处理
            # 检查消息中是否已经包含搜索结果
            if NETWORK_SEARCH_ENABLED and result['search_required'] and result['search_query']:
                # 检查消息中是否已经包含搜索结果的标记
                if "以下是关于" in content and "的搜索结果" in content:
                    logger.info(f"消息中已包含搜索结果，跳过搜索处理")
                    return False

                logger.info(f"检测到搜索需求 - 用户: {sender_name}")
                logger.info(f"搜索查询: {result['search_query']}")

                # 先发送一个正在搜索的提示
                processing_message = f"正在搜索：{result['search_query']}，请稍候..."
                self._send_raw_message(processing_message, chat_id)

                # 获取对话上下文
                conversation_context = self.memory_service.get_recent_context(self.current_avatar, user_id)

                # 调用网络搜索服务，传递对话上下文
                search_results = self.network_search_service.search_internet(
                    query=result['search_query'],
                    conversation_context=conversation_context
                )

                if search_results['original']:
                    # 不发送搜索结果给用户，而是将其添加到上下文中
                    logger.info("将搜索结果添加到上下文中，不发送给用户")

                    # 异步生成总结并添加到系统提示词中
                    # 使用用户配置的模型
                    threading.Thread(
                        target=self._async_generate_summary,
                        args=(chat_id, result['search_query'], search_results['original'], None),  # 传入None，使用用户配置的模型
                        daemon=True
                    ).start()
                    logger.info(f"已启动异步线程生成搜索结果总结，使用用户配置的模型")

                    # 异步保存消息记录
                    is_system_message = sender_name == "System" or sender_name.lower() == "system"
                    threading.Thread(target=self.save_message,
                                    args=(chat_id, sender_name, content, content, is_system_message)).start()

                    # 将搜索结果作为上下文添加到当前消息中
                    content_with_context = f"{content}\n\n{search_results['original']}"

                    # 处理添加了上下文的消息
                    api_response = self.get_api_response(content_with_context, chat_id, is_group)

                    # 发送API响应给用户
                    self._send_raw_message(api_response, chat_id)

                    # 返回 True 表示已处理搜索需求
                    return True
                else:
                    # 搜索失败，不发送错误消息，直接返回处理失败
                    logger.info("搜索失败，不发送错误消息，继续正常处理请求")
                

            # 返回 False 表示未处理搜索需求或处理失败
            return False
            '''

        except Exception as e:
            logger.error(f"处理时间提醒和搜索失败: {str(e)}")
            return False

    def _check_time_reminder(self, content: str, chat_id: str, sender_name: str):
        """检查和处理时间提醒（兼容旧接口）"""
        # 避免处理系统消息
        if sender_name == "System" or sender_name.lower() == "system" :
            logger.debug(f"跳过时间提醒识别：{sender_name}发送的消息不处理")
            return

        try:
            # 使用 time_recognition 服务识别时间
            time_infos = self.time_recognition.recognize_time(content)
            if time_infos:
                for target_time, reminder_content in time_infos:
                    logger.info(f"检测到提醒请求 - 用户: {sender_name}")
                    logger.info(f"提醒时间: {target_time}, 内容: {reminder_content}")

                    # 使用 reminder_service 创建提醒
                    success = self.reminder_service.add_reminder(
                        chat_id=chat_id,
                        target_time=target_time,
                        content=reminder_content,
                        sender_name=sender_name,
                        silent=True
                    )

                    if success:
                        logger.info("提醒任务创建成功")
                    else:
                        logger.error("提醒任务创建失败")

        except Exception as e:
            logger.error(f"处理时间提醒失败: {str(e)}")

    def add_to_queue(self, chat_id: str, content: str, sender_name: str,
                    username: str, is_group: bool = False):
        """添加消息到队列（兼容旧接口）"""
        return self._add_to_message_queue(content, chat_id, sender_name, username, is_group, False)

    def process_messages(self, chat_id: str):
        """处理消息队列中的消息（已废弃，保留兼容）"""
        # 该方法不再使用，保留以兼容旧代码
        logger.warning("process_messages方法已废弃，使用handle_message代替")
        pass