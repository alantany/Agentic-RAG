# -*- coding: utf-8 -*-
"""
Agentic RAG 系统配置文件
统一管理所有API密钥和模型配置
⚠️  敏感信息已移至.env文件，请确保.env文件不被提交到版本控制
"""

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# OpenAI API 配置 (使用OpenRouter)
OPENAI_CONFIG = {
    "api_key": os.getenv("OPENAI_API_KEY", ""),
    "base_url": os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
    "model": os.getenv("OPENAI_MODEL", "deepseek/deepseek-chat"),
    "timeout": 60,
    "temperature": 0.1,
    "max_requests_per_minute": int(os.getenv("MAX_REQUESTS_PER_MINUTE", "10")),
    "request_interval": int(os.getenv("REQUEST_INTERVAL", "6"))
}

# 备用API配置（如果主API失败时使用）
BACKUP_OPENAI_CONFIG = {
    "api_key": os.getenv("BACKUP_OPENAI_API_KEY", ""),
    "base_url": "https://api.chatanywhere.tech/v1",
    "model": "gpt-4o-mini-2024-07-18",
    "timeout": 60,
    "temperature": 0.1
}

# Pinecone 向量数据库配置
PINECONE_CONFIG = {
    "api_key": os.getenv("PINECONE_API_KEY", ""),
    "environment": "gcp-starter",
    "index_name": "medical-records",
    "dimension": 384,  # all-MiniLM-L6-v2 的维度
    "metric": "cosine"
}

# MongoDB 配置
MONGODB_CONFIG = {
    "connection_string": os.getenv("MONGODB_CONNECTION_STRING", ""),
    "database_name": "medical_records",
    "collection_name": "patients",
    "tls_allow_invalid_certificates": True
}

# Sentence Transformers 模型配置
SENTENCE_TRANSFORMER_CONFIG = {
    "model_name": "sentence-transformers/all-MiniLM-L6-v2",
    "cache_folder": "./models",
    "device": "cpu"  # 可以改为 "cuda" 如果有GPU
}

# 图数据库配置
GRAPH_DATABASE_CONFIG = {
    "graph_file": "medical_graph.gexf",
    "temp_graph_file": "temp_graph.html",
    "node_types": [
        "patient",
        "basic_info", 
        "diagnosis",
        "chief_complaint",
        "present_illness",
        "lab_result",
        "treatment"
    ],
    "relationship_types": [
        "has_basic_info",
        "has_diagnosis", 
        "has_complaint",
        "has_present_illness",
        "has_lab_result",
        "has_treatment"
    ]
}

# Neo4j 图数据库（Aura）连接配置
NEO4J_CONFIG = {
    "uri": os.getenv("NEO4J_URI", ""),
    "username": os.getenv("NEO4J_USERNAME", "neo4j"),
    "password": os.getenv("NEO4J_PASSWORD", ""),
    "database": "neo4j",
    "aura_instance_id": "fe69c89f",
    "aura_instance_name": "Instance01",
}

# 系统配置
SYSTEM_CONFIG = {
    "max_retries": 3,
    "chunk_size": 100000,
    "similarity_threshold": 0.3,
    "max_results": 5,
    "vector_top_k": 50
}

# 环境变量配置
ENV_CONFIG = {
    "HF_HUB_OFFLINE": "0",
    "TRANSFORMERS_OFFLINE": "0",
    "TOKENIZERS_PARALLELISM": "false"
}

# 获取OpenAI客户端的便捷函数
def get_openai_client(use_backup=False):
    """获取配置好的OpenAI客户端"""
    from openai import OpenAI
    import os
    
    # 设置环境变量
    for key, value in ENV_CONFIG.items():
        os.environ[key] = value
    
    config = BACKUP_OPENAI_CONFIG if use_backup else OPENAI_CONFIG
    
    try:
        client = OpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
            timeout=config["timeout"]
        )
        return client, config["model"], config["temperature"]
    except Exception as e:
        if not use_backup:
            # 如果主配置失败，尝试备用配置
            return get_openai_client(use_backup=True)
        else:
            # 备用配置也失败，抛出异常
            raise e

