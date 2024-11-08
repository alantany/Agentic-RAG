import streamlit as st
import importlib
import subprocess
import sys
import sqlite3
import json
from openai import OpenAI
import networkx as nx
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import pickle
import os
import pdfplumber
from datetime import datetime
import re

# 设置页面配置
st.set_page_config(page_title="医疗 RAG 系统", layout="wide")

# 初始化会话状态
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'data_initialized' not in st.session_state:
    st.session_state.data_initialized = False

# 向量存储类
class VectorStore:
    def __init__(self):
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.dimension = 384
        self.index = faiss.IndexFlatL2(self.dimension)
        self.documents = []
        if os.path.exists('vector_store.pkl'):
            self.load_store()
    
    def text_to_vector(self, text: str):
        return self.model.encode(text)
    
    def add_document(self, doc: dict):
        vector = self.text_to_vector(doc["content"])
        self.index.add(np.array([vector], dtype=np.float32))
        self.documents.append(doc)
        self.save_store()
    
    def search(self, query: str, limit: int = 3):
        query_vector = self.text_to_vector(query)
        D, I = self.index.search(np.array([query_vector], dtype=np.float32), limit)
        results = []
        for idx in I[0]:
            if idx < len(self.documents):
                results.append(self.documents[idx])
        return results
    
    def save_store(self):
        store_data = {
            'index': faiss.serialize_index(self.index),
            'documents': self.documents
        }
        with open('vector_store.pkl', 'wb') as f:
            pickle.dump(store_data, f)
    
    def load_store(self):
        try:
            with open('vector_store.pkl', 'rb') as f:
                store_data = pickle.load(f)
                self.index = faiss.deserialize_index(store_data['index'])
                self.documents = store_data['documents']
        except Exception as e:
            print(f"加载向量存储失败: {str(e)}")

# PDF解析类
class MedicalRecordParser:
    def __init__(self, pdf_content):
        self.content = pdf_content
        self.parsed_data = self._parse_content()
    
    def _parse_content(self):
        data = {}
        try:
            # 提取基本信息
            data['name'] = re.search(r'姓名\s*([\u4e00-\u9fa5]+)', self.content).group(1)
            data['gender'] = re.search(r'性别\s*([\u4e00-\u9fa5]+)', self.content).group(1)
            data['age'] = int(re.search(r'年龄\s*(\d+)岁', self.content).group(1))
            data['ethnicity'] = re.search(r'民族\s*([\u4e00-\u9fa5]+)', self.content).group(1)
            data['marriage'] = re.search(r'婚姻\s*([\u4e00-\u9fa5]+)', self.content).group(1)
            
            # 提取日期
            admission_date = re.search(r'住院日期\s*:(\d{4}\s*年\d{1,2}月\d{1,2}日)', self.content).group(1)
            data['admission_date'] = datetime.strptime(admission_date.replace(' ', ''), '%Y年%m月%d日').strftime('%Y-%m-%d')
            
            # 提取诊断
            diagnoses = []
            if match := re.search(r'出院诊断\s*:(.*?)出院时情况', self.content, re.DOTALL):
                diagnoses_text = match.group(1)
                diagnoses = [d.strip() for d in diagnoses_text.split('\n') if d.strip()]
            data['diagnoses'] = diagnoses
            
            # 提取症状
            symptoms = []
            if match := re.search(r'主\s*诉\s*:(.*?)入院时情况', self.content, re.DOTALL):
                symptoms_text = match.group(1)
                symptoms = [s.strip() for s in re.findall(r'[，。、](.*?)[，。、]', symptoms_text)]
            data['symptoms'] = symptoms
            
            # 提取检查结果
            examinations = {}
            exam_patterns = {
                '头颅MRI': r'头颅\s*MRI\s*提示(.*?)。',
                '动态心电图': r'动态心电图\s*:(.*?)。',
                '眼震电图': r'眼震电图提示(.*?)。'
            }
            for exam, pattern in exam_patterns.items():
                if match := re.search(pattern, self.content):
                    examinations[exam] = match.group(1).strip()
            data['examinations'] = examinations
            
            return data
        except Exception as e:
            st.error(f"解析PDF内容错误: {str(e)}")
            return {}

