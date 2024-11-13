import streamlit as st
import sqlite3
from openai import OpenAI
import networkx as nx
import pdfplumber
from datetime import datetime
import re
from vector_store import (
    vectorize_document, 
    search_similar, 
    num_tokens_from_string,
    init_pinecone,
    get_vector_search_results
)
import pandas as pd
import json
import os
from pymongo import MongoClient
from bson import json_util
import time
import traceback

def check_data_initialized():
    """检查是否已有数据"""
    try:
        db = get_mongodb_connection()
        if db is None:
            return False
        
        # 检查是否有数据
        count = db.patients.count_documents({})
        return count > 0
    except Exception as e:
        st.error(f"检查数据初始化状态错误: {str(e)}")
        return False

def get_mongodb_connection():
    """获取MongoDB连接并测试连接"""
    # 如果已经有连接，直接返回
    if 'mongodb_connection' in st.session_state:
        return st.session_state.mongodb_connection
    
    try:
        client = MongoClient(
            "mongodb+srv://alantany:Mikeno01@airss.ykc1h.mongodb.net/ai-news?retryWrites=true&w=majority&appName=MedicalRAG",
            tlsAllowInvalidCertificates=True
        )
        # 测试连接
        client.server_info()
        db = client['medical_records']
        st.write("✅ MongoDB连接成功")
        # 保存连接到session_state
        st.session_state.mongodb_connection = db
        return db
    except Exception as e:
        st.error(f"MongoDB连接错误: {str(e)}")
        return None

def get_structured_data(text: str) -> dict:
    """使用LLM提取医疗相关的结构化数据"""
    try:
        # 旧的配置
        # client = OpenAI(
        #     api_key="sk-2D0EZSwcWUcD4c2K59353b7214854bBd8f35Ac131564EfBa",
        #     base_url="https://free.gpt.ge/v1"
        # )
        
        # 新的配置
        client = OpenAI(
            api_key="sk-1pUmQlsIkgla3CuvKTgCrzDZ3r0pBxO608YJvIHCN18lvOrn",
            base_url="https://api.chatanywhere.tech/v1"
        )
        
        # 读取示例JSON
        with open('get_inf.json', 'r', encoding='utf-8') as f:
            example_json = f.read()
        
        prompt = """请参照以下示例JSON格式，从医疗病历中提取结构化信息。

示例JSON格式：
{example_json}

病历内容：
{text}

请严格按照示例JSON的格式提取信息，注意：
1. 使用相同的中文字段名
2. 完全相同的数据结构层次
3. 提取所有可能的检验指标和具体数值
4. 保留数值的精确度和单位
5. 对于数组类型的字段（如"现病史"、"入院诊断"等），尽可能完整地列出所有项目
6. 保持日期格式的统一（YYYY-MM-DD）
7. 确保生成的是合法的JSON格式
8. 使用null表示缺失的信息
9. 特别注意提取所有生化指标的具体数值和单位
10. 保持生命体征的格式统一

请直接返回JSON数据，不要包含其他内容。
确保返回的JSON使用中文字段名，与示例完全一致。""".format(
            example_json=example_json,
            text=text
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "你是一个医疗信息结构化专家，擅长从病历中提取关键医疗信息并生成规范的JSON数据。请严格按照示例格式提取信息，使用中文字段名。"
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.1
        )
        
        # 获取并解析JSON响应
        json_str = response.choices[0].message.content.strip()
        
        # 清理JSON字符串
        if json_str.startswith('```json'):
            json_str = json_str[7:]
        if json_str.endswith('```'):
            json_str = json_str[:-3]
        json_str = json_str.strip()
        
        # 显示原始JSON字符串（用于调试）
        st.write("AI返回的JSON字符串：")
        st.code(json_str, language="json")
        
        # 解析JSON
        data = json.loads(json_str)
        
        # 删除_id字段（如果存在）
        if '_id' in data:
            del data['_id']
        
        return data
        
    except Exception as e:
        st.error(f"结构化数据提取错误: {str(e)}")
        st.error("原始错误：" + str(e))
        return None

def get_database_commands(text: str) -> dict:
    """使用LLM分析病历内容并生成数据库命令"""
    try:
        client = OpenAI(
            api_key="sk-1pUmQlsIkgla3CuvKTgCrzDZ3r0pBxO608YJvIHCN18lvOrn",
            base_url="https://api.chatanywhere.tech/v1"
        )
        
        # 显示正在处理的文本
        st.write("正在分析的病历内容：")
        st.code(text[:200] + "...")  # 只显示前200个字符
        
        prompt = """请分析以下医疗病历，并生成数据库命令。严按照JSON格式返回，不要包含任何其他内容：

病历内容：
{}

返回格式：
{{
    "relational_db": {{
        "create_tables": [
            "CREATE TABLE IF NOT EXISTS patients (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, gender TEXT, age INTEGER, admission_date DATE);",
            "CREATE TABLE IF NOT EXISTS diagnoses (id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, diagnosis TEXT, FOREIGN KEY(patient_id) REFERENCES patients(id));"
        ],
        "insert_data": [
            "INSERT INTO patients (name, gender, age, admission_date) VALUES ('张三', '男', 45, '2024-01-01');",
            "INSERT INTO diagnoses (patient_id, diagnosis) VALUES (1, '高血压');"
        ]
    }},
    "graph_db": {{
        "nodes": [
            {{
                "id": "patient_1",
                "type": "patient",
                "properties": {{
                    "name": "张三",
                    "age": 45,
                    "gender": "男"
                }}
            }}
        ],
        "relationships": [
            {{
                "from_node": "patient_1",
                "to_node": "diagnosis_1",
                "type": "HAS_DIAGNOSIS",
                "properties": {{
                    "date": "2024-01-01"
                }}
            }}
        ]
    }}
}}""".format(text)

        # 显示发送给LLM的提示词
        st.write("发送给AI的提示词：")
        st.code(prompt[:200] + "...")  # 只显示前200个字符
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "你是一个医疗数据库专家。请严格按照JSON格式返回数据库命令，确保SQL语句和图数据库命令都是完整且可执行的。"
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.1  # 降低随机性
        )
        
        # 获取响应文本
        response_text = response.choices[0].message.content.strip()
        
        # 显示原响应
        st.write("AI的始响应：")
        st.code(response_text)
        
        # 清理响应文本
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        try:
            # 尝试解JSON
            commands = json.loads(response_text)
            
            # 验证JSON结构
            if not isinstance(commands, dict):
                raise ValueError("返回的不是有效的JSON对象")
            if "relational_db" not in commands or "graph_db" not in commands:
                raise ValueError("JSON缺少必要的键")
            
            # 显示解析后的命令
            st.write("解析后的数据库命令：")
            st.json(commands)
            
            return commands
        except json.JSONDecodeError as e:
            st.error(f"JSON: {str(e)}")
            st.error("位置：" + str(e.pos))
            st.error("行号：" + str(e.lineno))
            st.error("列号：" + str(e.colno))
            return None
        except ValueError as e:
            st.error(f"数据验证错误: {str(e)}")
            return None
            
    except Exception as e:
        st.error(f"生成数据库命令失败: {str(e)}")
        st.error("原始错误：" + str(e))  # 显示详细错误信息
        return None