class APIRequestManager:
    """API请求管理器，控制请求频率"""
    def __init__(self):
        self.last_request_time = 0
        self.request_count = 0
        self.start_time = 0
        
    def wait_if_needed(self):
        """如果需要，等待一段时间再发送请求"""
        import time
        current_time = time.time()
        
        # 初始化开始时间
        if self.start_time == 0:
            self.start_time = current_time
        
        # 重置计数器（每分钟）
        if current_time - self.start_time >= 60:
            self.request_count = 0
            self.start_time = current_time
        
        # 检查是否超过每分钟限制
        if self.request_count >= OPENAI_CONFIG["max_requests_per_minute"]:
            wait_time = 60 - (current_time - self.start_time)
            if wait_time > 0:
                import streamlit as st
                st.warning(f"⏳ 达到API请求限制 ({OPENAI_CONFIG['max_requests_per_minute']}/分钟)，等待 {wait_time:.1f} 秒...")
                time.sleep(wait_time)
                self.request_count = 0
                self.start_time = time.time()
        
        # 控制请求间隔
        time_since_last = current_time - self.last_request_time
        if time_since_last < OPENAI_CONFIG["request_interval"]:
            wait_time = OPENAI_CONFIG["request_interval"] - time_since_last
            import streamlit as st
            st.info(f"⏱️ API请求间隔控制，等待 {wait_time:.1f} 秒...")
            time.sleep(wait_time)
        
        self.last_request_time = time.time()
        self.request_count += 1
        
    def get_stats(self):
        """获取API使用统计"""
        import time
        current_time = time.time()
        
        if self.start_time == 0:
            return {
                "requests_this_minute": 0,
                "time_since_last_request": 0,
                "max_requests_per_minute": OPENAI_CONFIG["max_requests_per_minute"],
                "request_interval": OPENAI_CONFIG["request_interval"]
            }
        
        # 如果超过一分钟，重置计数
        if current_time - self.start_time >= 60:
            requests_this_minute = 0
        else:
            requests_this_minute = self.request_count
            
        return {
            "requests_this_minute": requests_this_minute,
            "time_since_last_request": current_time - self.last_request_time if self.last_request_time > 0 else 0,
            "max_requests_per_minute": OPENAI_CONFIG["max_requests_per_minute"],
            "request_interval": OPENAI_CONFIG["request_interval"]
        }

# 全局请求管理器
api_manager = APIRequestManager()

def make_api_request(client, model, messages, temperature=0.1, max_tokens=None):
    """安全的API请求函数，包含频率控制"""
    api_manager.wait_if_needed()
    
    request_params = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    
    if max_tokens:
        request_params["max_tokens"] = max_tokens
        
    return client.chat.completions.create(**request_params)

def test_openai_client():
    """测试OpenAI客户端连接"""
    try:
        client, model, temperature = get_openai_client()
        # 发送一个简单的测试请求
        response = make_api_request(
            client, model, 
            [{"role": "user", "content": "Hello"}], 
            temperature, max_tokens=10
        )
        return True, "主API配置正常"
    except Exception as e:
        try:
            client, model, temperature = get_openai_client(use_backup=True)
            response = make_api_request(
                client, model,
                [{"role": "user", "content": "Hello"}],
                temperature, max_tokens=10
            )
            return True, "备用API配置正常"
        except Exception as backup_e:
            return False, f"主API错误: {str(e)}, 备用API错误: {str(backup_e)}"

# 获取Pinecone配置的便捷函数
def get_pinecone_config():
    """获取Pinecone配置"""
    return PINECONE_CONFIG

# 获取MongoDB配置的便捷函数
def get_mongodb_config():
    """获取MongoDB配置"""
    return MONGODB_CONFIG

# 获取Sentence Transformer配置的便捷函数
def get_sentence_transformer_config():
    """获取Sentence Transformer配置"""
    return SENTENCE_TRANSFORMER_CONFIG

# 获取图数据库配置的便捷函数
def get_graph_database_config():
    """获取图数据库配置"""
    return GRAPH_DATABASE_CONFIG

# 获取Neo4j驱动（需要 neo4j>=5）
def get_neo4j_driver():
    """创建并返回 Neo4j Driver（调用方负责在结束时关闭 driver.close()）"""
    try:
        from neo4j import GraphDatabase
        cfg = NEO4J_CONFIG
        driver = GraphDatabase.driver(
            cfg["uri"],
            auth=(cfg["username"], cfg["password"])
        )
        return driver
    except Exception as e:
        # 返回 None 由调用方决定回退到本地GEXF
        return None

# 获取系统配置的便捷函数
def get_system_config():
    """获取系统配置"""
    return SYSTEM_CONFIG