# 数据导入函数
def import_medical_data(pdf_content):
    parser = MedicalRecordParser(pdf_content)
    
    # 导入向量数据库
    vector_store = VectorStore()
    document = {
        "title": f"{parser.parsed_data['name']}的病历",
        "content": pdf_content,
        "type": "病历记录",
        "date": parser.parsed_data['admission_date']
    }
    vector_store.add_document(document)
    
    # 导入关系数据库
    conn = sqlite3.connect('medical_records.db')
    cursor = conn.cursor()
    
    # 创建表（如果不存在）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, gender TEXT, age INTEGER,
        ethnicity TEXT, marriage TEXT,
        admission_date DATE, discharge_date DATE
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS diagnoses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER, diagnosis TEXT,
        diagnosis_type TEXT,
        FOREIGN KEY (patient_id) REFERENCES patients(id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS examinations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER, exam_type TEXT,
        exam_result TEXT, exam_date DATE,
        FOREIGN KEY (patient_id) REFERENCES patients(id)
    )
    ''')
    
    # 插入数据
    cursor.execute('''
    INSERT INTO patients (name, gender, age, ethnicity, marriage, admission_date)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        parser.parsed_data['name'],
        parser.parsed_data['gender'],
        parser.parsed_data['age'],
        parser.parsed_data['ethnicity'],
        parser.parsed_data['marriage'],
        parser.parsed_data['admission_date']
    ))
    
    patient_id = cursor.lastrowid
    
    for diagnosis in parser.parsed_data['diagnoses']:
        cursor.execute('''
        INSERT INTO diagnoses (patient_id, diagnosis, diagnosis_type)
        VALUES (?, ?, ?)
        ''', (patient_id, diagnosis, '出院诊断'))
    
    for exam_type, result in parser.parsed_data['examinations'].items():
        cursor.execute('''
        INSERT INTO examinations (patient_id, exam_type, exam_result, exam_date)
        VALUES (?, ?, ?, ?)
        ''', (patient_id, exam_type, result, parser.parsed_data['admission_date']))
    
    conn.commit()
    conn.close()
    
    # 导入图数据库
    G = nx.Graph()
    
    # 添加患者节点
    G.add_node(parser.parsed_data['name'],
               type="patient",
               age=parser.parsed_data['age'],
               gender=parser.parsed_data['gender'])
    
    # 添加诊断节点和关系
    for diagnosis in parser.parsed_data['diagnoses']:
        G.add_node(diagnosis, type="diagnosis")
        G.add_edge(parser.parsed_data['name'], diagnosis, relationship="diagnosed_with")
    
    # 添加症状节点和关系
    for symptom in parser.parsed_data['symptoms']:
        G.add_node(symptom, type="symptom")
        G.add_edge(parser.parsed_data['name'], symptom, relationship="has_symptom")
    
    # 添加检查结果节点和关系
    for exam_type, result in parser.parsed_data['examinations'].items():
        G.add_node(exam_type, type="examination", result=result)
        G.add_edge(parser.parsed_data['name'], exam_type, relationship="underwent")
    
    nx.write_gexf(G, "medical_graph.gexf")
    
    return True

# 搜索函数
def get_vector_search_results(query: str) -> list:
    try:
        vector_store = VectorStore()
        results = vector_store.search(query)
        return [f"{item['title']}: {item['content']}" for item in results]
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
        st.error(f"数据库搜索错误: {str(e)}")
        return []

def get_graph_search_results(query: str) -> list:
    try:
        G = nx.read_gexf("medical_graph.gexf")
        results = []
        for node in G.nodes(data=True):
            if query.lower() in str(node[1]).lower():
                neighbors = list(G.neighbors(node[0]))
                results.append(f"{node[0]} 相关: {neighbors}")
        return results[:3]
    except Exception as e:
        st.error(f"图数据库搜索错误: {str(e)}")
        return []

def get_llm_response(query: str, search_results: dict) -> str:
    try:
        client = OpenAI(
            api_key="sk-2D0EZSwcWUcD4c2K59353b7214854bBd8f35Ac131564EfBa",
            base_url="https://free.gpt.ge/v1"
        )
        
        prompt = f"""
        查询: {query}
        搜索结果:
        向量搜索: {search_results['vector']}
        关系数据库: {search_results['rdb']}
        图数据库: {search_results['graph']}
        
        请基于以上信息生成回答。
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"LLM响应错误: {str(e)}")
        return "抱歉，生成回答时出现错误。"

# 主界面
st.title("🏥 医疗 RAG 系统")

# 侧边栏配置
with st.sidebar:
    st.header("系统配置")
    
    # 数据导入部分
    st.subheader("数据导入")
    uploaded_file = st.file_uploader("上传病历PDF文件", type=['pdf'])
    
    if uploaded_file is not None:
        if st.button("导入数据"):
            with st.spinner("正在导入数据..."):
                try:
                    # 使用pdfplumber读取PDF内容
                    with pdfplumber.open(uploaded_file) as pdf:
                        pdf_content = ""
                        for page in pdf.pages:
                            pdf_content += page.extract_text()
                    
                    # 导入数据
                    if import_medical_data(pdf_content):
                        st.success("数据导入成功！")
                        st.session_state.data_initialized = True
                    else:
                        st.error("数据导入失败！")
                except Exception as e:
                    st.error(f"PDF读取错误: {str(e)}")
    
    # 搜索方法选择
    st.subheader("搜索配置")
    search_methods = st.multiselect(
        "选择搜索方法",
        ["向量搜索", "关系数据库", "图数据库"],
        default=["向量搜索", "关系数据库", "图数据库"]
    )

# 主要内容区域
query = st.text_input("请输入您的问题：")

if st.button("搜索并生成"):
    if not st.session_state.data_initialized:
        st.warning("请先导入数据！")
    else:
        with st.spinner("正在处理..."):
            # 执行搜索
            search_results = {
                "vector": get_vector_search_results(query) if "向量搜索" in search_methods else [],
                "rdb": get_rdb_search_results(query) if "关系数据库" in search_methods else [],
                "graph": get_graph_search_results(query) if "图数据库" in search_methods else []
            }
            
            # 获取LLM响应
            response = get_llm_response(query, search_results)
            
            # 更新对话历史
            st.session_state.chat_history.append({"query": query, "response": response})

# 显示对话历史
st.subheader("对话历史")
for chat in st.session_state.chat_history:
    st.text_area("问题：", chat["query"], height=50, disabled=True)
    st.text_area("回答：", chat["response"], height=100, disabled=True)
    st.markdown("---")