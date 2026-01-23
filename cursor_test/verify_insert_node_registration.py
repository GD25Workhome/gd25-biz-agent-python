"""
验证 insert_data_to_vector_db 节点是否正确注册

运行方式：
    python cursor_test/verify_insert_node_registration.py
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def verify_node_registration():
    """验证节点注册"""
    print("=" * 60)
    print("验证 insert_data_to_vector_db 节点注册")
    print("=" * 60)
    
    try:
        # 导入模块以触发自动注册
        from backend.domain.flows.implementations.insert_data_to_vector_db_func import (
            InsertDataToVectorDbNode
        )
        print("✓ 成功导入 InsertDataToVectorDbNode")
        
        # 检查 get_key 方法
        key = InsertDataToVectorDbNode.get_key()
        print(f"✓ get_key() 返回: {key}")
        assert key == "insert_data_to_vector_db", f"key 应该为 'insert_data_to_vector_db'，实际为: {key}"
        
        # 检查节点注册
        from backend.domain.flows.nodes.function_registry import function_registry
        
        # 触发发现机制
        function_registry.discover()
        
        # 检查是否已注册
        node_class = function_registry.get("insert_data_to_vector_db")
        if node_class:
            print(f"✓ 节点已注册到 function_registry")
            print(f"  注册的类: {node_class.__name__}")
        else:
            print("⚠️  节点未在注册表中找到")
            print(f"  可用的节点: {function_registry.get_all_keys()}")
            return False
        
        # 检查节点实例化
        node_instance = InsertDataToVectorDbNode()
        print(f"✓ 节点可以正常实例化: {type(node_instance).__name__}")
        
        print("\n" + "=" * 60)
        print("✓ 所有验证通过！")
        print("=" * 60)
        return True
        
    except ImportError as e:
        print(f"✗ 导入失败: {e}")
        print("  这可能是由于环境依赖问题，但不影响节点本身的实现")
        return False
    except Exception as e:
        print(f"✗ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = verify_node_registration()
    sys.exit(0 if success else 1)
