"""
预约管理工具测试
测试 create_appointment、query_appointment、update_appointment 函数

运行方式：
==========
# 直接运行测试文件
python cursor_test/M1_test/domain/test_appointment_tools.py

# 或者在项目根目录运行
python -m cursor_test.M1_test.domain.test_appointment_tools
"""
import sys
import asyncio
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional
from unittest.mock import Mock, patch, AsyncMock, MagicMock

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
from infrastructure.database.models import User, Appointment
from infrastructure.database.models.appointment import AppointmentStatus
from domain.tools.appointment.create import create_appointment
from domain.tools.appointment.query import query_appointment
from domain.tools.appointment.update import update_appointment


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


async def create_test_appointment(
    session: AsyncSession,
    user_id: str,
    department: str = "内科",
    doctor_name: Optional[str] = "张医生",
    appointment_time: Optional[datetime] = None,
    status: AppointmentStatus = AppointmentStatus.PENDING,
    notes: Optional[str] = None
) -> Appointment:
    """创建测试预约"""
    if appointment_time is None:
        appointment_time = datetime.utcnow()
    
    appointment = Appointment(
        user_id=user_id,
        department=department,
        doctor_name=doctor_name,
        appointment_time=appointment_time,
        status=status,
        notes=notes
    )
    session.add(appointment)
    await session.flush()
    await session.refresh(appointment)
    return appointment


# ==================== create_appointment 测试 ====================

