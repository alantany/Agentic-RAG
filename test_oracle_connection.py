#!/usr/bin/env python3
"""
测试Oracle 23ai数据库连接
"""

import oracledb
import sys
from oracle_23ai_config import ORACLE_23AI_CONFIG

def test_oracle_connection():
    """测试Oracle数据库连接"""
    print("🔍 测试Oracle 23ai数据库连接...")
    print("=" * 50)
    
    # 显示连接配置
    print("📊 连接配置:")
    print(f"  用户名: {ORACLE_23AI_CONFIG['username']}")
    print(f"  密码: {'*' * len(ORACLE_23AI_CONFIG['password'])}")
    print(f"  连接串: {ORACLE_23AI_CONFIG['dsn']}")
    print()
    
    try:
        # 尝试连接数据库
        print("🔗 正在连接数据库...")
        
        connection = oracledb.connect(
            user=ORACLE_23AI_CONFIG["username"],
            password=ORACLE_23AI_CONFIG["password"],
            dsn=ORACLE_23AI_CONFIG["dsn"]
        )
        
        print("✅ 数据库连接成功！")
        
        # 获取数据库基本信息
        cursor = connection.cursor()
        
        print("\n📋 数据库信息:")
        
        # 1. 当前用户
        cursor.execute("SELECT USER FROM DUAL")
        current_user = cursor.fetchone()[0]
        print(f"  当前用户: {current_user}")
        
        # 2. 测试简单查询
        print("\n🧪 执行测试查询:")
        cursor.execute("SELECT SYSDATE FROM DUAL")
        current_time = cursor.fetchone()[0]
        print(f"  当前时间: {current_time}")
        
        # 3. 检查JSON功能
        print("\n🔍 检查Oracle 23ai特性:")
        try:
            cursor.execute("SELECT JSON_VALUE('{\"test\": \"value\"}', '$.test') FROM DUAL")
            json_result = cursor.fetchone()[0]
            print(f"  ✅ JSON 功能可用: {json_result}")
        except Exception as e:
            print(f"  ❌ JSON 功能不可用: {str(e)}")
        
        # 4. 检查向量功能（基础测试）
        try:
            # 尝试创建一个简单的向量（如果支持）
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.fetchone()
            print("  ✅ 基础SQL功能正常")
        except Exception as e:
            print(f"  ❌ 基础SQL测试失败: {str(e)}")
        
        # 5. 检查用户权限和表
        print("\n💾 用户环境:")
        try:
            cursor.execute("SELECT COUNT(*) FROM USER_TABLES")
            table_count = cursor.fetchone()[0]
            print(f"  用户表数量: {table_count}")
        except Exception as e:
            print(f"  表信息获取失败: {str(e)}")
        
        # 6. 测试向量数据类型（如果支持）
        print("\n🎯 Vector功能测试:")
        try:
            # 尝试创建临时向量
            cursor.execute("SELECT VECTOR('[1,2,3]', 3, FLOAT32) FROM DUAL")
            vector_result = cursor.fetchone()[0]
            print("  ✅ Vector数据类型支持正常")
            print(f"  测试向量: {str(vector_result)[:50]}...")
        except Exception as e:
            print(f"  ⚠️  Vector功能测试: {str(e)}")
            print("  💡 可能需要Oracle 23ai或更高版本")
        
        cursor.close()
        connection.close()
        
        print("\n🎉 Oracle 23ai连接测试完成！")
        return True
        
    except oracledb.DatabaseError as e:
        error, = e.args
        print(f"❌ 数据库连接失败!")
        print(f"错误代码: {error.code}")
        print(f"错误信息: {error.message}")
        
        # 提供常见问题的解决建议
        if error.code == 12541:  # TNS:no listener
            print("\n💡 解决建议:")
            print("  1. 检查Oracle数据库是否启动")
            print("  2. 检查监听器是否运行")
            print("  3. 验证连接串格式是否正确")
        elif error.code == 1017:  # invalid username/password
            print("\n💡 解决建议:")
            print("  1. 检查用户名和密码是否正确")
            print("  2. 确认用户是否存在于目标数据库")
        elif error.code == 12514:  # TNS:listener does not currently know of service
            print("\n💡 解决建议:")
            print("  1. 检查服务名是否正确")
            print("  2. 确认数据库服务是否注册到监听器")
        
        return False
        
    except Exception as e:
        print(f"❌ 连接测试失败: {str(e)}")
        return False

def test_oracledb_installation():
    """测试oracledb模块安装"""
    print("🔍 检查oracledb模块...")
    
    try:
        import oracledb
        print(f"✅ oracledb 版本: {oracledb.__version__}")
        
        # 检查客户端模式
        print(f"📦 客户端模式: {'Thick' if oracledb.is_thin_mode() == False else 'Thin'}")
        
        return True
        
    except ImportError:
        print("❌ oracledb 模块未安装")
        print("💡 安装命令: pip install oracledb")
        return False
    except Exception as e:
        print(f"❌ oracledb 模块检查失败: {str(e)}")
        return False

if __name__ == "__main__":
    print("Oracle 23ai 数据库连接测试")
    print("=" * 60)
    
    # 1. 检查oracledb模块
    if not test_oracledb_installation():
        sys.exit(1)
    
    print()
    
    # 2. 测试数据库连接
    success = test_oracle_connection()
    
    if success:
        print("\n🎯 下一步:")
        print("  1. 运行: python oracle_23ai_config.py")
        print("  2. 初始化数据库表结构")
        print("  3. 启动应用: streamlit run oracle_agentic_rag_demo.py")
        sys.exit(0)
    else:
        print("\n❌ 请解决连接问题后重试")
        sys.exit(1)