def execute_database_commands(commands: dict):
    """执行数据库命令"""
    try:
        # 执行关系数据库命令
        conn = sqlite3.connect('medical_records.db')
        cursor = conn.cursor()
        
        st.write("创建数据表...")
        for create_command in commands['relational_db']['create_tables']:
            cursor.execute(create_command)
            st.write(f"✅ 执行成功: {create_command[:50]}...")
        
        st.write("插数据...")
        for insert_command in commands['relational_db']['insert_data']:
            cursor.execute(insert_command)
            st.write(f"✅ 执行成功: {insert_command[:50]}...")
        
        conn.commit()
        conn.close()
        
        # 创建图数据库
        st.write("构建知识谱...")
        G = nx.Graph()
        
        # 添加节点
        for node in commands['graph_db']['nodes']:
            G.add_node(node['id'], 
                      type=node['type'],
                      **node['properties'])
            st.write(f"✅ 添加节点: {node['id']}")
        
        # 添加关系
        for rel in commands['graph_db']['relationships']:
            G.add_edge(rel['from_node'],
                      rel['to_node'],
                      type=rel['type'],
                      **rel.get('properties', {}))
            st.write(f"✅ 添加关系: {rel['from_node']} -> {rel['to_node']}")
        
        # 保存图
        nx.write_gexf(G, "medical_graph.gexf")
        st.success(f"✅ 知识图谱构建成功，包含 {len(G.nodes)} 个节点和 {len(G.edges)} 条边")
        
        return True
    except Exception as e:
        st.error(f"执行数据库命令失败: {str(e)}")
        return False

# 设置页面配置
st.set_page_config(page_title="医疗 RAG 系统", layout="wide")

# 初始化会话状态
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'data_initialized' not in st.session_state:
    st.session_state.data_initialized = False
if 'file_chunks' not in st.session_state:
    st.session_state.file_chunks = {}
if 'file_indices' not in st.session_state:
    st.session_state.file_indices = {}
if 'structured_data' not in st.session_state:
    st.session_state.structured_data = {}

# PDF解析类
class MedicalRecordParser:
    def __init__(self, pdf_content):
        self.content = pdf_content
        self.parsed_data = self._parse_content()
    
    def _parse_content(self):
        data = {}
        try:
            # 打印PDF容用于调试
            st.write("PDF内容:", self.content)
            
            # 提取基本信息，添加错误理
            def safe_extract(pattern, text, default="未知"):
                match = re.search(pattern, text)
                return match.group(1) if match else default
            
            # 提取基本信息
            data['name'] = safe_extract(r'姓名\s*([\u4e00-\u9fa5]+)', self.content)
            data['gender'] = safe_extract(r'性别\s*([\u4e00-\u9fa5]+)', self.content)
            
            # 提取年龄，添加错误处理
            age_match = re.search(r'年龄\s*(\d+)岁', self.content)
            data['age'] = int(age_match.group(1)) if age_match else 0
            
            data['ethnicity'] = safe_extract(r'民族\s*([\u4e00-\u9fa5]+)', self.content)
            data['marriage'] = safe_extract(r'婚姻\s*([\u4e00-\u9fa5]+)', self.content)
            
            # 提取日期，添加错误处理
            admission_date = safe_extract(r'住院日期\s*:(\d{4}\s*年\d{1,2}月\d{1,2}日)', self.content)
            if admission_date != "未知":
                data['admission_date'] = datetime.strptime(admission_date.replace(' ', ''), '%Y年%m月%d日').strftime('%Y-%m-%d')
            else:
                data['admission_date'] = datetime.now().strftime('%Y-%m-%d')
            
            # 提取主诉和病
            data['chief_complaint'] = safe_extract(r'主\s*诉\s*:(.*?)(?:现病史|$)', self.content)
            data['present_illness'] = safe_extract(r'现病史\s*:(.*?)(?:既往史|$)', self.content)
            data['past_history'] = safe_extract(r'既往史\s*:(.*?)(?:检查|$)', self.content)
            
            # 提取生命体征
            data['vital_signs'] = {
                'temperature': safe_extract_float(r'体温\s*(\d+\.?\d*)\s*℃', self.content),
                'pulse': safe_extract_int(r'脉搏\s*(\d+)\s*次/分', self.content),
                'breathing': safe_extract_int(r'呼吸\s*(\d+)\s*次/分', self.content),
                'blood_pressure': safe_extract(r'血压\s*(\d+/\d+)\s*mmHg', self.content)
            }
            
            # 提取体格检查
            data['physical_exam'] = safe_extract(r'体格检查\s*:(.*?)(?:辅助检|$)', self.content)
            
            # 提取症状（带详细信
            symptoms_text = safe_extract(r'主\s*诉\s*:(.*?)(?:入院时情况|$)', self.content)
            data['symptoms'] = []
            for symptom_match in re.finditer(r'([^，。、]+?)(?:有|出现)([^、]+)', symptoms_text):
                data['symptoms'].append({
                    'symptom': symptom_match.group(1),
                    'description': symptom_match.group(2),
                    'onset_date': None  # 可以进一步提取时间信息
                })
            
            # 取检查结果带异标记）
            data['examinations'] = {}
            exam_patterns = {
                '头颅MRI': r'头颅\s*MRI\s*提示(.*?)。',
                '动态心电图': r'动态心电图\s*:(.*?)。',
                '眼震电图': r'眼震电图提示(.*?)。',
                '血常规': r'血常规[检查]*[:：](.*?)',
                '心脏超声': r'心脏超声[检查]*[:：](.*?)。'
            }
            for exam, pattern in exam_patterns.items():
                if match := re.search(pattern, self.content):
                    result = match.group(1).strip()
                    data['examinations'][exam] = {
                        'result': result,
                        'abnormal': bool(re.search(r'异常|高|降低|不足|过多', result)),
                        'description': result
                    }
            
            # 提取治疗信息
            treatment_text = safe_extract(r'治疗经过\s*:(.*?)(?:出院|$)', self.content)
            data['treatments'] = []
            for treatment_match in re.finditer(r'(给予|使用)([^。、]+?)(?:治疗|用药)', treatment_text):
                data['treatments'].append({
                    'treatment_type': '药物治疗',
                    'medication': treatment_match.group(2),
                    'dosage': None,  # 可以进一步提取剂量信息
                    'frequency': None  # 可以进一步提取频率信息
                })
            
            # 打印解析结果用于调试
            st.write("解析结果:", data)
            
            return data
        except Exception as e:
            st.error(f"析PDF内容时发生错误: {str(e)}")
            # 返回默数据而不是字典
            return {
                'name': '未知者',
                'gender': '未知',
                'age': 0,
                'ethnicity': '未知',
                'marriage': '未知',
                'admission_date': datetime.now().strftime('%Y-%m-%d'),
                'diagnoses': ['未知断'],
                'symptoms': ['未知症状'],
                'examinations': {'基本检查': '未见异常'}
            }

