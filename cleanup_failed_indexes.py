#!/usr/bin/env python3
"""
清理失败的索引
"""

import oracledb
from oracle_23ai_config import ORACLE_23AI_CONFIG, JSON_CONFIG

def cleanup_failed_indexes():
    """清理失败的索引"""
    print("🧹 清理失败的索引...")
    
    try:
        connection = oracledb.connect(
            user=ORACLE_23AI_CONFIG["username"],
            password=ORACLE_23AI_CONFIG["password"],
            dsn=ORACLE_23AI_CONFIG["dsn"]
        )
        
        cursor = connection.cursor()
        
        # 删除失败的JSON搜索索引
        try:
            cursor.execute(f"DROP INDEX {JSON_CONFIG['search_index']}")
            print(f"✅ 删除失败的索引 {JSON_CONFIG['search_index']}")
        except Exception as e:
            print(f"ℹ️ 索引删除: {str(e)}")
        
        connection.commit()
        cursor.close()
        connection.close()
        
        print("✅ 索引清理完成")
        
    except Exception as e:
        print(f"❌ 索引清理失败: {str(e)}")

if __name__ == "__main__":
    cleanup_failed_indexes()
