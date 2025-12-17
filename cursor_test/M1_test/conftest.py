"""
测试配置和共享 Fixtures
"""
import sys
import os
from pathlib import Path

# 将项目根目录添加到 Python 路径
# 获取 conftest.py 所在目录的父目录的父目录（项目根目录）
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest
import pytest_asyncio
import asyncio
import uuid
from datetime import datetime
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from infrastructure.database.base import Base
from infrastructure.database.models import User, BloodPressureRecord, Appointment
from infrastructure.database.models.appointment import AppointmentStatus


# 使用正式数据库连接进行测试
# 注意：测试使用事务回滚，确保不会污染正式数据库
TEST_DATABASE_URL = settings.ASYNC_DB_URI


# 移除自定义 event_loop fixture，使用 pytest-asyncio 默认的


@pytest_asyncio.fixture(scope="function")
async def test_db_engine():
    """
    创建测试数据库引擎（连接正式数据库）
    
    注意：此 fixture 连接到正式数据库，但测试使用事务回滚确保数据安全
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=True,  # 开启 SQL 日志，方便查看数据库操作
        pool_pre_ping=True,  # 连接前检查连接是否有效
        pool_size=5,
        max_overflow=10
    )
    
    # 验证连接：尝试连接数据库
    async with engine.begin() as conn:
        # 执行简单查询验证连接
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
        print(f"✅ 成功连接到数据库: {TEST_DATABASE_URL}")
    
    yield engine
    
    # 清理：关闭所有连接
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_db_session(test_db_engine):
    """
    创建测试数据库会话（使用嵌套事务确保数据安全）
    
    每个测试都在独立的嵌套事务（SAVEPOINT）中运行，即使测试中调用了 commit()，
    测试结束后也会回滚整个事务，确保不会污染正式数据库中的数据。
    """
    async_session_factory = async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    # 使用嵌套事务（SAVEPOINT）支持测试中的 commit()
    async with async_session_factory() as session:
        # 手动开始外层事务（不使用上下文管理器，避免自动提交）
        trans = None
        try:
            trans = await session.begin()
            # 创建保存点（嵌套事务）
            # 这样测试中的 commit() 只会提交到保存点，不会提交到外层事务
            nested_trans = None
            try:
                nested_trans = await session.begin_nested()
                try:
                    yield session
                except Exception:
                    # 如果测试失败，回滚到保存点
                    if nested_trans and nested_trans.is_active:
                        try:
                            await nested_trans.rollback()
                        except Exception:
                            pass  # 忽略回滚错误
                    raise
                finally:
                    # 保存点上下文退出后，手动回滚保存点（即使测试中调用了 commit()）
                    if nested_trans and nested_trans.is_active:
                        try:
                            await nested_trans.rollback()
                        except Exception:
                            pass  # 如果保存点已经回滚或不存在，忽略错误
            except Exception:
                # 如果嵌套事务创建失败，直接抛出异常
                raise
        finally:
            # 回滚外层事务，确保不提交任何数据到数据库
            if trans and trans.is_active:
                try:
                    await trans.rollback()
                    print("✅ 测试事务已回滚，数据库数据未受影响")
                except Exception as e:
                    # 如果事务已经关闭或回滚失败，记录但不抛出异常
                    print(f"⚠️  事务回滚时出现异常（已忽略）: {e}")


@pytest.fixture
def test_user_data():
    """
    测试用户数据
    
    使用唯一标识符确保每次测试运行的数据都是唯一的，避免唯一性约束冲突。
    使用 UUID 的前 8 位作为后缀，确保 username、phone、email 都是唯一的。
    """
    unique_suffix = str(uuid.uuid4())[:8]  # 使用 UUID 的前 8 位作为唯一后缀
    return {
        "username": f"test_user_{unique_suffix}",
        "phone": f"138{unique_suffix}",
        "email": f"test_{unique_suffix}@example.com",
        "is_active": True
    }


@pytest_asyncio.fixture
async def test_user(test_db_session, test_user_data):
    """创建测试用户"""
    user = User(**test_user_data)
    test_db_session.add(user)
    await test_db_session.flush()
    await test_db_session.refresh(user)
    return user


@pytest.fixture
def test_blood_pressure_data():
    """测试血压记录数据"""
    return {
        "systolic": 120,
        "diastolic": 80,
        "heart_rate": 72,
        "record_time": datetime.utcnow(),
        "notes": "测试记录"
    }


@pytest_asyncio.fixture
async def test_blood_pressure_record(test_db_session, test_user, test_blood_pressure_data):
    """创建测试血压记录"""
    record = BloodPressureRecord(
        user_id=test_user.id,
        **test_blood_pressure_data
    )
    test_db_session.add(record)
    await test_db_session.flush()
    await test_db_session.refresh(record)
    return record


@pytest.fixture
def test_appointment_data():
    """测试预约数据"""
    return {
        "department": "内科",
        "doctor_name": "张医生",
        "appointment_time": datetime.utcnow(),
        "status": AppointmentStatus.PENDING,
        "notes": "测试预约"
    }


@pytest_asyncio.fixture
async def test_appointment(test_db_session, test_user, test_appointment_data):
    """创建测试预约"""
    appointment = Appointment(
        user_id=test_user.id,
        **test_appointment_data
    )
    test_db_session.add(appointment)
    await test_db_session.flush()
    await test_db_session.refresh(appointment)
    return appointment


@pytest.fixture
def mock_llm_response():
    """Mock LLM 响应"""
    return {
        "content": "这是 LLM 的回复",
        "role": "assistant"
    }


@pytest.fixture
def mock_java_service_response():
    """Mock Java 微服务响应"""
    return {
        "id": "1",
        "userId": "1",
        "department": "内科",
        "appointmentTime": "2025-01-15T10:00:00",
        "status": "pending"
    }