# 添加辅助函
def safe_extract_float(pattern, text, default=0.0):
    """安全提取浮点数"""
    match = re.search(pattern, text)
    try:
        return float(match.group(1)) if match else default
    except:
        return default

def safe_extract_int(pattern, text, default=0):
    """安全提取整数"""
    match = re.search(pattern, text)
    try:
        return int(match.group(1)) if match else default
    except:
        return default

# 添加清理数据的函数
def clear_all_data():
    """清理所有数据"""
    try:
        # 清理向量数据库
        st.write("清理向量数据库...")
        st.session_state.file_chunks = {}
        st.session_state.file_indices = {}
        
        # 清理session state中的结构化数据
        st.write("清理结化数据...")
        st.session_state.structured_data = {}
        st.session_state.mongodb_records = []
        
        # 清理MongoDB中的数据（可选）
        # db = get_mongodb_connection()
        # if db:
        #     db.patients.delete_many({})
        
        st.success("✅ 所有数据清理完")
        return True
    except Exception as e:
        st.error(f"清理数据时出错: {str(e)}")
        return False

# 修改数据导入函数
def import_medical_data(pdf_content):
    try:
        # 首先测试MongoDB连接
        st.write("测试MongoDB连接...")
        db = get_mongodb_connection()
        if db is None:
            st.error("MongoDB连接失败，终止导入")
            return False
        
        # 清理旧数据
        st.write("开始清理旧数据...")
        if not clear_all_data():
            st.error("清理旧数据失败，终止导入")
            return False
        
        # 使用LLM提取结构化数据
        st.write("使用AI提取结构化数据...")
        data = get_structured_data(pdf_content)
        if not data:
            st.error("结构化数据提取失败")
            return False
        
        # 添加元数据
        data['metadata'] = {
            'import_time': datetime.now().isoformat(),
            'source_type': 'pdf',
            'last_updated': datetime.now().isoformat()
        }
        
        # 保存到MongoDB
        st.write("保存结构化数据到MongoDB...")
        try:
            # 保存到patients集合
            result = db.patients.insert_one(data)
            st.write(f" 数据保存到MongoDB (ID: {result.inserted_id})")
            
            # 保存ID到session state以便后续查询
            if 'mongodb_records' not in st.session_state:
                st.session_state.mongodb_records = []
            st.session_state.mongodb_records.append(str(result.inserted_id))
            
            # 同时保存到session state用于即时查询
            st.session_state.structured_data = data
            st.write("✅ 结构化数据保存成功")
        except Exception as e:
            st.error(f"MongoDB插入数据误: {str(e)}")
            return False
        
        # 向量化文档
        st.write("开始向量文档...")
        chunks, index = vectorize_document(pdf_content)
        # 使用患者姓名作为文件名
        file_name = f"{data.get('患者姓名', '未知患者')}的病历"
        st.session_state.file_chunks[file_name] = chunks
        st.session_state.file_indices[file_name] = index
        st.write(f"✅ 向量化成功，共生成 {len(chunks)} 个文档块")
        
        return True
    except Exception as e:
        st.error(f"数据导入误: {str(e)}")
        return False

# 搜索数
def get_vector_search_results(query: str) -> list:
    try:
        results = []
        for file_name, chunks in st.session_state.file_chunks.items():
            index = st.session_state.file_indices[file_name]
            chunk_results = search_similar(query, index, chunks)
            results.extend([f"{file_name}: {chunk}" for chunk in chunk_results])
        return results
    except Exception as e:
        st.error(f"向量搜索错误: {str(e)}")
        return []

