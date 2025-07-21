@app.route('/get_all_configs')
def get_all_configs():
    """获取所有最新的配置数据"""
    try:
        # 直接从配置文件读取所有配置数据
        config_path = os.path.join(ROOT_DIR, 'src/config/config.json')
        
        # 检查文件是否存在
        if not os.path.exists(config_path):
            logger.warning(f"配置文件不存在: {config_path}")
            return jsonify({
                "status": "error",
                "message": "配置文件不存在"
            })
            
        # 读取配置文件    
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        # 解析配置数据为前端需要的格式
        configs = {}
        tasks = []

        # 处理用户设置
        if 'categories' in config_data:
            # 用户设置
            if 'user_settings' in config_data['categories'] and 'settings' in config_data['categories']['user_settings']:
                configs['基础配置'] = {}
                if 'listen_list' in config_data['categories']['user_settings']['settings']:
                    configs['基础配置']['LISTEN_LIST'] = config_data['categories']['user_settings']['settings']['listen_list']
                if 'group_chat_config' in config_data['categories']['user_settings']['settings']:
                    configs['基础配置']['GROUP_CHAT_CONFIG'] = config_data['categories']['user_settings']['settings']['group_chat_config']

            # LLM设置
            if 'llm_settings' in config_data['categories'] and 'settings' in config_data['categories']['llm_settings']:
                llm_settings = config_data['categories']['llm_settings']['settings']
                if 'api_key' in llm_settings:
                    configs['基础配置']['DEEPSEEK_API_KEY'] = llm_settings['api_key']
                if 'base_url' in llm_settings:
                    configs['基础配置']['DEEPSEEK_BASE_URL'] = llm_settings['base_url']
                if 'model' in llm_settings:
                    configs['基础配置']['MODEL'] = llm_settings['model']
                if 'max_tokens' in llm_settings:
                    configs['基础配置']['MAX_TOKEN'] = llm_settings['max_tokens']
                if 'temperature' in llm_settings:
                    configs['基础配置']['TEMPERATURE'] = llm_settings['temperature']

            # 媒体设置
            if 'media_settings' in config_data['categories'] and 'settings' in config_data['categories']['media_settings']:
                media_settings = config_data['categories']['media_settings']['settings']

                # 图像识别设置
                configs['图像识别API配置'] = {}
                if 'image_recognition' in media_settings:
                    img_recog = media_settings['image_recognition']
                    if 'api_key' in img_recog:
                        # 保留完整配置，包括元数据
                        configs['图像识别API配置']['VISION_API_KEY'] = img_recog['api_key']
                    if 'base_url' in img_recog:
                        configs['图像识别API配置']['VISION_BASE_URL'] = img_recog['base_url']
                    if 'temperature' in img_recog:
                        configs['图像识别API配置']['VISION_TEMPERATURE'] = img_recog['temperature']
                    if 'model' in img_recog:
                        configs['图像识别API配置']['VISION_MODEL'] = img_recog['model']

            # 行为设置
            if 'behavior_settings' in config_data['categories'] and 'settings' in config_data['categories']['behavior_settings']:
                behavior = config_data['categories']['behavior_settings']['settings']

                # 主动消息配置
                configs['主动消息配置'] = {}
                if 'auto_message' in behavior:
                    auto_msg = behavior['auto_message']
                    if 'content' in auto_msg:
                        configs['主动消息配置']['AUTO_MESSAGE'] = auto_msg['content']
                    if 'countdown' in auto_msg:
                        if 'min_hours' in auto_msg['countdown']:
                            configs['主动消息配置']['MIN_COUNTDOWN_HOURS'] = auto_msg['countdown']['min_hours']
                        if 'max_hours' in auto_msg['countdown']:
                            configs['主动消息配置']['MAX_COUNTDOWN_HOURS'] = auto_msg['countdown']['max_hours']

                if 'quiet_time' in behavior:
                    quiet = behavior['quiet_time']
                    if 'start' in quiet:
                        configs['主动消息配置']['QUIET_TIME_START'] = quiet['start']
                    if 'end' in quiet:
                        configs['主动消息配置']['QUIET_TIME_END'] = quiet['end']

                # 消息队列配置
                configs['消息配置'] = {}
                if 'message_queue' in behavior:
                    msg_queue = behavior['message_queue']
                    if 'timeout' in msg_queue:
                        configs['消息配置']['QUEUE_TIMEOUT'] = msg_queue['timeout']

                # 人设配置
                configs['人设配置'] = {}
                if 'context' in behavior:
                    context = behavior['context']
                    if 'max_groups' in context:
                        configs['人设配置']['MAX_GROUPS'] = context['max_groups']
                    if 'avatar_dir' in context:
                        configs['人设配置']['AVATAR_DIR'] = context['avatar_dir']

            # 网络搜索设置
            if 'network_search_settings' in config_data['categories'] and 'settings' in config_data['categories']['network_search_settings']:
                network_search = config_data['categories']['network_search_settings']['settings']
                configs['网络搜索配置'] = {}
                if 'search_enabled' in network_search:
                    configs['网络搜索配置']['NETWORK_SEARCH_ENABLED'] = network_search['search_enabled']
                if 'weblens_enabled' in network_search:
                    configs['网络搜索配置']['WEBLENS_ENABLED'] = network_search['weblens_enabled']
                if 'api_key' in network_search:
                    configs['网络搜索配置']['NETWORK_SEARCH_API_KEY'] = network_search['api_key']
                if 'base_url' in network_search:
                    configs['网络搜索配置']['NETWORK_SEARCH_BASE_URL'] = network_search['base_url']

            # 定时任务
            if 'schedule_settings' in config_data['categories'] and 'settings' in config_data['categories']['schedule_settings']:
                if 'tasks' in config_data['categories']['schedule_settings']['settings']:
                    tasks = config_data['categories']['schedule_settings']['settings']['tasks'].get('value', [])

        logger.debug(f"获取到的所有配置数据: {configs}")
        logger.debug(f"获取到的任务数据: {tasks}")

        return jsonify({
            'status': 'success',
            'configs': configs,
            'tasks': tasks
        })
    except Exception as e:
        logger.error(f"获取所有配置数据失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

def update_config_value(config_data, key, value):
    """更新配置值"""
    logger.debug(f"更新配置项: {key} = {value}")

    # 处理不同的配置项
    if key == 'LISTEN_LIST':
        # 确保是列表形式
        if isinstance(value, str):
            value = value.split(',')
            # 过滤空值并去除前后空格
            value = [v.strip() for v in value if v.strip()]
        elif not isinstance(value, list):
            value = [str(value)] if value else []

        # 确保配置结构存在
        if 'categories' not in config_data:
            config_data['categories'] = {}
        if 'user_settings' not in config_data['categories']:
            config_data['categories']['user_settings'] = {
                'title': '用户设置',
                'settings': {}
            }
        if 'settings' not in config_data['categories']['user_settings']:
            config_data['categories']['user_settings']['settings'] = {}

        # 更新配置
        config_data['categories']['user_settings']['settings']['listen_list'] = {
            'value': value,
            'type': 'array',
            'description': '要监听的用户列表（请使用微信昵称，不要使用备注名）'
        }
    elif key == 'GROUP_CHAT_CONFIG':
        # 群聊配置
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except:
                value = []
        elif not isinstance(value, list):
            value = []

        # 确保配置结构存在
        if 'categories' not in config_data:
            config_data['categories'] = {}
        if 'user_settings' not in config_data['categories']:
            config_data['categories']['user_settings'] = {
                'title': '用户设置',
                'settings': {}
            }
        if 'settings' not in config_data['categories']['user_settings']:
            config_data['categories']['user_settings']['settings'] = {}

        # 更新群聊配置
        config_data['categories']['user_settings']['settings']['group_chat_config'] = {
            'value': value,
            'type': 'array',
            'description': '群聊配置列表'
        }
    elif key in ['DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL', 'MODEL', 'MAX_TOKEN', 'TEMPERATURE']:
        # LLM配置
        if 'categories' not in config_data:
            config_data['categories'] = {}
        if 'llm_settings' not in config_data['categories']:
            config_data['categories']['llm_settings'] = {
                'title': '大语言模型配置',
                'settings': {}
            }
        if 'settings' not in config_data['categories']['llm_settings']:
            config_data['categories']['llm_settings']['settings'] = {}

        settings_map = {
            'DEEPSEEK_API_KEY': 'api_key',
            'DEEPSEEK_BASE_URL': 'base_url',
            'MODEL': 'model',
            'MAX_TOKEN': 'max_tokens',
            'TEMPERATURE': 'temperature'
        }

        field = settings_map.get(key)
        if field:
            value_type = 'string'
            if key == 'MAX_TOKEN':
                value = int(value) if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()) else 0
                value_type = 'number'
            elif key == 'TEMPERATURE':
                value = float(value) if isinstance(value, (int, float)) or (isinstance(value, str) and value.replace('.', '', 1).isdigit()) else 0.0
                value_type = 'number'

            is_secret = key == 'DEEPSEEK_API_KEY'
            config_data['categories']['llm_settings']['settings'][field] = {
                'value': value,
                'type': value_type,
                'description': key,
                'is_secret': is_secret
            }
    elif key in ['VISION_API_KEY', 'VISION_BASE_URL', 'VISION_TEMPERATURE', 'VISION_MODEL']:
        # 媒体设置 - 图像识别
        if 'categories' not in config_data:
            config_data['categories'] = {}
        if 'media_settings' not in config_data['categories']:
            config_data['categories']['media_settings'] = {
                'title': '媒体设置',
                'settings': {}
            }
        if 'settings' not in config_data['categories']['media_settings']:
            config_data['categories']['media_settings']['settings'] = {}
        if 'image_recognition' not in config_data['categories']['media_settings']['settings']:
            config_data['categories']['media_settings']['settings']['image_recognition'] = {}

        settings_map = {
            'VISION_API_KEY': 'api_key',
            'VISION_BASE_URL': 'base_url',
            'VISION_TEMPERATURE': 'temperature',
            'VISION_MODEL': 'model'
        }

        field = settings_map.get(key)
        if field:
            value_type = 'string'
            if key == 'VISION_TEMPERATURE':
                value = float(value) if isinstance(value, (int, float)) or (isinstance(value, str) and value.replace('.', '', 1).isdigit()) else 0.0
                value_type = 'number'

            is_secret = key == 'VISION_API_KEY'
            config_data['categories']['media_settings']['settings']['image_recognition'][field] = {
                'value': value,
                'type': value_type,
                'description': key,
                'is_secret': is_secret
            }
    elif key in ['AUTO_MESSAGE', 'MIN_COUNTDOWN_HOURS', 'MAX_COUNTDOWN_HOURS', 'QUIET_TIME_START', 'QUIET_TIME_END']:
        # 行为设置 - 主动消息
        if 'categories' not in config_data:
            config_data['categories'] = {}
        if 'behavior_settings' not in config_data['categories']:
            config_data['categories']['behavior_settings'] = {
                'title': '行为设置',
                'settings': {}
            }
        if 'settings' not in config_data['categories']['behavior_settings']:
            config_data['categories']['behavior_settings']['settings'] = {}
        if 'auto_message' not in config_data['categories']['behavior_settings']['settings']:
            config_data['categories']['behavior_settings']['settings']['auto_message'] = {
                'content': {'value': '', 'type': 'string', 'description': '主动消息内容'},
                'countdown': {
                    'min_hours': {'value': 0, 'type': 'number', 'description': '最小倒计时小时数'},
                    'max_hours': {'value': 0, 'type': 'number', 'description': '最大倒计时小时数'}
                }
            }
        if 'quiet_time' not in config_data['categories']['behavior_settings']['settings']:
            config_data['categories']['behavior_settings']['settings']['quiet_time'] = {
                'start': {'value': '', 'type': 'string', 'description': '免打扰开始时间'},
                'end': {'value': '', 'type': 'string', 'description': '免打扰结束时间'}
            }

        if key == 'AUTO_MESSAGE':
            config_data['categories']['behavior_settings']['settings']['auto_message']['content']['value'] = value
        elif key == 'MIN_COUNTDOWN_HOURS':
            config_data['categories']['behavior_settings']['settings']['auto_message']['countdown']['min_hours']['value'] = float(value) if isinstance(value, (int, float)) or (isinstance(value, str) and value.replace('.', '', 1).isdigit()) else 0
        elif key == 'MAX_COUNTDOWN_HOURS':
            config_data['categories']['behavior_settings']['settings']['auto_message']['countdown']['max_hours']['value'] = float(value) if isinstance(value, (int, float)) or (isinstance(value, str) and value.replace('.', '', 1).isdigit()) else 0
        elif key == 'QUIET_TIME_START':
            config_data['categories']['behavior_settings']['settings']['quiet_time']['start']['value'] = value
        elif key == 'QUIET_TIME_END':
            config_data['categories']['behavior_settings']['settings']['quiet_time']['end']['value'] = value
    elif key == 'QUEUE_TIMEOUT':
        # 行为设置 - 消息队列
        if 'categories' not in config_data:
            config_data['categories'] = {}
        if 'behavior_settings' not in config_data['categories']:
            config_data['categories']['behavior_settings'] = {
                'title': '行为设置',
                'settings': {}
            }
        if 'settings' not in config_data['categories']['behavior_settings']:
            config_data['categories']['behavior_settings']['settings'] = {}
        if 'message_queue' not in config_data['categories']['behavior_settings']['settings']:
            config_data['categories']['behavior_settings']['settings']['message_queue'] = {
                'timeout': {'value': 0, 'type': 'number', 'description': '队列超时时间（秒）'}
            }

        timeout_value = int(value) if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()) else 0
        config_data['categories']['behavior_settings']['settings']['message_queue']['timeout']['value'] = timeout_value
    elif key in ['MAX_GROUPS', 'AVATAR_DIR']:
        # 行为设置 - 上下文
        if 'categories' not in config_data:
            config_data['categories'] = {}
        if 'behavior_settings' not in config_data['categories']:
            config_data['categories']['behavior_settings'] = {
                'title': '行为设置',
                'settings': {}
            }
        if 'settings' not in config_data['categories']['behavior_settings']:
            config_data['categories']['behavior_settings']['settings'] = {}
        if 'context' not in config_data['categories']['behavior_settings']['settings']:
            config_data['categories']['behavior_settings']['settings']['context'] = {
                'max_groups': {'value': 1, 'type': 'number', 'description': '最大群聊数量'},
                'avatar_dir': {'value': '', 'type': 'string', 'description': '人设目录'}
            }

        if key == 'MAX_GROUPS':
            max_groups = int(value) if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()) else 1
            config_data['categories']['behavior_settings']['settings']['context']['max_groups']['value'] = max_groups
        elif key == 'AVATAR_DIR':
            config_data['categories']['behavior_settings']['settings']['context']['avatar_dir']['value'] = value
    elif key in ['NETWORK_SEARCH_ENABLED', 'WEBLENS_ENABLED', 'NETWORK_SEARCH_API_KEY', 'NETWORK_SEARCH_BASE_URL']:
        # 网络搜索设置
        if 'categories' not in config_data:
            config_data['categories'] = {}
        if 'network_search_settings' not in config_data['categories']:
            config_data['categories']['network_search_settings'] = {
                'title': '网络搜索设置',
                'settings': {}
            }
        if 'settings' not in config_data['categories']['network_search_settings']:
            config_data['categories']['network_search_settings']['settings'] = {}

        settings_map = {
            'NETWORK_SEARCH_ENABLED': 'search_enabled',
            'WEBLENS_ENABLED': 'weblens_enabled',
            'NETWORK_SEARCH_API_KEY': 'api_key',
            'NETWORK_SEARCH_BASE_URL': 'base_url'
        }

        field = settings_map.get(key)
        if field:
            value_type = 'string'
            if key in ['NETWORK_SEARCH_ENABLED', 'WEBLENS_ENABLED']:
                value = value if isinstance(value, bool) else (value.lower() == 'true' if isinstance(value, str) else bool(value))
                value_type = 'boolean'

            is_secret = key == 'NETWORK_SEARCH_API_KEY'
            config_data['categories']['network_search_settings']['settings'][field] = {
                'value': value,
                'type': value_type,
                'description': key,
                'is_secret': is_secret
            }

