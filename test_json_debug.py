#!/usr/bin/env python3
"""
Oracle JSON搜索调试脚本
直接连接数据库执行测试SQL，找出JSON搜索问题
"""

import oracledb
from oracle_23ai_config import ORACLE_23AI_CONFIG
import json

def test_json_search():
    """测试JSON搜索功能"""
    print("🔍 Oracle 23ai JSON搜索调试")
    print("=" * 60)
    
    try:
        # 连接数据库
        connection = oracledb.connect(
            user=ORACLE_23AI_CONFIG["username"],
            password=ORACLE_23AI_CONFIG["password"],
            dsn=ORACLE_23AI_CONFIG["dsn"]
        )
        print("✅ 数据库连接成功")
        
        cursor = connection.cursor()
        
        # 测试1: 检查表中的数据总数
        print("\n📊 测试1: 检查表中的数据总数")
        cursor.execute("SELECT COUNT(*) AS total_records FROM MEDICAL_DOCUMENTS")
        total_count = cursor.fetchone()[0]
        print(f"   总记录数: {total_count}")
        
        if total_count == 0:
            print("❌ 表中没有数据！")
            return
        
        # 测试2: 查看所有记录的基本信息
        print("\n📋 测试2: 查看所有记录的基本信息")
        cursor.execute("""
            SELECT patient_id, 
                   SUBSTR(DOC_DATA, 1, 200) AS doc_preview,
                   created_date
            FROM MEDICAL_DOCUMENTS
        """)
        records = cursor.fetchall()
        for i, row in enumerate(records, 1):
            print(f"   记录{i}: 患者={row[0]}, 创建时间={row[2]}")
            print(f"   内容预览: {row[1]}")
            print()
        
        # 测试3: 测试患者ID精确匹配
        print("\n🔍 测试3: 测试患者ID精确匹配")
        cursor.execute("SELECT patient_id, DOC_DATA FROM MEDICAL_DOCUMENTS WHERE patient_id = '周某某'")
        exact_results = cursor.fetchall()
        print(f"   精确匹配结果数: {len(exact_results)}")
        for row in exact_results:
            print(f"   找到: 患者={row[0]}")
        
        # 测试4: 测试患者ID模糊匹配
        print("\n🔍 测试4: 测试患者ID模糊匹配")
        cursor.execute("SELECT patient_id, DOC_DATA FROM MEDICAL_DOCUMENTS WHERE patient_id LIKE '%周某某%'")
        like_results = cursor.fetchall()
        print(f"   模糊匹配结果数: {len(like_results)}")
        for row in like_results:
            print(f"   找到: 患者={row[0]}")
        
        # 测试5: 测试JSON内容搜索（查找"主诉"）
        print("\n🔍 测试5: 测试JSON内容搜索（查找'主诉'）")
        cursor.execute("SELECT patient_id, DOC_DATA FROM MEDICAL_DOCUMENTS WHERE UPPER(DOC_DATA) LIKE UPPER('%主诉%')")
        complaint_results = cursor.fetchall()
        print(f"   '主诉'搜索结果数: {len(complaint_results)}")
        for row in complaint_results:
            print(f"   找到: 患者={row[0]}")
            # 尝试解析JSON并查找主诉相关内容
            try:
                if isinstance(row[1], dict):
                    doc_data = row[1]
                elif isinstance(row[1], str):
                    doc_data = json.loads(row[1])
                else:
                    doc_data = {}
                print(f"   JSON keys: {list(doc_data.keys())}")
                # 查找包含"主诉"的字段
                for key, value in doc_data.items():
                    if '主诉' in str(key) or '主诉' in str(value):
                        print(f"   主诉相关: {key} = {value}")
            except Exception as e:
                print(f"   JSON解析失败: {e}")
        
        # 测试6: 测试JSON内容搜索（查找"头晕"）
        print("\n🔍 测试6: 测试JSON内容搜索（查找'头晕'）")
        cursor.execute("SELECT patient_id, DOC_DATA FROM MEDICAL_DOCUMENTS WHERE UPPER(DOC_DATA) LIKE UPPER('%头晕%')")
        dizzy_results = cursor.fetchall()
        print(f"   '头晕'搜索结果数: {len(dizzy_results)}")
        for row in dizzy_results:
            print(f"   找到: 患者={row[0]}")
        
        # 测试7: 组合条件测试
        print("\n🔍 测试7: 组合条件测试")
        cursor.execute("""
            SELECT patient_id, DOC_DATA 
            FROM MEDICAL_DOCUMENTS 
            WHERE patient_id LIKE '%周某某%' 
              AND (UPPER(DOC_DATA) LIKE UPPER('%主诉%') OR UPPER(DOC_DATA) LIKE UPPER('%头晕%'))
        """)
        combined_results = cursor.fetchall()
        print(f"   组合条件结果数: {len(combined_results)}")
        for row in combined_results:
            print(f"   找到: 患者={row[0]}")
        
        # 测试8: 显示完整的JSON结构（仅第一条记录）
        print("\n📄 测试8: 显示完整的JSON结构")
        cursor.execute("SELECT patient_id, DOC_DATA FROM MEDICAL_DOCUMENTS WHERE ROWNUM = 1")
        first_record = cursor.fetchone()
        if first_record:
            print(f"   患者: {first_record[0]}")
            try:
                if isinstance(first_record[1], dict):
                    doc_data = first_record[1]
                elif isinstance(first_record[1], str):
                    doc_data = json.loads(first_record[1])
                else:
                    doc_data = {"raw": str(first_record[1])}
                
                print("   完整JSON结构:")
                print(json.dumps(doc_data, ensure_ascii=False, indent=2))
            except Exception as e:
                print(f"   JSON解析失败: {e}")
                print(f"   原始数据类型: {type(first_record[1])}")
                print(f"   原始数据: {str(first_record[1])[:500]}...")
        
        cursor.close()
        connection.close()
        
        print("\n✅ 所有测试完成！")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_json_search()