def get_rdb_search_results(query: str) -> list:
    try:
        conn = sqlite3.connect('medical_records.db')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.name, d.diagnosis 
            FROM patients p 
            JOIN diagnoses d ON p.id = d.patient_id 
            WHERE d.diagnosis LIKE ?
        """, (f"%{query}%",))
        results = cursor.fetchall()
        conn.close()
        return [f"{name}: {diagnosis}" for name, diagnosis in results]
    except Exception as e:
        st.error(f"据库搜索错误: {str(e)}")
        return []

def generate_graph_query(query: str) -> dict:
    """使用LLM生成图数据库查询条件"""
    try:
        st.write("开始创建OpenAI客户端...")
        client = OpenAI(
            api_key="sk-1pUmQlsIkgla3CuvKTgCrzDZ3r0pBxO608YJvIHCN18lvOrn",
            base_url="https://api.chatanywhere.tech/v1",
            timeout=60
        )
        st.write("✅ OpenAI客户端创建成功")
        
        # 读取图数据库的结构信息
        G = nx.read_gexf("medical_graph.gexf")
        
        # 获取图的基本信息
        graph_info = {
            "node_types": list(set(nx.get_node_attributes(G, 'type').values())),
            "relationships": list(set(nx.get_edge_attributes(G, 'relationship').values())),
            "nodes_sample": {
                node: data for node, data in list(G.nodes(data=True))[:5]
            },
            "edges_sample": {
                f"{u}->{v}": data for u, v, data in list(G.edges(data=True))[:5]
            }
        }
        
        prompt = f"""请根据问题和图数据库结构生成图数据库查询条件。

图数据库结构：
节点类型: {graph_info["node_types"]}
关系类型: {graph_info["relationships"]}
节点示例: {json.dumps(graph_info["nodes_sample"], ensure_ascii=False, indent=2)}
关系示例: {json.dumps(graph_info["edges_sample"], ensure_ascii=False, indent=2)}

用户问题：{query}

请生一个包含查询条件的字典，示例格式：

1. 查询患者的主诉：
{{
    "start_node": {{"type": "patient", "name": "从问题中提取的患者姓名"}},
    "relationship": "complains_of",
    "end_node": {{"type": "chief_complaint"}},
    "return": ["end_node.content"]
}}

2. 查询患者的生命体征：
{{
    "start_node": {{"type": "patient", "name": "从问题中提取的患者姓名"}},
    "relationship": "has_vital_sign",
    "end_node": {{"type": "vital_sign"}},
    "return": ["end_node.name", "end_node.value"]
}}

3. 查询患者的生化指标：
{{
    "start_node": {{"type": "patient", "name": "从问题中提取的患者姓名"}},
    "relationship": "has_test_result",
    "end_node": {{"type": "biochemical_test"}},
    "return": ["end_node.name", "end_node.value"]
}}

注意：
1. 从用户问题中提取正确的患者姓名
2. 使用正确的节点类型和关系类型
3. 使用正确的属性名称
4. 指定要返回的具体属性

请直接返回查询条件的JSON字符串，不要包含任何其他内容。"""

        st.write("🔄 正在调用OpenAI API...")
        response = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {
                    "role": "system", 
                    "content": "你是一个图数据库查询专家。根据实际的数库结构生成精确的查询条件。"
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.1
        )
        st.write("✅ OpenAI API调用成功")
        
        # 获取响应文本并清理
        query_str = response.choices[0].message.content.strip()
        st.write("原始响应文本：", query_str)
        
        if query_str.startswith('```json'):
            query_str = query_str[7:]
        if query_str.endswith('```'):
            query_str = query_str[:-3]
        query_str = query_str.strip()
        
        st.write("清理后的JSON字符串：", query_str)
        
        # 显示生成的查询条件
        st.write("生成的图数据库查询条件：")
        st.code(query_str, language="json")
        
        return json.loads(query_str)
        
    except Exception as e:
        st.error(f"生成图数据库查询条件错误: {str(e)}")
        st.error(f"错误类型: {type(e).__name__}")
        st.error(f"错误堆栈: {traceback.format_exc()}")
        return None

def get_graph_search_results(query: str) -> list:
    """从图数据库中搜索相关信息"""
    try:
        # 使用LLM生成查询条件
        query_obj = generate_graph_query(query)
        if not query_obj:
            return []
        
        G = nx.read_gexf("medical_graph.gexf")
        results = []
        
        # 根据查询条件执行搜索
        start_nodes = [node for node, data in G.nodes(data=True)
                      if data.get('type') == query_obj["start_node"]["type"] and 
                         node == query_obj["start_node"]["name"]]
        
        for start_node in start_nodes:
            # 获取所有邻居节点
            for neighbor in G.neighbors(start_node):
                edge_data = G.get_edge_data(start_node, neighbor)
                neighbor_data = G.nodes[neighbor]
                
                # 检查关系类型和终点节点类型是否匹配
                if (edge_data.get("relationship") == query_obj["relationship"] and
                    neighbor_data.get('type') == query_obj["end_node"]["type"]):
                    
                    # 构建结果
                    result = []
                    for attr in query_obj["return"]:
                        node_type, attr_name = attr.split(".")
                        if node_type == "end_node":
                            result.append(f"{attr_name}: {neighbor_data.get(attr_name, '')}")
                    
                    results.append(f"{start_node} -> {edge_data.get('relationship')} -> {' | '.join(result)}")
        
        return results
    except Exception as e:
        st.error(f"图数据库搜索错误: {str(e)}")
        return []

def generate_mongodb_query(query: str) -> dict:
    """使用LLM生成MongoDB查询条件和投影"""
    try:
        st.write("开始创建OpenAI客端...")
        client = OpenAI(
            api_key="sk-1pUmQlsIkgla3CuvKTgCrzDZ3r0pBxO608YJvIHCN18lvOrn",
            base_url="https://api.chatanywhere.tech/v1",
            timeout=60
        )
        st.write("✅ OpenAI客户端创建成功")
        
        # 读取示例JSON结构
        st.write("读取JSON模板...")
        with open('get_inf.json', 'r', encoding='utf-8') as f:
            schema = json.load(f)
        st.write("✅ JSON模板读取成功")
        
        prompt = f"""你是一个MongoDB查询专家。请根据以下问题和数结构生成MongoDB查询条件。

据结构：
{json.dumps(schema, ensure_ascii=False, indent=2)}