async def test_create_appointment_local_db():
    """测试用例 1: 创建预约（正常情况，使用本地数据库）"""
    test_name = "创建预约（正常情况，使用本地数据库）"
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
        
        # 模拟没有配置 Java 微服务
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await create_appointment.ainvoke({
                "user_id": user.id,
                "department": "内科",
                "appointment_time": "2025-01-15T10:00:00",
                "doctor_name": "张医生",
                "notes": "测试预约",
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功创建预约" in result, "应该包含成功消息"
        assert "内科" in result, "应该包含科室"
        assert "张医生" in result, "应该包含医生姓名"
        
        # 验证数据库中的记录
        from infrastructure.database.repository.appointment_repository import AppointmentRepository
        repo = AppointmentRepository(session)
        appointments = await repo.get_by_user_id(user.id, limit=10)
        assert len(appointments) > 0, "应该创建了预约记录"
        assert appointments[0].department == "内科", "科室应该正确"
        assert appointments[0].doctor_name == "张医生", "医生姓名应该正确"
        assert appointments[0].status == AppointmentStatus.PENDING, "状态应该是PENDING"
        
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


async def test_create_appointment_java_service():
    """测试用例 2: 创建预约（使用 Java 微服务）"""
    test_name = "创建预约（使用 Java 微服务）"
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
        
        # 模拟 Java 微服务响应
    mock_response = {
        "id": "1",
            "userId": user.id,
            "department": "内科",
            "appointmentTime": "2025-01-15T10:00:00",
            "status": "pending"
        }
        
        # 模拟配置了 Java 微服务
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', 'http://localhost:8080'):
            with patch('domain.tools.appointment.create.JavaServiceClient') as MockClient:
                mock_client = AsyncMock()
                mock_client.create_appointment = AsyncMock(return_value=mock_response)
                MockClient.return_value = mock_client
                
                result = await create_appointment.ainvoke({
                    "user_id": user.id,
                    "department": "内科",
                    "appointment_time": "2025-01-15T10:00:00",
                    "doctor_name": "张医生",
                    "session": session
                })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功创建预约" in result, "应该包含成功消息"
        
        # 验证调用了 Java 微服务
        mock_client.create_appointment.assert_called_once()
        
        print(f"  ✅ 返回结果: {result}")
        print(f"  ✅ Java 微服务已调用")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_create_appointment_java_service_fallback():
    """测试用例 3: 创建预约（Java 微服务失败，降级到本地数据库）"""
    test_name = "创建预约（Java 微服务失败，降级到本地数据库）"
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
        
        # 模拟 Java 微服务失败
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', 'http://localhost:8080'):
            with patch('domain.tools.appointment.create.JavaServiceClient') as MockClient:
                mock_client = AsyncMock()
                mock_client.create_appointment = AsyncMock(side_effect=Exception("服务不可用"))
                MockClient.return_value = mock_client
                
                result = await create_appointment.ainvoke({
                    "user_id": user.id,
                    "department": "内科",
                    "appointment_time": "2025-01-15T10:00:00",
                    "doctor_name": "张医生",
                    "session": session
                })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功创建预约" in result, "应该包含成功消息（降级到本地数据库）"
        
        # 验证数据库中的记录（降级创建）
        from infrastructure.database.repository.appointment_repository import AppointmentRepository
        repo = AppointmentRepository(session)
        appointments = await repo.get_by_user_id(user.id, limit=10)
        assert len(appointments) > 0, "应该创建了预约记录（降级）"
        
        print(f"  ✅ 返回结果: {result}")
        print(f"  ✅ 降级到本地数据库成功")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_create_appointment_required_fields():
    """测试用例 4: 创建预约（必填字段验证）"""
    test_name = "创建预约（必填字段验证）"
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
        
        # 测试正常调用（必填字段由函数签名验证）
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await create_appointment.ainvoke({
                "user_id": user.id,
                "department": "内科",
                "appointment_time": "2025-01-15T10:00:00",
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功创建预约" in result, "应该包含成功消息"
        
        print(f"  ✅ 必填字段验证通过")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_create_appointment_iso_time():
    """测试用例 5: 创建预约（时间解析：ISO 格式）"""
    test_name = "创建预约（时间解析：ISO 格式）"
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
        
        iso_time = "2025-01-15T10:30:00"
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await create_appointment.ainvoke({
                "user_id": user.id,
                "department": "内科",
                "appointment_time": iso_time,
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功创建预约" in result, "应该包含成功消息"
        
        # 验证数据库中的时间
        from infrastructure.database.repository.appointment_repository import AppointmentRepository
        repo = AppointmentRepository(session)
        appointments = await repo.get_by_user_id(user.id, limit=10)
        assert len(appointments) > 0, "应该创建了记录"
        
        appointment_time = appointments[0].appointment_time
        expected_time = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
        time_diff = abs((appointment_time - expected_time).total_seconds())
        assert time_diff < 60, f"时间应该正确解析，差异: {time_diff}秒"
        
        print(f"  ✅ ISO 时间解析成功: {iso_time}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_create_appointment_invalid_time():
    """测试用例 6: 创建预约（时间解析：错误格式）"""
    test_name = "创建预约（时间解析：错误格式）"
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
        
        invalid_time = "invalid-time-format"
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await create_appointment.ainvoke({
                "user_id": user.id,
                "department": "内科",
                "appointment_time": invalid_time,
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "预约时间格式错误" in result, "应该包含格式错误消息"
        assert invalid_time in result, "应该包含错误的时间格式"
        
        print(f"  ✅ 错误格式时间处理: {result}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_create_appointment_no_session():
    """测试用例 7: 创建预约（数据库会话未提供）"""
    test_name = "创建预约（数据库会话未提供）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试不提供 session
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            try:
                await create_appointment.ainvoke({
                    "user_id": 1,
                    "department": "内科",
                    "appointment_time": "2025-01-15T10:00:00"
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


# ==================== query_appointment 测试 ====================

async def test_query_appointment_single():
    """测试用例 1: 查询预约（查询单个预约）"""
    test_name = "查询预约（查询单个预约）"
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
        appointment = await create_test_appointment(session, user.id, "内科", "张医生")
        
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await query_appointment.ainvoke({
                "user_id": user.id,
                "appointment_id": appointment.id,
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "预约信息" in result, "应该包含预约信息"
        assert str(appointment.id) in result, "应该包含预约ID"
        assert "内科" in result, "应该包含科室"
        assert "张医生" in result, "应该包含医生姓名"
        
        print(f"  ✅ 查询结果: {result[:200]}...")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_query_appointment_all():
    """测试用例 2: 查询预约（查询用户所有预约）"""
    test_name = "查询预约（查询用户所有预约）"
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
        
        # 创建多条预约
        await create_test_appointment(session, user.id, "内科", "张医生")
        await create_test_appointment(session, user.id, "外科", "李医生")
        
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await query_appointment.ainvoke({
                "user_id": user.id,
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "预约记录" in result, "应该包含预约记录"
        assert "共 2 条" in result, "应该显示记录数量"
        assert "内科" in result, "应该包含第一条预约的科室"
        assert "外科" in result, "应该包含第二条预约的科室"
        
        print(f"  ✅ 查询结果包含2条记录")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_query_appointment_java_service():
    """测试用例 3: 查询预约（使用 Java 微服务）"""
    test_name = "查询预约（使用 Java 微服务）"
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
        
        # 模拟 Java 微服务响应
    mock_response = {
        "id": "1",
        "userId": str(user.id),
            "department": "内科",
            "appointmentTime": "2025-01-15T10:00:00",
            "status": "pending"
        }
        
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', 'http://localhost:8080'):
            with patch('domain.tools.appointment.query.JavaServiceClient') as MockClient:
                mock_client = AsyncMock()
                mock_client.query_appointment = AsyncMock(return_value=mock_response)
                MockClient.return_value = mock_client
                
                result = await query_appointment.ainvoke({
                    "user_id": user.id,
                "appointment_id": str(appointment.id),
                    "session": session
                })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "预约信息" in result, "应该包含预约信息"
        
        # 验证调用了 Java 微服务
        mock_client.query_appointment.assert_called_once()
        
        print(f"  ✅ 返回结果: {result}")
        print(f"  ✅ Java 微服务已调用")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_query_appointment_java_service_fallback():
    """测试用例 4: 查询预约（Java 微服务失败，降级到本地数据库）"""
    test_name = "查询预约（Java 微服务失败，降级到本地数据库）"
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
        appointment = await create_test_appointment(session, user.id, "内科", "张医生")
        
        # 模拟 Java 微服务失败
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', 'http://localhost:8080'):
            with patch('domain.tools.appointment.query.JavaServiceClient') as MockClient:
                mock_client = AsyncMock()
                mock_client.query_appointment = AsyncMock(side_effect=Exception("服务不可用"))
                MockClient.return_value = mock_client
                
                result = await query_appointment.ainvoke({
                    "user_id": user.id,
                    "appointment_id": appointment.id,
                    "session": session
                })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "预约信息" in result, "应该包含预约信息（降级到本地数据库）"
        assert str(appointment.id) in result, "应该包含预约ID"
        
        print(f"  ✅ 返回结果: {result[:200]}...")
        print(f"  ✅ 降级到本地数据库成功")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_query_appointment_not_exists():
    """测试用例 5: 查询预约（预约不存在）"""
    test_name = "查询预约（预约不存在）"
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
        
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await query_appointment.ainvoke({
                "user_id": user.id,
                "appointment_id": "99999",
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "不存在" in result, "应该包含不存在消息"
        assert "99999" in result, "应该包含预约ID"
        
        print(f"  ✅ 返回结果: {result}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_query_appointment_no_records():
    """测试用例 6: 查询预约（无记录）"""
    test_name = "查询预约（无记录）"
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
        
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await query_appointment.ainvoke({
                "user_id": user.id,
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "暂无预约记录" in result, "应该显示无记录消息"
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


async def test_query_appointment_no_session():
    """测试用例 7: 查询预约（数据库会话未提供）"""
    test_name = "查询预约（数据库会话未提供）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试不提供 session
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            try:
                await query_appointment.ainvoke({
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


# ==================== update_appointment 测试 ====================

async def test_update_appointment_local_db():
    """测试用例 1: 更新预约（正常情况，使用本地数据库）"""
    test_name = "更新预约（正常情况，使用本地数据库）"
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
        appointment = await create_test_appointment(session, user.id, "内科", "张医生")
        
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await update_appointment.ainvoke({
                "appointment_id": appointment.id,
                "department": "外科",
                "doctor_name": "李医生",
                "notes": "更新后的备注",
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功更新预约" in result, "应该包含成功消息"
        assert str(appointment.id) in result, "应该包含预约ID"
        
        # 验证数据库中的更新
        await session.refresh(appointment)
        assert appointment.department == "外科", "科室应该已更新"
        assert appointment.doctor_name == "李医生", "医生姓名应该已更新"
        assert appointment.notes == "更新后的备注", "备注应该已更新"
        
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


async def test_update_appointment_java_service():
    """测试用例 2: 更新预约（使用 Java 微服务）"""
    test_name = "更新预约（使用 Java 微服务）"
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
        appointment = await create_test_appointment(session, user.id, "内科", "张医生")
        
        # 模拟 Java 微服务响应
        mock_response = {
            "id": appointment.id,
            "department": "外科",
            "status": "confirmed"
        }
        
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', 'http://localhost:8080'):
            with patch('domain.tools.appointment.update.JavaServiceClient') as MockClient:
                mock_client = AsyncMock()
                mock_client.update_appointment = AsyncMock(return_value=mock_response)
                MockClient.return_value = mock_client
                
                result = await update_appointment.ainvoke({
                    "appointment_id": appointment.id,
                    "department": "外科",
                    "session": session
                })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功更新预约" in result, "应该包含成功消息"
        
        # 验证调用了 Java 微服务
        mock_client.update_appointment.assert_called_once()
        
        print(f"  ✅ 返回结果: {result}")
        print(f"  ✅ Java 微服务已调用")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_update_appointment_java_service_fallback():
    """测试用例 3: 更新预约（Java 微服务失败，降级到本地数据库）"""
    test_name = "更新预约（Java 微服务失败，降级到本地数据库）"
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
        appointment = await create_test_appointment(session, user.id, "内科", "张医生")
        
        # 模拟 Java 微服务失败
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', 'http://localhost:8080'):
            with patch('domain.tools.appointment.update.JavaServiceClient') as MockClient:
                mock_client = AsyncMock()
                mock_client.update_appointment = AsyncMock(side_effect=Exception("服务不可用"))
                MockClient.return_value = mock_client
                
                result = await update_appointment.ainvoke({
                    "appointment_id": appointment.id,
                    "department": "外科",
                    "session": session
                })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功更新预约" in result, "应该包含成功消息（降级到本地数据库）"
        
        # 验证数据库中的更新（降级）
        await session.refresh(appointment)
        assert appointment.department == "外科", "科室应该已更新（降级）"
        
        print(f"  ✅ 返回结果: {result}")
        print(f"  ✅ 降级到本地数据库成功")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_update_appointment_partial():
    """测试用例 4: 更新预约（部分字段更新）"""
    test_name = "更新预约（部分字段更新）"
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
        appointment = await create_test_appointment(session, user.id, "内科", "张医生", notes="原始备注")
        
        original_department = appointment.department
        
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await update_appointment.ainvoke({
                "appointment_id": appointment.id,
                "doctor_name": "王医生",
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功更新预约" in result, "应该包含成功消息"
        
        # 验证数据库中的更新
        await session.refresh(appointment)
        assert appointment.doctor_name == "王医生", "医生姓名应该已更新"
        assert appointment.department == original_department, "科室应该未改变"
        assert appointment.notes == "原始备注", "备注应该未改变"
        
        print(f"  ✅ 部分字段更新成功")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_update_appointment_status():
    """测试用例 5: 更新预约（状态更新）"""
    test_name = "更新预约（状态更新）"
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
        appointment = await create_test_appointment(session, user.id, "内科", "张医生", status=AppointmentStatus.PENDING)
        
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await update_appointment.ainvoke({
                "appointment_id": appointment.id,
                "status": "confirmed",
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "成功更新预约" in result, "应该包含成功消息"
        
        # 验证数据库中的状态更新
        await session.refresh(appointment)
        assert appointment.status == AppointmentStatus.CONFIRMED, "状态应该已更新为CONFIRMED"
        
        print(f"  ✅ 状态更新成功: PENDING -> CONFIRMED")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_update_appointment_not_exists():
    """测试用例 6: 更新预约（预约不存在）"""
    test_name = "更新预约（预约不存在）"
    session = None
    engine = None
    trans = None
    nested_trans = None
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        session, engine, trans, nested_trans = await create_test_db_session()
        
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await update_appointment.ainvoke({
                "appointment_id": "99999",
                "department": "外科",
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "不存在" in result, "应该包含不存在消息"
        assert "99999" in result, "应该包含预约ID"
        
        print(f"  ✅ 返回结果: {result}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_update_appointment_invalid_status():
    """测试用例 7: 更新预约（无效状态）"""
    test_name = "更新预约（无效状态）"
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
        appointment = await create_test_appointment(session, user.id, "内科", "张医生")
        
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await update_appointment.ainvoke({
                "appointment_id": appointment.id,
                "status": "invalid_status",
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "无效的预约状态" in result, "应该包含无效状态消息"
        assert "invalid_status" in result, "应该包含无效的状态值"
        
        print(f"  ✅ 返回结果: {result}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_update_appointment_invalid_time():
    """测试用例 8: 更新预约（时间格式错误）"""
    test_name = "更新预约（时间格式错误）"
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
        appointment = await create_test_appointment(session, user.id, "内科", "张医生")
        
        invalid_time = "invalid-time-format"
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            result = await update_appointment.ainvoke({
                "appointment_id": appointment.id,
                "appointment_time": invalid_time,
                "session": session
            })
        
        assert isinstance(result, str), "返回结果应该是字符串"
        assert "预约时间格式错误" in result, "应该包含格式错误消息"
        assert invalid_time in result, "应该包含错误的时间格式"
        
        print(f"  ✅ 返回结果: {result}")
        
        test_result.add_pass(test_name)
        
    except AssertionError as e:
        test_result.add_fail(test_name, str(e))
    except Exception as e:
        test_result.add_fail(test_name, f"未预期的错误: {type(e).__name__}: {str(e)}")
    finally:
        if session:
            await cleanup_test_db_session(session, engine, trans, nested_trans)


async def test_update_appointment_no_session():
    """测试用例 9: 更新预约（数据库会话未提供）"""
    test_name = "更新预约（数据库会话未提供）"
    
    try:
        print(f"\n{'='*60}")
        print(f"执行测试: {test_name}")
        print(f"{'='*60}")
        
        # 测试不提供 session
        with patch.object(settings, 'JAVA_SERVICE_BASE_URL', None):
            try:
                await update_appointment.ainvoke({
                    "appointment_id": str(mock_response["id"]),
                    "department": "外科"
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
    print("开始执行预约管理工具测试")
    print("="*60)
    
    # create_appointment 测试
    await test_create_appointment_local_db()
    await test_create_appointment_java_service()
    await test_create_appointment_java_service_fallback()
    await test_create_appointment_required_fields()
    await test_create_appointment_iso_time()
    await test_create_appointment_invalid_time()
    await test_create_appointment_no_session()
    
    # query_appointment 测试
    await test_query_appointment_single()
    await test_query_appointment_all()
    await test_query_appointment_java_service()
    await test_query_appointment_java_service_fallback()
    await test_query_appointment_not_exists()
    await test_query_appointment_no_records()
    await test_query_appointment_no_session()
    
    # update_appointment 测试
    await test_update_appointment_local_db()
    await test_update_appointment_java_service()
    await test_update_appointment_java_service_fallback()
    await test_update_appointment_partial()
    await test_update_appointment_status()
    await test_update_appointment_not_exists()
    await test_update_appointment_invalid_status()
    await test_update_appointment_invalid_time()
    await test_update_appointment_no_session()
    
    # 打印测试总结
    success = test_result.summary()
    return success


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
