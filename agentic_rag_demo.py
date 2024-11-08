import streamlit as st
import importlib
import subprocess
import sys
import sqlite3
import json
from vector_store import VectorStore
import networkx as nx

# 检查并安装依赖
def install_missing_packages():
    required_packages = {
        'openai': 'openai',
        'faiss': 'faiss-cpu',
        'sqlalchemy': 'sqlalchemy',
        'networkx': 'networkx',
        'sentence_transformers': 'sentence-transformers'
    }
    
    for package, pip_name in required_packages.items():
        if importlib.util.find_spec(package) is None:
            st.warning(f"正在安装 {pip_name}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
            st.success(f"{pip_name} 安装成功！")

install_missing_packages()

# 初始化OpenAI客户端
client = OpenAI(
    api_key="sk-2D0EZSwcWUcD4c2K59353b7214854bBd8f35Ac131564EfBa",
    base_url="https://free.gpt.ge/v1"
)

# 初始化向量存储
vector_store = VectorStore()

# 设置页面配置
st.set_page_config(page_title="Agentic RAG 系统", layout="wide")

# 初始化会话状态
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

def get_vector_search_results(query: str) -> list:
    try:
        results = vector_store.search(query)
        return [f"{item['title']}: {item['content']}" for item in results]
    except Exception as e:
        st.error(f"向量搜索错误: {str(e)}")
        return []

def get_rdb_search_results(query: str) -> list:
    try:
        conn = sqlite3.connect('knowledge_base.db')
        cursor = conn.cursor()
        
        cursor.execute("""
        SELECT title, content FROM documents 
        WHERE title LIKE ? OR content LIKE ?
        LIMIT 3
        """, (f"%{query}%", f"%{query}%"))
        
        results = cursor.fetchall()
        conn.close()
        
        return [f"{title}: {content}" for title, content in results]
    except Exception as e:
        st.error(f"数据库搜索错误: {str(e)}")
        return []

def get_graph_search_results(query: str) -> list:
    try:
        G = nx.read_gexf("knowledge_graph.gexf")
        results = []
        
        for node in G.nodes(data=True):
            if query.lower() in node[1].get('content', '').lower():
                results.append(f"{node[0]}: {node[1].get('content', '')}")
        
        return results[:3]
    except Exception as e:
        st.error(f"图数据库搜索错误: {str(e)}")
        return []

def get_llm_response(query: str, search_results: dict) -> str:
    try:
        # 构建提示词
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

def process_medical_query(query: str):
    """处理医疗查询"""
    # 向量搜索找相似病例
    vector_results = vector_store.search(query)
    
    # 关系数据库查询具体信息
    with sqlite3.connect('medical_records.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.name, d.diagnosis 
            FROM patients p 
            JOIN diagnoses d ON p.id = d.patient_id 
            WHERE d.diagnosis LIKE ?
        """, (f"%{query}%",))
        sql_results = cursor.fetchall()
    
    # 图数据库查询关系
    G = nx.read_gexf("medical_graph.gexf")
    graph_results = []
    for node in G.nodes(data=True):
        if query.lower() in str(node[1]).lower():
            neighbors = list(G.neighbors(node[0]))
            graph_results.append(f"{node[0]} 相关: {neighbors}")
    
    return {
        "vector": vector_results,
        "sql": sql_results,
        "graph": graph_results
    }

# 主界面
st.title("🤖 Agentic RAG 系统")

# 侧边栏配置
with st.sidebar:
    st.header("系统配置")
    search_methods = st.multiselect(
        "选择搜索方法",
        ["向量搜索", "关系数据库", "图数据库"],
        default=["向量搜索", "关系数据库", "图数据库"]
    )

# 主要内容区域
query = st.text_input("请输入您的问题：")

if st.button("搜索并生成"):
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