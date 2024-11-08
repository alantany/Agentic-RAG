import PyPDF2
import re
from datetime import datetime
import streamlit as st
from vector_store import VectorStore
import sqlite3
import networkx as nx

class MedicalRecordParser:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.content = self._read_pdf()
        self.parsed_data = self._parse_content()
    
    def _read_pdf(self):
        """读取PDF文件内容"""
        try:
            with open(self.pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                return text
        except Exception as e:
            st.error(f"PDF读取错误: {str(e)}")
            return ""
    
    def _parse_content(self):
        """解析病历内容"""
        data = {}
        
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

def import_to_vector_store(parser):
    """导入到向量数据库"""
    vector_store = VectorStore()
    
    # 创建完整的病历文档
    document = {
        "title": f"{parser.parsed_data['name']}的病历",
        "content": parser.content,
        "type": "病历记录",
        "date": parser.parsed_data['admission_date']
    }
    
    vector_store.add_document(document)
    return True

def import_to_sqlite(parser):
    """导入到关系数据库"""
    try:
        conn = sqlite3.connect('medical_records.db')
        cursor = conn.cursor()
        
        # 插入患者基本信息
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
        
        # 插入诊断信息
        for diagnosis in parser.parsed_data['diagnoses']:
            cursor.execute('''
            INSERT INTO diagnoses (patient_id, diagnosis, diagnosis_type)
            VALUES (?, ?, ?)
            ''', (patient_id, diagnosis, '出院诊断'))
        
        # 插入检查结果
        for exam_type, result in parser.parsed_data['examinations'].items():
            cursor.execute('''
            INSERT INTO examinations (patient_id, exam_type, exam_result, exam_date)
            VALUES (?, ?, ?, ?)
            ''', (patient_id, exam_type, result, parser.parsed_data['admission_date']))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"SQLite导入错误: {str(e)}")
        return False

def import_to_graph(parser):
    """导入到图数据库"""
    try:
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
        
        # 保存图
        nx.write_gexf(G, "medical_graph.gexf")
        return True
    except Exception as e:
        print(f"图数据库导入错误: {str(e)}")
        return False

def main():
    st.title("医疗病历数据导入工具")
    
    uploaded_file = st.file_uploader("上传病历PDF文件", type=['pdf'])
    
    if uploaded_file is not None:
        # 保存上传的文件
        with open("temp.pdf", "wb") as f:
            f.write(uploaded_file.getvalue())
        
        parser = MedicalRecordParser("temp.pdf")
        
        if st.button("开始导入数据"):
            with st.spinner("正在导入数据..."):
                # 导入向量数据库
                if import_to_vector_store(parser):
                    st.success("向量数据库数据导入成功！")
                else:
                    st.error("向量数据库数据导入失败！")
                
                # 导入关系数据库
                if import_to_sqlite(parser):
                    st.success("关系数据库数据导入成功！")
                else:
                    st.error("关系数据库数据导入失败！")
                
                # 导入图数据库
                if import_to_graph(parser):
                    st.success("图数据库数据导入成功！")
                else:
                    st.error("图数据库数据导入失败！")

if __name__ == "__main__":
    main() 