用户问题：{query}

请生成一个MongoDB查询对象，必须包含query和projection两字段。示例格式：

{{
    "query": {{"患者姓名": "马某某"}},
    "projection": {{"患者姓名": 1, "生命体征.血压": 1, "_id": 0}}
}}

注意：
1. 必须返回合法的JSON格式
2. 必须包含query和projection两个字段
3. 使用双引号而不是单引
4. 字段名必须与数据结构中的完全匹配
5. 不要返回任何其他内容，只返回JSON对象

请直接返回查询对象，不要包含任何解释或说明。"""

        st.write("🔄 正在调用OpenAI API...")
        response = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",  # 修改这里
            messages=[
                {
                    "role": "system", 
                    "content": "你是一个MongoDB查询专家。请只返回JSON格式的查询对象，不要返回任何其他内容。"
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.1
        )
        st.write("✅ OpenAI API调用成")
        
        # 获取响应文本并清理
        query_str = response.choices[0].message.content.strip()
        st.write("原始响应文本：", query_str)
        
        # 清理JSON字符串
        if query_str.startswith('```json'):
            query_str = query_str[7:]
        if query_str.endswith('```'):
            query_str = query_str[:-3]
        query_str = query_str.strip()
        
        st.write("清理后的JSON字符串：", query_str)
        
        # 显示生成的查询条件
        st.write("生成的MongoDB查询条件：")
        st.code(query_str, language="json")
        
        return json.loads(query_str)
        
    except Exception as e:
        st.error(f"生成查询条件错误: {str(e)}")
        st.error(f"错误类型: {type(e).__name__}")
        st.error(f"错误堆栈: {traceback.format_exc()}")
        return None

def get_structured_search_results(query: str) -> list:
    """从MongoDB中搜索相关信息"""
    try:
        db = get_mongodb_connection()
        if db is None:
            return []
        
        # 使用LLM生成查询条件和投影
        query_obj = generate_mongodb_query(query)
        if not query_obj:
            return []
        
        # 执行查询，使用生成的查询条件和投影
        docs = list(db.patients.find(query_obj["query"], query_obj["projection"]))
        st.write(f"找到 {len(docs)} 条记录")
        
        results = []
        for doc in docs:
            # 直接返回查询到的字段内容
            for field, value in doc.items():
                if field != '_id' and field != 'metadata':  # 排除特殊字段
                    if isinstance(value, list):
                        # 处理数组类型的字段
                        results.append(f"患者 {doc.get('患者姓名', '未知')} 的{field}：")
                        for item in value:
                            results.append(f"- {item}")
                    elif isinstance(value, dict):
                        # 处理字典类型的字段
                        results.append(f"患者 {doc.get('患者姓名', '未知')} 的{field}：")
                        for k, v in value.items():
                            results.append(f"- {k}: {v}")
                    else:
                        # 处理普通字段
                        results.append(f"患者 {doc.get('患姓名', '未知')} 的{field}是: {value}")
        
        return results
    except Exception as e:
        st.error(f"MongoDB搜索错误: {str(e)}")
        return []

# 修LLM响应函数
def get_llm_response(query: str, search_results: dict) -> str:
    try:
        client = OpenAI(
            api_key="sk-2D0EZSwcWUcD4c2K59353b7214854bBd8f35Ac131564EfBa",
            base_url="https://free.gpt.ge/v1"
        )
        
        prompt = f"""请基于以下相关内容回答问题：

用户问题: {query}

相内容:
{search_results}

请注意：
1. 只使用提供的相关内容回答问题
2. 如果相关内容中没有答案，请明确说明
3. 不要添加任何不在相关内容中的信息
4. 保持回答的准确性和客观性"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "你是一个专业的医疗助手，擅长解读医疗信息并提供准确的解答。"
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.1
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"LLM响应错误: {str(e)}")
        return "抱歉，生成回答时出现错误。"

# 页面标题和开发者信息
st.title("🏥 医疗 RAG 系统")
st.markdown("""
<div style='text-align: right; color: gray; padding: 0px 0px 20px 0px;'>
    <p>Developed by Huaiyuan Tan</p>
</div>
""", unsafe_allow_html=True)

# 修改侧边栏部分
with st.sidebar:
    st.header("系统设置")
    
    # 显示数据状态
    if check_data_initialized():
        st.success("✅ 数据库中已有数据")
    else:
        st.warning("⚠️ 数据库中暂无数据")
    
    # 数据导入部分
    st.subheader("数据导入")
    import_db = st.selectbox(
        "选择要导入的数据库",
        ["向量数据库", "MongoDB", "图数据库", "全部导入"]
    )
    
    if import_db in ["向量数据库", "MongoDB", "全部导入"]:
        uploaded_files = st.file_uploader(
            "上传病历PDF文件（可多选）", 
            type=['pdf'],
            accept_multiple_files=True  # 启用多文件上传
        )
        
        if uploaded_files:
            st.write(f"已选择 {len(uploaded_files)} 个文件：")
            for file in uploaded_files:
                st.write(f"- {file.name}")
            
            if st.button("导入数据"):
                with st.spinner("正在导入数据..."):
                    success = True
                    
                    for uploaded_file in uploaded_files:
                        st.write(f"正在处理文件：{uploaded_file.name}")
                        
                        # 读取PDF内容
                        with pdfplumber.open(uploaded_file) as pdf:
                            pdf_content = ""
                            for page in pdf.pages:
                                pdf_content += page.extract_text()
                        
                        if import_db in ["向量数据库", "全部导入"]:
                            st.write(f"开始导入向量数据库：{uploaded_file.name}")
                            try:
                                # 使用文件名作为唯一标识
                                file_name = uploaded_file.name.replace('.pdf', '')
                                chunks, index = vectorize_document(pdf_content, file_name)
                                if chunks and index:
                                    st.success(f"✅ 向量数据库导入成功，文档 '{file_name}' 共生成 {len(chunks)} 个文档块")
                                else:
                                    st.error(f"❌ 文档 '{file_name}' 导入失败")
                                    success = False
                            except Exception as e:
                                st.error(f"向量数据库导入失败: {str(e)}")
                                success = False
                        
                        if import_db in ["MongoDB", "全部导入"]:
                            st.write(f"开始导入MongoDB：{uploaded_file.name}")
                            # [MongoDB导入代码保持不变...]
                    
                    if success:
                        st.success(f"✅ 所有件导入完成")
                        st.rerun()
                    else:
                        st.error("部分文件导入失败，请检查错误信息")
        else:
            st.warning("请先上传PDF文件")
    
    elif import_db == "图数据库":
        if st.button("从MongoDB构建图数据库"):
            # [图数据库构建代码保持不变...]
            pass

