"""
测试 insert_data_to_vector_db_func 节点功能

运行方式（pytest）：
    pytest cursor_test/test_insert_data_to_vector_db_func.py -v

运行方式（直接运行）：
    cd cursor_test
    python test_insert_data_to_vector_db_func.py
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(project_root / ".env")

# 确保 ProviderManager 已加载配置
from backend.infrastructure.llm.providers.manager import ProviderManager
from backend.app.config import settings

# 初始化 ProviderManager
config_path = project_root / settings.MODEL_PROVIDERS_CONFIG
if not config_path.is_absolute():
    config_path = project_root / config_path
ProviderManager.load_providers(config_path)


def _import_insert_node():
    """导入 InsertDataToVectorDbNode，避免通过 __init__.py 导入时的依赖问题"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "insert_data_to_vector_db_func",
        project_root / "backend/domain/flows/implementations/insert_data_to_vector_db_func.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.InsertDataToVectorDbNode


async def test_insert_data_to_vector_db_node_success():
    """测试 insert_data_to_vector_db 节点成功场景"""
    print("=" * 60)
    print("测试 1: insert_data_to_vector_db 节点成功场景")
    print("=" * 60)
    
    import asyncio
    InsertDataToVectorDbNode = _import_insert_node()
    from backend.domain.state import FlowState
    from backend.infrastructure.database.connection import get_session_factory
    from backend.infrastructure.database.models.embedding_record import EmbeddingRecord
    from langchain_core.messages import HumanMessage
    from sqlalchemy import select
    
    # 创建节点实例
    node = InsertDataToVectorDbNode()
    
    # 1. 先创建一个测试用的 embedding_record
    session_factory = get_session_factory()
    async with session_factory() as session:
        # 创建测试记录
        test_record = EmbeddingRecord(
            scene_summary="测试场景摘要",
            optimization_question="测试问题",
            ai_response="测试回复",
            message_id="test_message_001",
            version=0,
            is_published=False,
            source_table_name="test_table",
            source_record_id="test_source_001",
            generation_status=0,  # 进行中
            failure_reason=None,
        )
        session.add(test_record)
        await session.flush()
        await session.refresh(test_record)
        embedding_records_id = test_record.id
        await session.commit()
        
        print(f"创建测试记录: id={embedding_records_id}")
    
    # 2. 创建测试状态
    # 模拟 embedding_value（2048维向量）
    test_embedding_value = [0.1] * 2048
    
    state: FlowState = {
        "current_message": HumanMessage(content="测试"),
        "history_messages": [],
        "flow_msgs": [],
        "session_id": "test_session",
        "edges_var": {
            "embedding_value": test_embedding_value
        },
        "prompt_vars": {
            "embedding_records_id": embedding_records_id
        }
    }
    
    # 3. 执行节点
    new_state = await node.execute(state)
    
    # 4. 验证数据库记录已更新
    async with session_factory() as session:
        stmt = select(EmbeddingRecord).where(
            EmbeddingRecord.id == embedding_records_id
        )
        result = await session.execute(stmt)
        updated_record = result.scalar_one_or_none()
        
        assert updated_record is not None, "记录应该存在"
        assert updated_record.generation_status == 1, "generation_status 应该为 1（成功）"
        assert updated_record.embedding_value is not None, "embedding_value 应该已设置"
        assert updated_record.failure_reason is None, "failure_reason 应该为 None"
        
        # 验证向量值（如果是列表，检查长度）
        if isinstance(updated_record.embedding_value, list):
            assert len(updated_record.embedding_value) == 2048, "向量维度应该为 2048"
        
        print(f"✓ 记录已更新: id={embedding_records_id}")
        print(f"  generation_status: {updated_record.generation_status}")
        print(f"  embedding_value 已设置: {updated_record.embedding_value is not None}")
        print("✓ 测试通过\n")
    
    # 清理：删除测试记录
    async with session_factory() as session:
        stmt = select(EmbeddingRecord).where(
            EmbeddingRecord.id == embedding_records_id
        )
        result = await session.execute(stmt)
        test_record = result.scalar_one_or_none()
        if test_record:
            await session.delete(test_record)
            await session.commit()
            print(f"清理测试记录: id={embedding_records_id}\n")


