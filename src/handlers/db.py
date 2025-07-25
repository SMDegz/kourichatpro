import logging
import pyodbc
from datetime import date
from src.utils.console import print_status

logger = logging.getLogger('main')

class DBHandler:
    def __init__(self,str):
        self.name = str
        print(self.name)
    
    def connect_to_db(self):
        """连接到SQL Server数据库"""
        try:
            # conn = pyodbc.connect(
            #     'Driver={SQL Server};'
            #     'Server=47.113.149.254;'
            #     'Database=CoreShop;'
            #     'Trusted_Connection=yes;'
            # )
            conn = pyodbc.connect(
                'Driver={SQL Server};'
                'Server=47.113.149.254;'
                'Database=CoreShop;'
                'UID=sa;'  # 替换为实际用户名
                'PWD=456123.zz;'  # 替换为实际密码
            )
            return conn
        except Exception as e:
            logging.error(f'数据库连接失败: {str(e)}')
            raise
        
    def update_dataLoop(self, conn, id):
        try:
            cursor = conn.cursor()
            sql = f"""
                    UPDATE CoreCmsParcelStorage
                    SET sendstatus = 0
                    WHERE id = {id}
                    """
            # 执行更新
            cursor.execute(sql)
            # 提交所有更新
            conn.commit()
            print(f"更新成功")
            
        except Exception as e:
            conn.rollback()
            logging.error(f"更新状态失败: {str(e)}")
            raise
        finally:
            cursor.close()
                
    def select_dataLoop(self,conn):
        """查询数据库"""
        try:
            cursor = conn.cursor()
            
            today = date.today()
            formatted_date = today.strftime('%Y-%m-%d')

            
            # 构建SELECT语句，将TOP直接放在SELECT后面
            sql = f"""
                SELECT DISTINCT  
                    a.id,
                    a.name,
                    a.phone_number,
                    a.pickupcode,
                    a.parcel_status,
                    a.storage_time,
                    b.groupname
                FROM [dbo].[CoreCmsParcelStorage] a
                INNER JOIN [dbo].[CoreCmsPhoneCompare] b 
                    ON a.phone_number = b.hidephone
                WHERE 
                    a.status = 1 
                    AND a.sendstatus = 1 
                    AND a.storage_time > '{formatted_date}'  -- 使用参数化查询
                """                    
           
            print(sql)
            
            cursor.execute(sql)

            # 获取查询结果
            results = cursor.fetchall()
            
            #print(results)
            
            return results
            
        except Exception as e:
            print_status(f'查询失败: {str(e)}')
            raise        
    
            
    def select_data(self,conn, table_name, conditions=None, order_by=None, limit=None,group_by=None, extract_field=None):
        """查询数据库"""
        try:
            cursor = conn.cursor()
            
            # 构建SELECT语句
            # 处理LIMIT参数，转换为TOP语法
            limit_clause = f"TOP {limit}" if limit else ""
            
            # 构建SELECT语句，将TOP直接放在SELECT后面
            sql = f"SELECT {limit_clause} * FROM {table_name}"                              
            values = []
            # 添加查询条件
            if conditions:
                where_conditions = []
               
                
                for k, v in conditions:
                    if isinstance(v, list):
                        # 处理IN子句：生成多个?占位符
                        placeholders = ", ".join(["?"] * len(v))
                        where_conditions.append(f"{k} IN ({placeholders})")
                        values.extend(v)  # 展开列表为多个值
                    else:
                        # 判断键是否包含"time"，决定使用>还是=
                        operator = ">" if "time" in k.lower() else "="
                        where_conditions.append(f"{k} {operator} ?")
                        values.append(v)
                
                if where_conditions:
                    sql += " WHERE " + " AND ".join(where_conditions)
            
            # 添加排序
            if order_by:
                sql += f" ORDER BY {order_by}"
                
            print(sql)
            
            # 执行SELECT语句
            if conditions:
                cursor.execute(sql, list(values))
            else:
                cursor.execute(sql)
                
            # 获取查询结果
            results = cursor.fetchall()
            
            print(results)
            
            if results:
                # 按指定字段分组
                if group_by and results:
                    grouped_data = {}
                    for row in results:
                        # 将行转换为字典以便按字段名访问
                        row_dict = dict(zip([column[0] for column in cursor.description], row))
                        group_key = row_dict[group_by]
                        
                        if group_key not in grouped_data:
                            grouped_data[group_key] = []
                            
                        grouped_data[group_key].append(row_dict)
                    
                    # 提取指定字段
                    if extract_field:
                        extracted_data = {}
                        for group_key, group_items in grouped_data.items():
                            # 提取每组中的指定字段
                            extracted_values = [item[extract_field] for item in group_items]
                            extracted_data[group_key] = extracted_values
                            
                            print(f"\n分组: {group_key} ({len(extracted_values)} 个 {extract_field})")
                            print(f"  {extract_field}列表: {extracted_values}")
                        
                        return extracted_data
                    else:
                        # 未指定提取字段，返回原始分组数据
                        for group_key, group_items in grouped_data.items():
                            print(f"\n分组: {group_key} ({len(group_items)} 条记录)")
                            for i, item in enumerate(group_items, 1):
                                print(f"  记录 {i}: {item}")
                    
                    return grouped_data
                else:
                    
                    if extract_field:
                        # 获取列名
                        columns = [desc[0] for desc in cursor.description]
                        # 将结果转换为字典列表
                        results_dict = [dict(zip(columns, row)) for row in results]
                        # 通过列名提取字段值
                        field_list = [row[extract_field] for row in results_dict]   
                        return field_list
                        
                    # 未指定分组字段或结果为空，直接返回原始结果
                    print(f"查询结果 ({len(results)} 条记录)")
                    for i, row in enumerate(results, 1):
                        row_dict = dict(zip([column[0] for column in cursor.description], row))
                        print(f"记录 {i}: {row_dict}")
                        
                    return results
            else:
                return results
            
        except Exception as e:
            print_status(f'查询失败: {str(e)}')
            raise
        
    def extract_field(self,conn,results,extract_field):
        if extract_field:
            cursor = conn.cursor()
            # 获取列名
            columns = [desc[0] for desc in cursor.description]
            # 将结果转换为字典列表
            results_dict = [dict(zip(columns, row)) for row in results]
            # 通过列名提取字段值
            field_list = [row[extract_field] for row in results_dict]   
            return field_list
        
    def update_status_by_phone_and_code(self, conn,data, table_name):
        """
        根据手机号和取货码更新记录状态
        
        参数:
            conn: 数据库连接
            data: 字典，格式为 {phone_number: [pickupcode1, pickupcode2, ...]}
        """
        try:
            cursor = conn.cursor()
            
            # 遍历每个手机号及其对应的取货码列表
            for phone_number, pickup_codes in data.items():
                # 为每个取货码生成一个更新语句
                for pickup_code in pickup_codes:
                    # 构建SQL更新语句
                    sql = f"""
                    UPDATE {table_name}
                    SET sendstatus = 0
                    WHERE phone_number = ? AND pickupcode = ?
                    """
                    print(sql)
                    # 执行更新
                    cursor.execute(sql, (phone_number, pickup_code))
                    print(f"更新记录: 手机号={phone_number}, 取货码={pickup_code}, 影响行数={cursor.rowcount}")
            
            # 提交所有更新
            conn.commit()
            print(f"成功更新 {len(data)} 个手机号的取货码状态")
            
        except Exception as e:
            conn.rollback()
            logging.error(f"更新状态失败: {str(e)}")
            raise
        finally:
            cursor.close()
        
            
    def update_data(self, conn,table_name ,data, condition):
        try:
            cursor = conn.cursor()
            
            # 构建SET子句
            set_clause = ', '.join([f"{key} = ?" for key in data.keys()])
            
            # 构建WHERE子句
            where_clause = ' AND '.join([f"{key} = ?" for key in condition.keys()])
            
            # 组合完整的UPDATE语句
            sql = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"
            
            # 组合参数
            params = list(data.values()) + list(condition.values())
            
            # 执行UPDATE语句
            cursor.execute(sql, params)
            conn.commit()
            print_status('数据更新成功')
            
        except Exception as e:
            conn.rollback()
            logging.error(f'数据更新失败: {str(e)}')
            raise
            
        finally:
            cursor.close()    
                
    def insert_data(self,conn,table_name, data):
        """将数据插入到数据库"""
        try:
            cursor = conn.cursor()
            
            # 构建INSERT语句
            columns = ', '.join(data.keys())
            values = ', '.join(['?' for _ in data])
            sql = f"INSERT INTO {table_name} ({columns}) VALUES ({values})"
            
            # 执行INSERT语句
            cursor.execute(sql, list(data.values()))
            conn.commit()
            print_status('数据导入成功')
        except Exception as e:
            conn.rollback()
            logging.error(f'数据导入失败: {str(e)}')
            raise
        finally:
            cursor.close()
            
