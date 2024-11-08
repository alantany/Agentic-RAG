import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import pickle
import os

class VectorStore:
    def __init__(self):
        # 初始化文本向量化模型
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.dimension = 384  # paraphrase-multilingual-MiniLM-L12-v2 的向量维度
        
        # 初始化FAISS索引
        self.index = faiss.IndexFlatL2(self.dimension)
        self.documents = []
        
        # 如果存在持久化的数据，则加载
        if os.path.exists('vector_store.pkl'):
            self.load_store()
    
    def text_to_vector(self, text: str):
        """将文本转换为向量"""
        return self.model.encode(text)
    
    def add_document(self, doc: dict):
        """添加文档到向量数据库"""
        # 获取文本的向量表示
        vector = self.text_to_vector(doc["content"])
        
        # 添加到FAISS索引
        self.index.add(np.array([vector], dtype=np.float32))
        self.documents.append(doc)
        
        # 保存到文件
        self.save_store()
    
    def search(self, query: str, limit: int = 3):
        """向量相似度搜索"""
        query_vector = self.text_to_vector(query)
        
        # 搜索最相似的向量
        D, I = self.index.search(np.array([query_vector], dtype=np.float32), limit)
        
        # 返回对应的文档
        results = []
        for idx in I[0]:
            if idx < len(self.documents):  # 确保索引有效
                results.append(self.documents[idx])
        
        return results
    
    def save_store(self):
        """保存向量存储到文件"""
        store_data = {
            'index': faiss.serialize_index(self.index),
            'documents': self.documents
        }
        with open('vector_store.pkl', 'wb') as f:
            pickle.dump(store_data, f)
    
    def load_store(self):
        """从文件加载向量存储"""
        try:
            with open('vector_store.pkl', 'rb') as f:
                store_data = pickle.load(f)
                self.index = faiss.deserialize_index(store_data['index'])
                self.documents = store_data['documents']
        except Exception as e:
            print(f"加载向量存储失败: {str(e)}") 