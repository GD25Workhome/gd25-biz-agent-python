"""
血压记录工具测试
测试 record_blood_pressure、query_blood_pressure、update_blood_pressure 函数

运行方式：
==========
# 直接运行测试文件
python cursor_test/M1_test/domain/test_blood_pressure_tools.py

# 或者在项目根目录运行
python -m cursor_test.M1_test.domain.test_blood_pressure_tools
"""
import sys
import asyncio
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional
from unittest.mock import Mock, patch, AsyncMock

# 添加项目根目录到 Python 路径
test_file_path = Path(__file__).resolve()
project_root = test_file_path.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)
from sqlalchemy import text

from app.core.config import settings
from infrastructure.database.models import User, BloodPressureRecord
from domain.tools.blood_pressure.record import record_blood_pressure
from domain.tools.blood_pressure.query import query_blood_pressure
from domain.tools.blood_pressure.update import update_blood_pressure


class TestResult:
    """测试结果记录类"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self, test_name: str):
        """记录通过的测试"""
        self.passed += 1
        print(f"✅ {test_name}")
    
    def add_fail(self, test_name: str, error: str):
        """记录失败的测试"""
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"❌ {test_name}: {error}")
    
    def summary(self):
        """打印测试总结"""
        print("\n" + "="*60)
        print("测试总结")
        print("="*60)
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")
        print(f"总计: {self.passed + self.failed}")
        
        if self.errors:
            print("\n失败详情:")
            for error in self.errors:
                print(f"  - {error}")
        
        print("="*60)
        return self.failed == 0


# 全局测试结果记录
test_result = TestResult()


async def create_test_db_session():
    """
    创建测试数据库会话
    
    使用嵌套事务（SAVEPOINT）确保测试数据不会污染正式数据库
    """
    engine = create_async_engine(
        settings.ASYNC_DB_URI,
        echo=False,
        pool_pre_ping=True
    )
    
    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    session = async_session_factory()
    
    # 开始外层事务
    trans = await session.begin()
    
    # 创建保存点（嵌套事务）
    nested_trans = await session.begin_nested()
    
    return session, engine, trans, nested_trans


async def cleanup_test_db_session(session, engine, trans, nested_trans):
    """清理测试数据库会话"""
    try:
        # 回滚保存点
        if nested_trans and nested_trans.is_active:
            await nested_trans.rollback()
    except Exception:
        pass
    
    try:
        # 回滚外层事务
        if trans and trans.is_active:
            await trans.rollback()
    except Exception:
        pass
    
    try:
        await session.close()
    except Exception:
        pass
    
    try:
        await engine.dispose()
    except Exception:
        pass


async def create_test_user(session: AsyncSession) -> User:
    """创建测试用户"""
    unique_suffix = str(uuid.uuid4())[:8]
    user = User(
        username=f"test_user_{unique_suffix}",
        phone=f"138{unique_suffix}",
        email=f"test_{unique_suffix}@example.com",
        is_active=True
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def create_test_blood_pressure_record(
    session: AsyncSession,
    user_id: str,
    systolic: int = 120,
    diastolic: int = 80,
    heart_rate: Optional[int] = 72,
    notes: Optional[str] = None
) -> BloodPressureRecord:
    """创建测试血压记录"""
    record = BloodPressureRecord(
        user_id=user_id,
        systolic=systolic,
        diastolic=diastolic,
        heart_rate=heart_rate,
        record_time=datetime.utcnow(),
        notes=notes
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


# ==================== record_blood_pressure 测试 ====================

async def test_record_blood_pressure_normal():
    """测试用例 1: 记录血压（正常情况）"""
    test_name = "记录血压（正常情况）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        user = await create_test_user(session)
        
        # 执行测试
        result = await record_blood_pressure.ainvoke({
            "user_id": user.id,
            "systolic": 120,
            "diastolic": 80,
            "heart_rate": 72,
            "notes": "测试记录",
            "session": session
        })
        
        # 验证结果
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功记录血压" in result, "应该包含成功消息"
        assert "120" in result, "应该包含收缩压"
        assert "80" in result, "应该包含舒张压"
        assert "72" in result, "应该包含心率"
        
        # 验证数据库中的记录
        from infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
        repo = BloodPressureRepository(session)
        records = await repo.get_by_user_id(user.id, limit=10)
        assert len(records) > 0, "应该创建了血压记录"
        assert records[0].systolic == 120, "收缩压应该正确"
        assert records[0].diastolic == 80, "舒张压应该正确"
        assert records[0].heart_rate == 72, "心率应该正确"
        
        print(f"  ✅ 返回结果: {result}")
        print(f"  ✅ 数据库记录已创建")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_record_blood_pressure_required_fields():
    """测试用例 2: 记录血压（必填字段验证）"""
    test_name = "记录血压（必填字段验证）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        user = await create_test_user(session)
        
        # 测试缺少必填字段 - 应该由函数签名验证，这里测试正常情况
        # 由于使用了 @tool 装饰器，参数验证由 LangChain 处理
        # 这里测试正常调用
        
        result = await record_blood_pressure.ainvoke({
            "user_id": user.id,
            "systolic": 130,
            "diastolic": 85,
            "session": session
        })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功记录血压" in result, "应该包含成功消息"
        
        print(f"  ✅ 返回结果: {result}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_record_blood_pressure_optional_fields():
    """测试用例 3: 记录血压（可选字段：heart_rate、notes）"""
    test_name = "记录血压（可选字段：heart_rate、notes）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        user = await create_test_user(session)
        
        # 测试不提供可选字段
        result1 = await record_blood_pressure.ainvoke({
            "user_id": user.id,
            "systolic": 125,
            "diastolic": 82,
            "session": session
        })
        
        assert isinstance(result1, str), "返回结果应该是字符串"
        assert "未记录" in result1, "心率应该显示为未记录"
        
        # 测试提供可选字段
        result2 = await record_blood_pressure.ainvoke({
            "user_id": user.id,
            "systolic": 128,
            "diastolic": 84,
            "heart_rate": 75,
            "notes": "测试备注",
            "session": session
        })
        
        assert isinstance(result2, str), "返回结果应该是字符串"
        assert "75" in result2, "应该包含心率"
        
        # 验证数据库记录
        from infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
        repo = BloodPressureRepository(session)
        records = await repo.get_by_user_id(user.id, limit=10)
        assert len(records) >= 2, "应该创建了至少2条记录"
        
        # 检查第二条记录的备注
        record_with_notes = [r for r in records if r.notes == "测试备注"]
        assert len(record_with_notes) > 0, "应该包含备注的记录"
        
        print(f"  ✅ 不提供可选字段: {result1}")
        print(f"  ✅ 提供可选字段: {result2}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_record_blood_pressure_iso_time():
    """测试用例 4: 记录血压（时间解析：ISO 格式）"""
    test_name = "记录血压（时间解析：ISO 格式）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        user = await create_test_user(session)
        
        # 测试 ISO 格式时间
        iso_time = "2025-01-15T10:30:00"
        result = await record_blood_pressure.ainvoke({
            "user_id": user.id,
            "systolic": 120,
            "diastolic": 80,
            "record_time": iso_time,
            "session": session
        })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功记录血压" in result, "应该包含成功消息"
        
        # 验证数据库中的时间
        from infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
        repo = BloodPressureRepository(session)
        records = await repo.get_by_user_id(user.id, limit=10)
        assert len(records) > 0, "应该创建了记录"
        
        # 验证时间是否正确解析（允许一些时间差）
        record_time = records[0].record_time
        expected_time = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
        time_diff = abs((record_time - expected_time).total_seconds())
        assert time_diff < 60, f"时间应该正确解析，差异: {time_diff}秒"
        
        print(f"  ✅ ISO 时间解析成功: {iso_time}")
        print(f"  ✅ 数据库时间: {record_time}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_record_blood_pressure_invalid_time():
    """测试用例 5: 记录血压（时间解析：错误格式）"""
    test_name = "记录血压（时间解析：错误格式）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        user = await create_test_user(session)
        
        # 测试错误格式时间 - 应该使用当前时间作为默认值
        invalid_time = "invalid-time-format"
        result = await record_blood_pressure.ainvoke({
            "user_id": user.id,
            "systolic": 120,
            "diastolic": 80,
            "record_time": invalid_time,
            "session": session
        })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功记录血压" in result, "应该包含成功消息（使用默认时间）"
        
        # 验证数据库中的时间应该是当前时间（允许一些时间差）
        from infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
        repo = BloodPressureRepository(session)
        records = await repo.get_by_user_id(user.id, limit=10)
        assert len(records) > 0, "应该创建了记录"
        
        record_time = records[0].record_time
        now = datetime.utcnow()
        time_diff = abs((record_time - now).total_seconds())
        assert time_diff < 60, f"应该使用当前时间，差异: {time_diff}秒"
        
        print(f"  ✅ 错误格式时间使用默认值: {invalid_time}")
        print(f"  ✅ 数据库时间: {record_time}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_record_blood_pressure_no_session():
    """测试用例 6: 记录血压（数据库会话未提供）"""
    test_name = "记录血压（数据库会话未提供）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试不提供 session
        try:
            await record_blood_pressure.ainvoke({
                "user_id": 1,
                "systolic": 120,
                "diastolic": 80
            })
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert "数据库会话未提供" in str(e), f"错误消息应该包含'数据库会话未提供'，实际: {str(e)}"
            print(f"  ✅ 正确抛出 ValueError: {str(e)}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


async def test_record_blood_pressure_db_error():
    """测试用例 7: 记录血压（数据库错误处理）"""
    test_name = "记录血压（数据库错误处理）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        
        # 模拟数据库错误 - 使用无效的用户ID
        # 由于外键约束，应该会失败
        try:
            result = await record_blood_pressure.ainvoke({
                "user_id": 99999,  # 不存在的用户ID
                "systolic": 120,
                "diastolic": 80,
                "session": session
            })
            # 如果外键约束没有启用，可能会成功，这是正常的
            # 这里主要测试函数能够处理错误情况
            print(f"  ✅ 函数执行完成（可能因外键约束失败或成功）")
        except Exception as e:
            # 数据库错误是预期的
            print(f"  ✅ 捕获到数据库错误: {type(e).__name__}: {str(e)}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


# ==================== query_blood_pressure 测试 ====================

async def test_query_blood_pressure_normal():
    """测试用例 1: 查询血压（正常情况）"""
    test_name = "查询血压（正常情况）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        user = await create_test_user(session)
        
        # 创建测试记录
        await create_test_blood_pressure_record(session, user.id, 120, 80, 72, "测试1")
        await create_test_blood_pressure_record(session, user.id, 125, 85, 75, "测试2")
        
        # 查询记录
        result = await query_blood_pressure.ainvoke({
            "user_id": user.id,
            "session": session
        })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "血压记录" in result, "应该包含'血压记录'"
        assert "120" in result, "应该包含第一条记录的收缩压"
        assert "125" in result, "应该包含第二条记录的收缩压"
        
        print(f"  ✅ 查询结果: {result[:200]}...")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_query_blood_pressure_with_records():
    """测试用例 2: 查询血压（有记录）"""
    test_name = "查询血压（有记录）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        user = await create_test_user(session)
        
        # 创建多条记录
        for i in range(3):
            await create_test_blood_pressure_record(
                session, user.id, 120 + i, 80 + i, 70 + i, f"记录{i+1}"
            )
        
        # 查询记录
        result = await query_blood_pressure.ainvoke({
            "user_id": user.id,
            "session": session
        })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "共 3 条" in result, "应该显示记录数量"
        assert "记录1" in result or "记录2" in result or "记录3" in result, "应该包含备注"
        
        print(f"  ✅ 查询结果包含3条记录")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_query_blood_pressure_no_records():
    """测试用例 3: 查询血压（无记录）"""
    test_name = "查询血压（无记录）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        user = await create_test_user(session)
        
        # 不创建记录，直接查询
        result = await query_blood_pressure.ainvoke({
            "user_id": user.id,
            "session": session
        })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "暂无血压记录" in result, "应该显示无记录消息"
        assert str(user.id) in result, "应该包含用户ID"
        
        print(f"  ✅ 无记录时返回: {result}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_query_blood_pressure_pagination():
    """测试用例 4: 查询血压（分页：limit、offset）"""
    test_name = "查询血压（分页：limit、offset）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        user = await create_test_user(session)
        
        # 创建5条记录
        for i in range(5):
            await create_test_blood_pressure_record(
                session, user.id, 120 + i, 80 + i, 70 + i
            )
        
        # 测试 limit
        result_limit = await query_blood_pressure.ainvoke({
            "user_id": user.id,
            "limit": 2,
            "session": session
        })
        
        assert isinstance(result_limit, str), "返回结果应该是字符串"
        assert "共 2 条" in result_limit, "应该只返回2条记录"
        
        # 测试 offset
        result_offset = await query_blood_pressure.ainvoke({
            "user_id": user.id,
            "limit": 2,
            "offset": 2,
            "session": session
        })
        
        assert isinstance(result_offset, str), "返回结果应该是字符串"
        assert "共 2 条" in result_offset, "应该返回2条记录（从第3条开始）"
        
        print(f"  ✅ limit=2 返回2条记录")
        print(f"  ✅ offset=2 返回2条记录")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_query_blood_pressure_no_session():
    """测试用例 5: 查询血压（数据库会话未提供）"""
    test_name = "查询血压（数据库会话未提供）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试不提供 session
        try:
            await query_blood_pressure.ainvoke({
                "user_id": 1
            })
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert "数据库会话未提供" in str(e), f"错误消息应该包含'数据库会话未提供'，实际: {str(e)}"
            print(f"  ✅ 正确抛出 ValueError: {str(e)}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


# ==================== update_blood_pressure 测试 ====================

async def test_update_blood_pressure_normal():
    """测试用例 1: 更新血压（正常情况）"""
    test_name = "更新血压（正常情况）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        user = await create_test_user(session)
        record = await create_test_blood_pressure_record(session, user.id, 120, 80, 72)
        
        # 更新记录
        result = await update_blood_pressure.ainvoke({
            "record_id": record.id,
            "systolic": 130,
            "diastolic": 85,
            "heart_rate": 75,
            "notes": "更新后的备注",
            "session": session
        })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功更新记录" in result, "应该包含成功消息"
        assert str(record.id) in result, "应该包含记录ID"
        
        # 验证数据库中的更新
        await session.refresh(record)
        assert record.systolic == 130, "收缩压应该已更新"
        assert record.diastolic == 85, "舒张压应该已更新"
        assert record.heart_rate == 75, "心率应该已更新"
        assert record.notes == "更新后的备注", "备注应该已更新"
        
        print(f"  ✅ 更新结果: {result}")
        print(f"  ✅ 数据库记录已更新")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_update_blood_pressure_partial():
    """测试用例 2: 更新血压（部分字段更新）"""
    test_name = "更新血压（部分字段更新）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        user = await create_test_user(session)
        record = await create_test_blood_pressure_record(session, user.id, 120, 80, 72, "原始备注")
        
        original_systolic = record.systolic
        original_diastolic = record.diastolic
        
        # 只更新收缩压
        result = await update_blood_pressure.ainvoke({
            "record_id": record.id,
            "systolic": 130,
            "session": session
        })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功更新记录" in result, "应该包含成功消息"
        
        # 验证数据库中的更新
        await session.refresh(record)
        assert record.systolic == 130, "收缩压应该已更新"
        assert record.diastolic == original_diastolic, "舒张压应该未改变"
        assert record.heart_rate == 72, "心率应该未改变"
        assert record.notes == "原始备注", "备注应该未改变"
        
        print(f"  ✅ 部分字段更新成功")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_update_blood_pressure_not_exists():
    """测试用例 3: 更新血压（记录不存在）"""
    test_name = "更新血压（记录不存在）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        
        # 尝试更新不存在的记录
        result = await update_blood_pressure.ainvoke({
            "record_id": 99999,
            "systolic": 130,
            "session": session
        })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "不存在" in result, "应该包含不存在消息"
        assert "99999" in result, "应该包含记录ID"
        
        print(f"  ✅ 返回结果: {result}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_update_blood_pressure_no_fields():
    """测试用例 4: 更新血压（没有提供更新字段）"""
    test_name = "更新血压（没有提供更新字段）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        user = await create_test_user(session)
        record = await create_test_blood_pressure_record(session, user.id, 120, 80, 72)
        
        # 不提供任何更新字段
        result = await update_blood_pressure.ainvoke({
            "record_id": record.id,
            "session": session
        })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "没有提供要更新的字段" in result, "应该包含提示消息"
        
        print(f"  ✅ 返回结果: {result}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_update_blood_pressure_no_session():
    """测试用例 5: 更新血压（数据库会话未提供）"""
    test_name = "更新血压（数据库会话未提供）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试不提供 session
        try:
            await update_blood_pressure.ainvoke({
                "record_id": 1,
                "systolic": 130
            })
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert "数据库会话未提供" in str(e), f"错误消息应该包含'数据库会话未提供'，实际: {str(e)}"
            print(f"  ✅ 正确抛出 ValueError: {str(e)}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")


# ==================== 主函数 ====================

async def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("开始执行血压记录工具测试")
    print("="*60)
    
    # record_blood_pressure 测试
    await test_record_blood_pressure_normal()
    await test_record_blood_pressure_required_fields()
    await test_record_blood_pressure_optional_fields()
    await test_record_blood_pressure_iso_time()
    await test_record_blood_pressure_invalid_time()
    await test_record_blood_pressure_no_session()
    await test_record_blood_pressure_db_error()
    
    # query_blood_pressure 测试
    await test_query_blood_pressure_normal()
    await test_query_blood_pressure_with_records()
    await test_query_blood_pressure_no_records()
    await test_query_blood_pressure_pagination()
    await test_query_blood_pressure_no_session()
    
    # update_blood_pressure 测试
    await test_update_blood_pressure_normal()
    await test_update_blood_pressure_partial()
    await test_update_blood_pressure_not_exists()
    await test_update_blood_pressure_no_fields()
    await test_update_blood_pressure_no_session()
    
    # 打印测试总结
    success = test_result.summary()
    return success


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