# 在侧边栏添加数据库内容看功能
with st.sidebar:
    st.header("数据库内容查看")
    view_db = st.selectbox(
        "选择要查看的数据库",
        ["向量数据库", "MongoDB", "图数据库"]
    )
    
    if st.button("查看数据"):
        if view_db == "向量数据库":
            st.write("📚 向量数据库内容：")
            try:
                # 初始化 Pinecone
                index = init_pinecone()
                if index:
                    # 获取所有向量
                    stats = index.describe_index_stats()
                    total_vectors = stats.total_vector_count
                    
                    if total_vectors > 0:
                        st.write(f"总向量数量：{total_vectors}")
                        
                        # 获取所有向量的元数据
                        # 使用空查询获取所有向量
                        results = index.query(
                            vector=[0] * 384,  # 使用零向量作为查询向量
                            top_k=total_vectors,  # 获取所有向量
                            include_metadata=True
                        )
                        
                        # 按文件名组织显示
                        files = {}
                        for match in results['matches']:
                            file_name = match['metadata'].get('original_file_name', '未知文件')
                            if file_name not in files:
                                files[file_name] = []
                            files[file_name].append(match['metadata'].get('text', ''))
                        
                        # 显示每个文件的内容
                        for file_name, chunks in files.items():
                            with st.expander(f"文档：{file_name}"):
                                for i, chunk in enumerate(chunks):
                                    st.write(f"片段 {i+1}:")
                                    st.info(chunk)
                    else:
                        st.warning("向量数据库中暂无数据")
            except Exception as e:
                st.error(f"读取向量数据库错误: {str(e)}")
                st.warning("向量数据库中暂无数据")
        
        elif view_db == "MongoDB":
            st.write("📊 MongoDB内容：")
            db = get_mongodb_connection()
            if db is not None:
                try:
                    docs = list(db.patients.find())
                    if docs:
                        for doc in docs:
                            with st.expander(f"患者：{doc.get('患者姓名', '未知患者')}"):
                                # 基本信息
                                st.write("👤 基本信息：")
                                for key in ['性别', '年龄', '民族', '职业', '婚姻状况', '入院日期', '出院日期']:
                                    if key in doc:
                                        st.write(f"{key}: {doc[key]}")
                                
                                # 主诉和现病史
                                if '主诉' in doc:
                                    st.write("🔍 主诉：", doc['主诉'])
                                if '现病史' in doc:
                                    st.write("📝 现病史：")
                                    for item in doc['现病史']:
                                        st.write(f"- {item}")
                                
                                # 诊断信息
                                if '入院诊断' in doc:
                                    st.write("🏥 入院诊断：")
                                    for diag in doc['入院诊断']:
                                        st.write(f"- {diag}")
                                if '出院诊断' in doc:
                                    st.write("🏥 出院诊断：")
                                    for diag in doc['出院诊断']:
                                        st.write(f"- {diag}")
                                
                                # 生命体征
                                if '生命体征' in doc:
                                    st.write("💓 生命体征：")
                                    for key, value in doc['生命体征'].items():
                                        st.write(f"{key}: {value}")
                                
                                # 生化指标
                                if '生化指标' in doc:
                                    st.write("🔬 生化指标：")
                                    for key, value in doc['生化指标'].items():
                                        st.write(f"{key}: {value}")
                                
                                # 治疗经过
                                if '诊疗经过' in doc:
                                    st.write("💊 诊疗经过：", doc['诊疗经过'])
                                
                                # 出院医嘱
                                if '出院医嘱' in doc:
                                    st.write("📋 出院医嘱：")
                                    for advice in doc['出院医嘱']:
                                        st.write(f"- {advice}")
                    else:
                        st.warning("MongoDB中暂无数据")
                except Exception as e:
                    st.error(f"查询MongoDB错误: {str(e)}")
                    st.error(f"错误类型: {type(e).__name__}")
                    st.error(f"错误堆栈: {traceback.format_exc()}")
            else:
                st.error("MongoDB连接失败")
        
        elif view_db == "图数据库":
            st.write("🕸️ 图数据库内容：")
            try:
                G = nx.read_gexf("medical_graph.gexf")
                
                # 显示节点信息
                with st.expander("节点信息"):
                    st.write("总节点数：", len(G.nodes))
                    for node, data in G.nodes(data=True):
                        st.write(f"节点：{node}")
                        st.write(f"类型：{data.get('type', '未知')}")
                        for key, value in data.items():
                            if key != 'type':
                                st.write(f"{key}: {value}")
                        st.write("---")
                
                # 显示关系信息
                with st.expander("关系信息"):
                    st.write("总关系数：", len(G.edges))
                    for u, v, data in G.edges(data=True):
                        st.write(f"关系：{u} -> {v}")
                        st.write(f"类型：{data.get('relationship', '未知')}")
                        for key, value in data.items():
                            if key != 'relationship':
                                st.write(f"{key}: {value}")
                        st.write("---")
            except Exception as e:
                st.error(f"读取图数据库错误: {str(e)}")
                st.warning("图数据库中暂无数据")

# 使用表单包装搜索部分
search_form = st.form(key="search_form", clear_on_submit=False)
with search_form:
    # 检索方式选择
    search_type = st.selectbox(
        "选择检索方式",
        ["向量数据库", "MongoDB", "图数据库", "混合检索"],
        help="选择单一数据库检索或混合检索模式"
    )
    
    # 查
    query = st.text_input("请输入的问题：")
    
    # 提交钮
    submit_button = st.form_submit_button("搜索并生成答案")