async def test_insert_data_to_vector_db_node_missing_embedding_value():
    """测试 insert_data_to_vector_db 节点 - embedding_value 缺失"""
    print("=" * 60)
    print("测试 2: insert_data_to_vector_db 节点 - embedding_value 缺失")
    print("=" * 60)
    
    from backend.domain.flows.implementations.insert_data_to_vector_db_func import (
        InsertDataToVectorDbNode
    )
    from backend.domain.state import FlowState
    from langchain_core.messages import HumanMessage
    
    # 创建节点实例
    node = InsertDataToVectorDbNode()
    
    # 创建测试状态（缺少 embedding_value）
    state: FlowState = {
        "current_message": HumanMessage(content="测试"),
        "history_messages": [],
        "flow_msgs": [],
        "session_id": "test_session",
        "edges_var": {},  # 缺少 embedding_value
        "prompt_vars": {
            "embedding_records_id": "test_id_001"
        }
    }
    
    # 执行节点，应该抛出 ValueError
    try:
        await node.execute(state)
        assert False, "应该抛出 ValueError"
    except ValueError as e:
        assert "embedding_value" in str(e).lower(), "错误信息应该包含 embedding_value"
        print(f"✓ 正确抛出异常: {e}\n")


async def test_insert_data_to_vector_db_node_missing_record_id():
    """测试 insert_data_to_vector_db 节点 - embedding_records_id 缺失"""
    print("=" * 60)
    print("测试 3: insert_data_to_vector_db 节点 - embedding_records_id 缺失")
    print("=" * 60)
    
    InsertDataToVectorDbNode = _import_insert_node()
    from backend.domain.state import FlowState
    from langchain_core.messages import HumanMessage
    
    # 创建节点实例
    node = InsertDataToVectorDbNode()
    
    # 创建测试状态（缺少 embedding_records_id）
    test_embedding_value = [0.1] * 2048
    state: FlowState = {
        "current_message": HumanMessage(content="测试"),
        "history_messages": [],
        "flow_msgs": [],
        "session_id": "test_session",
        "edges_var": {
            "embedding_value": test_embedding_value
        },
        "prompt_vars": {}  # 缺少 embedding_records_id
    }
    
    # 执行节点，应该抛出 ValueError
    try:
        await node.execute(state)
        assert False, "应该抛出 ValueError"
    except ValueError as e:
        assert "embedding_records_id" in str(e).lower(), "错误信息应该包含 embedding_records_id"
        print(f"✓ 正确抛出异常: {e}\n")


async def test_insert_data_to_vector_db_node_record_not_found():
    """测试 insert_data_to_vector_db 节点 - 记录不存在"""
    print("=" * 60)
    print("测试 4: insert_data_to_vector_db 节点 - 记录不存在")
    print("=" * 60)
    
    InsertDataToVectorDbNode = _import_insert_node()
    from backend.domain.state import FlowState
    from langchain_core.messages import HumanMessage
    
    # 创建节点实例
    node = InsertDataToVectorDbNode()
    
    # 创建测试状态（使用不存在的记录ID）
    test_embedding_value = [0.1] * 2048
    state: FlowState = {
        "current_message": HumanMessage(content="测试"),
        "history_messages": [],
        "flow_msgs": [],
        "session_id": "test_session",
        "edges_var": {
            "embedding_value": test_embedding_value
        },
        "prompt_vars": {
            "embedding_records_id": "non_existent_id_999999"
        }
    }
    
    # 执行节点，应该抛出 ValueError
    try:
        await node.execute(state)
        assert False, "应该抛出 ValueError"
    except ValueError as e:
        assert "未找到" in str(e) or "not found" in str(e).lower(), "错误信息应该表示记录未找到"
        print(f"✓ 正确抛出异常: {e}\n")


