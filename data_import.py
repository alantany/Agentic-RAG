import weaviate
import sqlite3
import networkx as nx
import json
import os
from vector_store import VectorStore

# 示例数据
sample_documents = [
    {
        "title": "人工智能简介",
        "content": "人工智能是计算机科学的一个分支，致力于开发能够模拟人类智能的系统。",
        "category": "AI基础"
    },
    {
        "title": "机器学习概述",
        "content": "机器学习是人工智能的一个子领域，专注于让计算机系统从数据中学习和改进。",
        "category": "机器学习"
    },
    {
        "title": "深度学习入门",
        "content": "深度学习是基于人工神经网络的机器学习方法，能够自动学习数据的层次化表示。",
        "category": "深度学习"
    }
]

def setup_vector_store():
    """设置和导入向量数据库数据"""
    try:
        vector_store = VectorStore()
        
        # 导入数据
        for doc in sample_documents:
            vector_store.add_document(doc)
        
        return True
    except Exception as e:
        print(f"向量存储设置错误: {str(e)}")
        return False

def setup_sqlite():
    """设置和导入关系数据库数据"""
    try:
        conn = sqlite3.connect('medical_records.db')
        cursor = conn.cursor()
        
        # 创建患者基本信息表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            gender TEXT,
            age INTEGER,
            ethnicity TEXT,
            marriage TEXT,
            admission_date DATE,
            discharge_date DATE
        )
        ''')
        
        # 创建诊断信息表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            diagnosis TEXT,
            diagnosis_type TEXT,  -- 入院诊断/出院诊断
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        )
        ''')
        
        # 创建检查结果表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS examinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            exam_type TEXT,
            exam_result TEXT,
            exam_date DATE,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        )
        ''')
        
        # 插入示例数据
        cursor.execute('''
        INSERT INTO patients (name, gender, age, ethnicity, marriage, admission_date, discharge_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ("周某某", "女", 69, "汉族", "已婚", "2024-06-18", "2024-06-24"))
        
        patient_id = cursor.lastrowid
        
        # 插入诊断
        diagnoses = [
            (patient_id, "脑血管供血不足", "出院诊断"),
            (patient_id, "多发腔隙性脑梗死", "出院诊断"),
            (patient_id, "脑动脉粥样硬化", "出院诊断"),
            (patient_id, "高血压病", "出院诊断")
        ]
        cursor.executemany('INSERT INTO diagnoses (patient_id, diagnosis, diagnosis_type) VALUES (?, ?, ?)', diagnoses)
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"SQLite设置错误: {str(e)}")
        return False

def setup_graph():
    """设置和导入图数据库数据"""
    try:
        G = nx.Graph()
        
        # 添加患者节点
        G.add_node("周某某", 
                   type="patient",
                   age=69,
                   gender="女")
        
        # 添加诊断节点
        diagnoses = ["脑血管供血不足", "多发腔隙性脑梗死", "脑动脉粥样硬化", "高血压病"]
        for diagnosis in diagnoses:
            G.add_node(diagnosis, type="diagnosis")
            G.add_edge("周某某", diagnosis, relationship="diagnosed_with")
        
        # 添加症状节点和关系
        symptoms = ["头晕", "恶心", "胸闷心慌"]
        for symptom in symptoms:
            G.add_node(symptom, type="symptom")
            G.add_edge("周某某", symptom, relationship="has_symptom")
        
        # 添加检查结果节点
        examinations = {
            "头颅MRI": "多发腔隙性脑梗塞，脑白质脱髓鞘改变",
            "动态心电图": "主导节律为窦性",
            "眼震电图": "眼动系统（+），动态位置试验（+）"
        }
        for exam, result in examinations.items():
            G.add_node(exam, type="examination", result=result)
            G.add_edge("周某某", exam, relationship="underwent")
        
        # 保存图
        nx.write_gexf(G, "medical_graph.gexf")
        return True
    except Exception as e:
        print(f"图数据库设置错误: {str(e)}")
        return False

def main():
    st.title("数据导入工具")
    
    if st.button("开始导入数据"):
        with st.spinner("正在导入数据..."):
            # 导入向量数据库
            if setup_vector_store():
                st.success("向量数据库数据导入成功！")
            else:
                st.error("向量数据库数据导入失败！")
            
            # 导入关系数据库
            if setup_sqlite():
                st.success("关系数据库数据导入成功！")
            else:
                st.error("关系数据库数据导入失败！")
            
            # 导入图数据库
            if setup_graph():
                st.success("图数据库数据导入成功！")
            else:
                st.error("图数据库数据导入失败！")

if __name__ == "__main__":
    main() 