# 在表单外处理搜索结果
if submit_button:
    if not check_data_initialized():
        st.warning("数据库中没有数据，请先导入数据！")
    else:
        with st.spinner("正在处理..."):
            search_results = {}
            
            # 根据选择的检索方式执行相应的搜索
            if search_type == "向量数据库":
                # 使用 vector_store.py 中的函数进行向量搜索
                from vector_store import get_vector_search_results
                vector_results = get_vector_search_results(query)
                search_results = {
                    "vector": vector_results,
                    "structured": [],
                    "graph": []
                }
                # 显示结果
                st.write("🔍 向量搜索结果:")
                with st.expander("向量搜索详情", expanded=True):
                    if vector_results:
                        for result in vector_results:
                            st.info(result)
                    else:
                        st.write("未找到相关内容")
                        st.write("可能的原因：")
                        st.write("1. 相似度分数低于阈值")
                        st.write("2. 查询向量与文档向量差异较大")
                        st.write("3. 数据库中没有相关内容")
                    
            elif search_type == "MongoDB":
                mongodb_results = get_structured_search_results(query)
                search_results = {
                    "vector": [],
                    "structured": mongodb_results,
                    "graph": []
                }
                # 显示结果
                st.write("📊 MongoDB搜索结果:")
                if mongodb_results:
                    for result in mongodb_results:
                        st.info(result)
                else:
                    st.write("未找到相关内容")
                    
            elif search_type == "图数据库":
                graph_results = get_graph_search_results(query)
                search_results = {
                    "vector": [],
                    "structured": [],
                    "graph": graph_results
                }
                # 显示结果
                st.write("🕸️ 图数据库搜索结果:")
                if graph_results:
                    for result in graph_results:
                        st.info(result)
                else:
                    st.write("未找到相关内容")
                    
            else:  # 混合检索
                # 使用 vector_store.py 中的函数进行向量搜索
                from vector_store import get_vector_search_results
                vector_results = get_vector_search_results(query)
                mongodb_results = get_structured_search_results(query)
                graph_results = get_graph_search_results(query)
                
                search_results = {
                    "vector": vector_results,
                    "structured": mongodb_results,
                    "graph": graph_results
                }
                
                # 使用列布局显示所有结果
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write("🔍 向量搜索结果:")
                    if vector_results:
                        # 使用 LLM 生成向量搜索结果的总结
                        try:
                            client = OpenAI(
                                api_key="sk-1pUmQlsIkgla3CuvKTgCrzDZ3r0pBxO608YJvIHCN18lvOrn",
                                base_url="https://api.chatanywhere.tech/v1",
                                timeout=60
                            )
                            
                            # 准备提示词
                            prompt = f"""请根据以下搜索结果回答问题：
                            
                            问题: {query}
                            
                            搜索结果:
                            {vector_results}
                            
                            请简洁地总结相关信息。如果没有找到相关信息，请直接说明。"""
                            
                            response = client.chat.completions.create(
                                model="gpt-4o-mini-2024-07-18",
                                messages=[
                                    {
                                        "role": "system", 
                                        "content": "你是一个专业的医疗助手，请简洁地总结搜索结果。"
                                    },
                                    {
                                        "role": "user", 
                                        "content": prompt
                                    }
                                ],
                                temperature=0.1
                            )
                            st.info(response.choices[0].message.content)
                        except Exception as e:
                            st.error(f"生成向量搜索总结失败: {str(e)}")
                            st.write("未找到相关内容")
                    else:
                        st.write("未找到相关内容")
                
                with col2:
                    st.write("📊 MongoDB搜索结果:")
                    if mongodb_results:
                        for result in mongodb_results:
                            st.info(result)
                    else:
                        st.write("未找到相关内容")
                
                with col3:
                    st.write("🕸️ 图数据库搜索结果:")
                    if graph_results:
                        for result in graph_results:
                            st.info(result)
                    else:
                        st.write("未找到相关内容")
            
            # 使用LLM生成最终答案
            st.write("🤖 AI 分析与回答:")
            with st.spinner("AI正在分析搜索结果..."):
                max_retries = 3  # 最大重试次数
                retry_count = 0
                
                while retry_count < max_retries:
                    try:
                        # 创建OpenAI客户端，使用新的配置
                        client = OpenAI(
                            api_key="sk-1pUmQlsIkgla3CuvKTgCrzDZ3r0pBxO608YJvIHCN18lvOrn",
                            base_url="https://api.chatanywhere.tech/v1",
                            timeout=60  # 增加超时时间
                        )
                        
                        # 准备提示词
                        prompt = f"""请基于以下相关内容回答问题：
                        
                        用户问题: {query}
                        
                        相关内容:
                        {search_results}
                        
                        请注意：
                        1. 只使用提供的相关内容回答问题
                        2. 如果相关内容中没有答案，请明确说明
                        3. 不要添加任何不在相关内容中的信息
                        4. 保持回答的准确性和客观性"""
                        
                        response = client.chat.completions.create(
                            model="gpt-4o-mini-2024-07-18",  # 使用相同的模型
                            messages=[
                                {
                                    "role": "system", 
                                    "content": "你是一个专业的医疗助手，擅长解读医疗信息并提供准确的解答。"
                                },
                                {
                                    "role": "user", 
                                    "content": prompt
                                }
                            ],
                            temperature=0.1
                        )
                        
                        answer = response.choices[0].message.content
                        st.success(answer)
                        
                        # 更新对话历史
                        st.session_state.chat_history.append({
                            "query": query,
                            "response": answer,
                            "search_results": search_results,
                            "search_type": search_type
                        })
                        
                        break  # 成功后跳出循环
                        
                    except Exception as e:
                        retry_count += 1
                        if retry_count == max_retries:
                            st.error(f"生成回答失败，已重试 {max_retries} 次")
                            st.error(f"错误类型: {type(e).__name__}")
                            st.error(f"错误信息: {str(e)}")
                            # 提供一个基本的回答
                            basic_answer = "抱歉，当前无法连接到AI服务。根据搜索结果，"
                            if search_results.get('structured'):
                                basic_answer += "找到以下相关信息：\n" + "\n".join(search_results['structured'])
                            else:
                                basic_answer += "未找到相关信息。"
                            st.info(basic_answer)
                        else:
                            st.warning(f"第 {retry_count} 次尝试失败，正在重试...")
                            time.sleep(2)  # 等待2秒后重试

