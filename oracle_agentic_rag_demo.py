"""
Oracle 23ai 融合数据库版本的 Agentic RAG 演示
统一使用Oracle 23ai管理向量、JSON文档和图数据
"""

import streamlit as st
import json
import pdfplumber
import traceback
from datetime import datetime
from typing import List, Dict, Any

# Oracle 23ai 模块导入
from oracle_23ai_config import initialize_oracle_23ai, oracle_manager
from oracle_vector_store import (
    oracle_vector_store, get_oracle_vector_search_results, 
    import_to_oracle_vectors, get_oracle_vector_stats, clear_oracle_vectors
)
from oracle_json_store import (
    oracle_json_store, get_oracle_json_search_results,
    import_to_oracle_json, get_oracle_json_stats, clear_oracle_json
)
from oracle_graph_store import (
    oracle_graph_store, get_oracle_graph_search_results,
    build_oracle_graph_from_json, get_oracle_graph_stats, clear_oracle_graph
)

# 通用配置导入
from config import get_openai_client, make_api_request, api_manager

# 设置页面配置
st.set_page_config(
    page_title="Oracle 23ai Agentic RAG - 医疗知识问答系统",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 页面标题
st.markdown("""
<div style='text-align: center; padding: 2rem 0;'>
    <h1>🏥 Oracle 23ai Agentic RAG</h1>
    <h2>医疗知识问答系统 - 融合数据库版本</h2>
    <p style='color: #666; font-size: 1.1em;'>基于Oracle 23ai融合数据库的智能医疗问答系统</p>
    <p style='color: #888; font-size: 0.9em;'>统一管理向量搜索、JSON文档和图数据库</p>
</div>
""", unsafe_allow_html=True)

def check_oracle_connection():
    """检查Oracle 23ai连接状态"""
    try:
        return oracle_manager.test_connection()
    except Exception as e:
        st.error(f"Oracle连接检查失败: {str(e)}")
        return False

def check_data_initialized():
    """检查数据是否已初始化"""
    try:
        # 检查向量数据
        vector_stats = get_oracle_vector_stats()
        if vector_stats.get('total_vectors', 0) > 0:
            return True
        
        # 检查JSON文档数据
        json_stats = get_oracle_json_stats()
        if json_stats.get('total_documents', 0) > 0:
            return True
        
        # 检查图数据
        graph_stats = get_oracle_graph_stats()
        if graph_stats.get('total_vertices', 0) > 0:
            return True
        
        return False
    except Exception as e:
        st.error(f"数据检查失败: {str(e)}")
        return False

def get_structured_data(pdf_content: str) -> Dict[str, Any]:
    """使用LLM提取结构化数据"""
    try:
        client, model, temperature = get_openai_client()
        
        # 读取结构化数据格式
        with open('get_inf.json', 'r', encoding='utf-8') as f:
            format_example = json.load(f)
        
        prompt = f"""请从以下医疗文档中提取结构化信息，严格按照JSON格式返回：

参考格式：
{json.dumps(format_example, ensure_ascii=False, indent=2)}

医疗文档内容：
{pdf_content[:5000]}  # 限制内容长度

要求：
1. 严格按照JSON格式返回
2. 如果某个字段没有信息，设置为null
3. 生化指标要提取所有数值和单位
4. 确保患者姓名正确提取"""

        response = make_api_request(
            client, model,
            [
                {
                    "role": "system",
                    "content": "你是一个专业的医疗文档分析专家，负责从医疗文档中提取结构化信息。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # 清理响应文本，提取JSON部分
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            response_text = response_text[json_start:json_end]
        elif "{" in response_text:
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            response_text = response_text[json_start:json_end]
        
        # 解析JSON
        structured_data = json.loads(response_text)
        return structured_data
        
    except Exception as e:
        st.error(f"结构化数据提取失败: {str(e)}")
        return {}

def import_to_oracle_all_databases(pdf_content: str, filename: str) -> bool:
    """导入数据到Oracle 23ai所有数据库"""
    try:
        st.write("🔄 开始导入到Oracle 23ai融合数据库...")
        
        # 1. 提取结构化数据
        st.write("📊 使用AI提取结构化数据...")
        structured_data = get_structured_data(pdf_content)
        
        if not structured_data:
            st.error("结构化数据提取失败")
            return False
        
        patient_name = structured_data.get('患者姓名', 'Unknown')
        st.write(f"📋 患者姓名: {patient_name}")
        
        # 2. 导入到JSON文档数据库
        st.write("💾 导入到Oracle JSON文档数据库...")
        json_success = import_to_oracle_json(structured_data, patient_name)
        
        if not json_success:
            st.error("JSON文档导入失败")
            return False
        
        # 3. 导入到向量数据库
        st.write("🔍 导入到Oracle向量数据库...")
        
        # 准备向量数据
        texts = []
        metadatas = []
        patient_names = []
        
        # 添加完整文档
        texts.append(pdf_content[:2000])  # 限制长度
        metadatas.append({
            'patient_name': patient_name,
            'source_type': 'full_document',
            'source_filename': filename,
            'import_time': datetime.now().isoformat()
        })
        patient_names.append(patient_name)
        
        # 添加主要字段
        for field in ['主诉', '现病史', '诊断', '治疗方案']:
            if field in structured_data and structured_data[field]:
                texts.append(f"{field}: {structured_data[field]}")
                metadatas.append({
                    'patient_name': patient_name,
                    'source_type': field,
                    'source_filename': filename,
                    'import_time': datetime.now().isoformat()
                })
                patient_names.append(patient_name)
        
        # 添加生化指标
        if '生化指标' in structured_data and structured_data['生化指标']:
            lab_data = structured_data['生化指标']
            if isinstance(lab_data, dict):
                for indicator, value in lab_data.items():
                    if value:
                        texts.append(f"生化指标 {indicator}: {value}")
                        metadatas.append({
                            'patient_name': patient_name,
                            'source_type': 'lab_result',
                            'indicator': indicator,
                            'value': value,
                            'source_filename': filename,
                            'import_time': datetime.now().isoformat()
                        })
                        patient_names.append(patient_name)
        
        vector_success = import_to_oracle_vectors(texts, metadatas, patient_names)
        
        if not vector_success:
            st.error("向量数据导入失败")
            return False
        
        # 4. 构建图数据库
        st.write("🕸️ 构建Oracle图数据库...")
        
        # 准备图数据（从JSON文档获取）
        json_documents = [{
            'patient_id': patient_name,
            'document': structured_data
        }]
        
        graph_success = build_oracle_graph_from_json(json_documents)
        
        if not graph_success:
            st.error("图数据库构建失败")
            return False
        
        st.success("✅ 数据成功导入到Oracle 23ai融合数据库！")
        return True
        
    except Exception as e:
        st.error(f"导入过程失败: {str(e)}")
        st.error(f"错误详情: {traceback.format_exc()}")
        return False

def perform_oracle_search(query: str, search_type: str = "混合检索"):
    """执行Oracle 23ai搜索"""
    try:
        st.write(f"🔍 执行{search_type}...")
        
        if search_type == "向量搜索":
            # 纯向量搜索
            vector_results = get_oracle_vector_search_results(query)
            
            st.write("🔍 Oracle向量搜索结果:")
            if vector_results:
                for i, result in enumerate(vector_results[:5], 1):
                    st.info(f"{i}. 患者: {result['patient_name']} | 相似度: {result['similarity']:.3f}")
                    st.write(f"内容: {result['content'][:200]}...")
            else:
                st.write("未找到相关向量内容")
        
        elif search_type == "文档搜索":
            # 纯JSON文档搜索
            json_results = get_oracle_json_search_results(query)
            
            st.write("📄 Oracle JSON文档搜索结果:")
            if json_results:
                for result in json_results:
                    st.info(result)
            else:
                st.write("未找到相关文档内容")
        
        elif search_type == "图数据库":
            # 纯图数据库搜索
            graph_results = get_oracle_graph_search_results(query)
            
            st.write("🕸️ Oracle图数据库搜索结果:")
            if graph_results:
                for result in graph_results:
                    st.info(result)
            else:
                st.write("未找到相关图数据")
        
        else:  # 混合检索
            # 并行执行所有搜索
            vector_results = get_oracle_vector_search_results(query)
            json_results = get_oracle_json_search_results(query)
            graph_results = get_oracle_graph_search_results(query)
            
            # 使用列布局显示结果
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write("🔍 向量搜索结果:")
                if vector_results:
                    for result in vector_results[:3]:
                        st.info(f"患者: {result['patient_name']}\n相似度: {result['similarity']:.3f}")
                else:
                    st.write("未找到相关内容")
            
            with col2:
                st.write("📄 JSON文档结果:")
                if json_results:
                    for result in json_results[:3]:
                        st.info(result)
                else:
                    st.write("未找到相关内容")
            
            with col3:
                st.write("🕸️ 图数据库结果:")
                if graph_results:
                    for result in graph_results[:3]:
                        st.info(result)
                else:
                    st.write("未找到相关内容")
            
            # 生成综合回答
            if vector_results or json_results or graph_results:
                st.write("🤖 综合分析结果:")
                
                try:
                    client, model, temperature = get_openai_client()
                    
                    # 准备综合信息
                    all_info = []
                    
                    if vector_results:
                        all_info.append("向量搜索结果:")
                        for result in vector_results[:3]:
                            all_info.append(f"- {result['content']}")
                    
                    if json_results:
                        all_info.append("文档搜索结果:")
                        for result in json_results[:3]:
                            all_info.append(f"- {result}")
                    
                    if graph_results:
                        all_info.append("图数据库结果:")
                        for result in graph_results[:3]:
                            all_info.append(f"- {result}")
                    
                    combined_info = "\n".join(all_info)
                    
                    prompt = f"""基于以下Oracle 23ai融合数据库的搜索结果，请回答用户问题：

用户问题：{query}

搜索结果：
{combined_info}

请提供准确、专业的医疗信息回答，如果信息不足请说明。"""
                    
                    response = make_api_request(
                        client, model,
                        [
                            {
                                "role": "system",
                                "content": "你是一个专业的医疗AI助手，基于Oracle 23ai融合数据库的搜索结果回答问题。"
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        temperature
                    )
                    
                    answer = response.choices[0].message.content.strip()
                    st.success(answer)
                    
                except Exception as e:
                    st.warning(f"AI回答生成失败: {str(e)}，显示原始搜索结果")
    
    except Exception as e:
        st.error(f"搜索失败: {str(e)}")

# 侧边栏配置
with st.sidebar:
    st.header("Oracle 23ai 系统设置")
    
    # Oracle连接状态
    st.subheader("🔗 数据库连接状态")
    if check_oracle_connection():
        st.success("✅ Oracle 23ai连接正常")
    else:
        st.error("❌ Oracle 23ai连接失败")
        if st.button("初始化Oracle 23ai"):
            with st.spinner("正在初始化Oracle 23ai..."):
                if initialize_oracle_23ai():
                    st.success("✅ Oracle 23ai初始化成功")
                    st.rerun()
                else:
                    st.error("❌ Oracle 23ai初始化失败")
    
    # API使用统计
    st.subheader("📊 API使用统计")
    try:
        stats = api_manager.get_stats()
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("本分钟请求", f"{stats['requests_this_minute']}/{stats['max_requests_per_minute']}")
        with col2:
            st.metric("请求间隔", f"{stats['request_interval']}秒")
        
        if stats['time_since_last_request'] > 0:
            st.info(f"⏰ 上次请求: {stats['time_since_last_request']:.1f}秒前")
        
        st.caption(f"💡 免费账户限制: {stats['max_requests_per_minute']}请求/分钟")
    except Exception as e:
        st.error(f"API统计获取失败: {str(e)}")
    
    st.divider()
    
    # 数据状态
    if check_data_initialized():
        st.success("✅ Oracle 23ai中已有数据")
    else:
        st.warning("⚠️ Oracle 23ai中暂无数据")
    
    # 数据导入
    st.subheader("📥 数据导入")
    uploaded_files = st.file_uploader(
        "选择PDF文件",
        type=['pdf'],
        accept_multiple_files=True,
        help="支持上传多个PDF医疗文档"
    )
    
    if uploaded_files:
        st.write(f"已选择 {len(uploaded_files)} 个文件：")
        for file in uploaded_files:
            st.write(f"- {file.name}")
        
        if st.button("导入到Oracle 23ai"):
            with st.spinner("正在导入数据到Oracle 23ai..."):
                success_count = 0
                
                for uploaded_file in uploaded_files:
                    st.write(f"正在处理文件：{uploaded_file.name}")
                    
                    # 读取PDF内容
                    with pdfplumber.open(uploaded_file) as pdf:
                        pdf_content = ""
                        for page in pdf.pages:
                            pdf_content += page.extract_text()
                    
                    # 导入到Oracle 23ai
                    if import_to_oracle_all_databases(pdf_content, uploaded_file.name):
                        success_count += 1
                        st.success(f"✅ {uploaded_file.name} 导入成功")
                    else:
                        st.error(f"❌ {uploaded_file.name} 导入失败")
                
                st.info(f"导入完成：{success_count}/{len(uploaded_files)} 个文件成功")
                if success_count > 0:
                    st.rerun()

# 数据库统计展示
with st.sidebar:
    st.subheader("📊 数据库统计")
    
    try:
        # 向量数据库统计
        vector_stats = get_oracle_vector_stats()
        if vector_stats:
            st.write("🔍 向量数据:")
            st.write(f"  - 向量数量: {vector_stats.get('total_vectors', 0)}")
            st.write(f"  - 患者数: {vector_stats.get('unique_patients', 0)}")
        
        # JSON文档统计
        json_stats = get_oracle_json_stats()
        if json_stats:
            st.write("📄 JSON文档:")
            st.write(f"  - 文档数量: {json_stats.get('total_documents', 0)}")
            st.write(f"  - 患者数: {json_stats.get('unique_patients', 0)}")
        
        # 图数据库统计
        graph_stats = get_oracle_graph_stats()
        if graph_stats:
            st.write("🕸️ 图数据:")
            st.write(f"  - 顶点数: {graph_stats.get('total_vertices', 0)}")
            st.write(f"  - 边数: {graph_stats.get('total_edges', 0)}")
    
    except Exception as e:
        st.error(f"统计信息获取失败: {str(e)}")
    
    # 数据清理
    st.subheader("🗑️ 数据管理")
    if st.button("清空所有数据", type="secondary"):
        if st.confirm("确定要清空Oracle 23ai中的所有数据吗？"):
            with st.spinner("正在清空数据..."):
                clear_oracle_vectors()
                clear_oracle_json()
                clear_oracle_graph()
                st.success("✅ 数据清空完成")
                st.rerun()

# 主界面 - 搜索功能
st.header("🔍 智能医疗问答")

# 搜索类型选择
search_type = st.selectbox(
    "选择搜索方式",
    ["混合检索", "向量搜索", "文档搜索", "图数据库"],
    help="混合检索：同时使用向量、文档和图数据库搜索"
)

# 搜索输入
query = st.text_input(
    "请输入您的问题",
    placeholder="例如：周某某的主诉是什么？",
    help="支持患者姓名、症状、诊断、治疗方案等查询"
)

# 执行搜索
if st.button("🚀 开始搜索", type="primary"):
    if query:
        perform_oracle_search(query, search_type)
    else:
        st.warning("请输入搜索问题")

# 示例问题
st.subheader("💡 示例问题")
example_questions = [
    "周某某的主诉是什么？",
    "蒲某某的生化指标有哪些？",
    "马某某的诊断结果是什么？",
    "刘某某的治疗方案是什么？",
    "哪些患者的白细胞偏高？"
]

cols = st.columns(len(example_questions))
for i, question in enumerate(example_questions):
    with cols[i]:
        if st.button(question, key=f"example_{i}"):
            perform_oracle_search(question, "混合检索")

# 系统信息
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 0.9em; padding: 1rem 0;'>
    <p><strong>Oracle 23ai Agentic RAG 医疗知识问答系统</strong></p>
    <p>基于Oracle 23ai融合数据库 | 统一管理向量、JSON文档和图数据</p>
    <p>Developed by Huaiyuan Tan</p>
</div>
""", unsafe_allow_html=True)