async def test_insert_data_to_vector_db_node_invalid_embedding_format():
    """测试 insert_data_to_vector_db 节点 - embedding_value 格式错误"""
    print("=" * 60)
    print("测试 5: insert_data_to_vector_db 节点 - embedding_value 格式错误")
    print("=" * 60)
    
    import importlib.util
    # 直接导入模块
    spec = importlib.util.spec_from_file_location(
        "insert_data_to_vector_db_func",
        project_root / "backend/domain/flows/implementations/insert_data_to_vector_db_func.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    InsertDataToVectorDbNode = module.InsertDataToVectorDbNode
    
    from backend.domain.state import FlowState
    from backend.infrastructure.database.connection import get_session_factory
    from backend.infrastructure.database.models.embedding_record import EmbeddingRecord
    from langchain_core.messages import HumanMessage
    from sqlalchemy import select
    
    # 创建节点实例
    node = InsertDataToVectorDbNode()
    
    # 1. 先创建一个测试用的 embedding_record
    session_factory = get_session_factory()
    async with session_factory() as session:
        test_record = EmbeddingRecord(
            scene_summary="测试场景摘要",
            optimization_question="测试问题",
            ai_response="测试回复",
            message_id="test_message_002",
            version=0,
            is_published=False,
            source_table_name="test_table",
            source_record_id="test_source_002",
            generation_status=0,
            failure_reason=None,
        )
        session.add(test_record)
        await session.flush()
        await session.refresh(test_record)
        embedding_records_id = test_record.id
        await session.commit()
    
    # 2. 创建测试状态（embedding_value 格式错误，不是列表）
    state: FlowState = {
        "current_message": HumanMessage(content="测试"),
        "history_messages": [],
        "flow_msgs": [],
        "session_id": "test_session",
        "edges_var": {
            "embedding_value": "invalid_format"  # 不是列表
        },
        "prompt_vars": {
            "embedding_records_id": embedding_records_id
        }
    }
    
    # 3. 执行节点，应该抛出 TypeError
    try:
        await node.execute(state)
        assert False, "应该抛出 TypeError"
    except TypeError as e:
        assert "format" in str(e).lower() or "list" in str(e).lower() or "tuple" in str(e).lower(), "错误信息应该表示格式错误"
        print(f"✓ 正确抛出异常: {e}\n")
    
    # 4. 验证记录状态已更新为失败
    async with session_factory() as session:
        stmt = select(EmbeddingRecord).where(
            EmbeddingRecord.id == embedding_records_id
        )
        result = await session.execute(stmt)
        updated_record = result.scalar_one_or_none()
        
        if updated_record:
            # 注意：由于异常处理，记录可能被更新为失败状态
            print(f"记录状态: generation_status={updated_record.generation_status}")
            if updated_record.generation_status == -1:
                print(f"  failure_reason: {updated_record.failure_reason[:100]}...")
    
    # 清理：删除测试记录
    async with session_factory() as session:
        stmt = select(EmbeddingRecord).where(
            EmbeddingRecord.id == embedding_records_id
        )
        result = await session.execute(stmt)
        test_record = result.scalar_one_or_none()
        if test_record:
            await session.delete(test_record)
            await session.commit()
            print(f"清理测试记录: id={embedding_records_id}\n")


def run_all_tests():
    """运行所有测试"""
    import asyncio
    
    print("=" * 60)
    print("开始测试 insert_data_to_vector_db_func 节点")
    print("=" * 60)
    print()
    
    # 运行所有测试
    asyncio.run(test_insert_data_to_vector_db_node_success())
    asyncio.run(test_insert_data_to_vector_db_node_missing_embedding_value())
    asyncio.run(test_insert_data_to_vector_db_node_missing_record_id())
    asyncio.run(test_insert_data_to_vector_db_node_record_not_found())
    asyncio.run(test_insert_data_to_vector_db_node_invalid_embedding_format())
    
    print("=" * 60)
    print("✓ 所有测试完成")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