# 修改对话历史显示部分
st.subheader("💬 对话历史")
for chat in st.session_state.chat_history:
    with st.expander(f"问题：{chat['query'][:50]}..."):
        st.write("🗣️ 用户问题：")
        st.info(chat["query"])
        
        st.write(f" 检索方式：{chat['search_type']}")
        
        # 显示搜索结果
        if "search_results" in chat:
            if chat['search_type'] == "混合检索":
                tabs = st.tabs(["向量搜索", "MongoDB", "图数据库"])
                with tabs[0]:
                    if "vector" in chat["search_results"]:
                        for result in chat["search_results"]["vector"]:
                            st.write(result)
                    else:
                        st.write("无向量搜索结果")
                with tabs[1]:
                    if "structured" in chat["search_results"]:
                        for result in chat["search_results"]["structured"]:
                            st.write(result)
                    else:
                        st.write("无MongoDB搜索结果")
                with tabs[2]:
                    if "graph" in chat["search_results"]:
                        for result in chat["search_results"]["graph"]:
                            st.write(result)
                    else:
                        st.write("无图数据库搜索结果")
            else:
                # 显示单一数据库的结果
                key_map = {
                    "向量数据库": "vector",
                    "MongoDB": "structured",
                    "图数据库": "graph"
                }
                key = key_map.get(chat['search_type'])
                if key and key in chat["search_results"]:
                    for result in chat["search_results"][key]:
                        st.write(result)
                else:
                    st.write("无搜索结果")
        
        st.write("🤖 AI 回答：")
        st.success(chat["response"])

def setup_graph(parser):
    G = nx.Graph()
    
    # 添加患者节点（带更多属性）
    G.add_node(parser.parsed_data['name'], 
               type="patient",
               age=parser.parsed_data['age'],
               gender=parser.parsed_data['gender'],
               chief_complaint=parser.parsed_data['chief_complaint'])
    
    # 添加症状节点（带详细信息）
    for symptom in parser.parsed_data['symptoms']:
        symptom_id = f"{symptom['symptom']}_{parser.parsed_data['name']}"
        G.add_node(symptom_id, 
                  type="symptom",
                  description=symptom['description'])
        G.add_edge(parser.parsed_data['name'], symptom_id, 
                  relationship="has_symptom",
                  onset_date=symptom['onset_date'])
    
    # 添加检查结果节点（带异常标记）
    for exam_type, exam_data in parser.parsed_data['examinations'].items():
        exam_id = f"{exam_type}_{parser.parsed_data['name']}"
        G.add_node(exam_id,
                  type="examination",
                  result=exam_data['result'],
                  abnormal=exam_data['abnormal'])
        G.add_edge(parser.parsed_data['name'], exam_id,
                  relationship="underwent")
        
        # 添加检结果与症状的关联
        for symptom in parser.parsed_data['symptoms']:
            symptom_id = f"{symptom['symptom']}_{parser.parsed_data['name']}"
            if any(word in exam_data['description'] for word in symptom['symptom'].split()):
                G.add_edge(exam_id, symptom_id,
                          relationship="confirms")
    
    # 添加治疗节点
    for treatment in parser.parsed_data['treatments']:
        treatment_id = f"{treatment['medication']}_{parser.parsed_data['name']}"
        G.add_node(treatment_id,
                  type="treatment",
                  medication=treatment['medication'],
                  dosage=treatment['dosage'])
        G.add_edge(parser.parsed_data['name'], treatment_id,
                  relationship="receives")

def clean_vector_store():
    """清理向量数据库"""
    try:
        st.session_state.file_chunks = {}
        st.session_state.file_indices = {}
        st.success("✅ 向量数据库已清空")
        return True
    except Exception as e:
        st.error(f"清理向量数据库错误: {str(e)}")
        return False

def clean_mongodb_data():
    """清理MongoDB中的所有数据"""
    try:
        db = get_mongodb_connection()
        if db is not None:
            result = db.patients.delete_many({})
            st.write(f"已删除所有记录（共 {result.deleted_count} 条）")
            st.success("✅ MongoDB已完全清空")
            
            if 'mongodb_records' in st.session_state:
                st.session_state.mongodb_records = []
            if 'structured_data' in st.session_state:
                st.session_state.structured_data = {}
            
            return True
    except Exception as e:
        st.error(f"清理MongoDB错误: {str(e)}")
        return False

def clean_graph_data():
    """清理图数据库"""
    try:
        if os.path.exists("medical_graph.gexf"):
            os.remove("medical_graph.gexf")
        st.success("✅ 图数据库已清空")
        return True
    except Exception as e:
        st.error(f"清理图数据库错误: {str(e)}")
        return False

# 在侧边栏添加清理按钮
with st.sidebar:
    # 选择要清空的数据库
    clean_db = st.selectbox(
        "选择要清空的数据库",
        ["向量数据库", "MongoDB", "图数据库", "全部数据库"]
    )
    
    if st.button("清空数据"):
        if clean_db == "向量数据库":
            if clean_vector_store():
                st.rerun()
        elif clean_db == "MongoDB":
            if clean_mongodb_data():
                st.rerun()
        elif clean_db == "图数据库":
            if clean_graph_data():
                st.rerun()
        else:  # 清空所有数据库
            success = True
            if not clean_vector_store():
                success = False
            if not clean_mongodb_data():
                success = False
            if not clean_graph_data():
                success = False
            
            if success:
                st.success("✅ 所有数据库已清空！")
                st.rerun()
            else:
                st.error("部分数库清空失败！")