@app.route('/save', methods=['POST'])
def save_config():
    """保存配置"""
    try:
        # 检查Content-Type
        if not request.is_json:
            return jsonify({
                "status": "error",
                "message": "请求Content-Type必须是application/json",
                "title": "错误"
            }), 415

        # 获取JSON数据
        config_data = request.get_json()
        if not config_data:
            return jsonify({
                "status": "error",
                "message": "无效的JSON数据",
                "title": "错误"
            }), 400

        # 读取当前配置
        current_config = load_config_file()

        # 处理配置更新
        for key, value in config_data.items():
            # 处理任务配置
            if key == 'TASKS':
                try:
                    tasks = value if isinstance(value, list) else (json.loads(value) if isinstance(value, str) else [])
                    logger.debug(f"处理任务数据: {tasks}")

                    # 确保schedule_settings结构存在
                    if 'categories' not in current_config:
                        current_config['categories'] = {}
                    if 'schedule_settings' not in current_config['categories']:
                        current_config['categories']['schedule_settings'] = {
                            'title': '定时任务配置',
                            'settings': {}
                        }
                    if 'settings' not in current_config['categories']['schedule_settings']:
                        current_config['categories']['schedule_settings']['settings'] = {}
                    if 'tasks' not in current_config['categories']['schedule_settings']['settings']:
                        current_config['categories']['schedule_settings']['settings']['tasks'] = {
                            'value': [],
                            'type': 'array',
                            'description': '定时任务列表'
                        }

                    # 更新任务列表
                    current_config['categories']['schedule_settings']['settings']['tasks']['value'] = tasks
                except Exception as e:
                    logger.error(f"处理定时任务配置失败: {str(e)}")
                    return jsonify({
                        "status": "error",
                        "message": f"处理定时任务配置失败: {str(e)}",
                        "title": "错误"
                    }), 400
            # 处理其他配置项
            elif key in ['LISTEN_LIST', 'GROUP_CHAT_CONFIG', 'DEEPSEEK_BASE_URL', 'MODEL', 'DEEPSEEK_API_KEY', 'MAX_TOKEN', 'TEMPERATURE',
                       'VISION_API_KEY', 'VISION_BASE_URL', 'VISION_TEMPERATURE', 'VISION_MODEL',
                       'IMAGE_MODEL', 'TEMP_IMAGE_DIR', 'AUTO_MESSAGE', 'MIN_COUNTDOWN_HOURS', 'MAX_COUNTDOWN_HOURS',
                       'QUIET_TIME_START', 'QUIET_TIME_END', 'TTS_API_URL', 'VOICE_DIR', 'MAX_GROUPS', 'AVATAR_DIR',
                       'QUEUE_TIMEOUT', 'NETWORK_SEARCH_ENABLED', 'WEBLENS_ENABLED', 'NETWORK_SEARCH_API_KEY', 'NETWORK_SEARCH_BASE_URL']:
                update_config_value(current_config, key, value)
            else:
                logger.warning(f"未知的配置项: {key}")

        # 保存配置
        if not save_config_file(current_config):
            return jsonify({
                "status": "error",
                "message": "保存配置文件失败",
                "title": "错误"
            }), 500

        # 立即重新加载配置
        g.config_data = current_config

        # 尝试重新加载全局配置
        try:
            from src.config import config
            config.load_config()
            logger.info("已重新加载全局配置")
        except Exception as e:
            logger.warning(f"重新加载全局配置失败: {str(e)}")

        # 重新初始化定时任务
        # 不再重新初始化任务，只更新配置文件
        logger.info("配置已更新，任务将在主程序下次启动时生效")

        return jsonify({
            "status": "success",
            "message": "✨ 配置已成功保存并生效",
            "title": "保存成功"
        })

    except Exception as e:
        logger.error(f"保存配置失败: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"保存失败: {str(e)}",
            "title": "错误"
        }), 500 