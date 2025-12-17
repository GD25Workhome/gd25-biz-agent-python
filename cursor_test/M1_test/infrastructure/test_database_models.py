"""
数据库模型测试

Pytest 命令示例：
================

# 运行整个测试文件
pytest cursor_test/M1_test/infrastructure/test_database_models.py

# 运行整个测试文件（详细输出）
pytest cursor_test/M1_test/infrastructure/test_database_models.py -v

# 运行整个测试文件（显示 print 输出）
pytest cursor_test/M1_test/infrastructure/test_database_models.py -s

# 运行整个测试文件（详细输出 + 显示 print 输出）
pytest cursor_test/M1_test/infrastructure/test_database_models.py -v -s

# 运行特定的测试类
pytest cursor_test/M1_test/infrastructure/test_database_models.py::TestUserModel

# 运行特定的测试方法
pytest cursor_test/M1_test/infrastructure/test_database_models.py::TestUserModel::test_create_user_success

# 使用 -k 参数过滤测试（按名称匹配）
pytest cursor_test/M1_test/infrastructure/test_database_models.py -k "test_create_user"

# 使用 -k 参数过滤测试（排除某些测试）
pytest cursor_test/M1_test/infrastructure/test_database_models.py -k "not test_user_relationships"

# 只运行失败的测试（需要先运行一次）
pytest cursor_test/M1_test/infrastructure/test_database_models.py --lf

# 运行失败的测试并显示失败信息
pytest cursor_test/M1_test/infrastructure/test_database_models.py --lf -v

# 在第一个失败时停止
pytest cursor_test/M1_test/infrastructure/test_database_models.py -x

# 显示测试覆盖率（需要安装 pytest-cov）
pytest cursor_test/M1_test/infrastructure/test_database_models.py --cov=infrastructure.database.models

# 从项目根目录运行（相对路径）
pytest cursor_test/M1_test/infrastructure/test_database_models.py

# 从项目根目录运行（使用绝对路径）
pytest /Users/m684620/work/github_GD25/gd25-biz-agent-python_cursor/cursor_test/M1_test/infrastructure/test_database_models.py
"""
import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from infrastructure.database.models import User, BloodPressureRecord, Appointment
from infrastructure.database.models.appointment import AppointmentStatus


class TestUserModel:
    """User 模型测试类"""
    
    @pytest.mark.asyncio
    async def test_create_user_success(self, test_db_session, test_user_data):
        """
        测试用例：创建用户（正常情况）
        
        验证：
        - 用户能够成功创建
        - 所有字段正确保存
        - 默认值正确设置
        """
        # Arrange（准备）
        # test_user_data 已通过 fixture 提供
        
        # Act（执行）
        user = User(**test_user_data)
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        
        # Assert（断言）
        assert user.id is not None
        assert user.username == test_user_data["username"]
        assert user.phone == test_user_data["phone"]
        assert user.email == test_user_data["email"]
        assert user.is_active == test_user_data["is_active"]
        assert user.created_at is not None
        assert user.updated_at is not None
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)
    
    @pytest.mark.asyncio
    async def test_create_user_required_fields(self, test_db_session):
        """
        测试用例：创建用户（必填字段验证）
        
        验证：
        - username 是必填字段，不能为空
        - 其他字段可以为空（phone、email）
        """
        # Arrange（准备）
        # 测试缺少必填字段的情况
        
        # Act & Assert（执行和断言）
        # 测试缺少 username
        with pytest.raises((IntegrityError, TypeError)):
            user = User(
                phone="13800138000",
                email="test@example.com"
            )
            test_db_session.add(user)
            await test_db_session.flush()
        
        await test_db_session.rollback()
        
        # 测试只有 username（应该成功）
        user = User(username="minimal_user")
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        
        assert user.id is not None
        assert user.username == "minimal_user"
        assert user.phone is None
        assert user.email is None
        assert user.is_active is True  # 默认值
    
    @pytest.mark.asyncio
    async def test_create_user_unique_constraints(self, test_db_session, test_user_data):
        """
        测试用例：创建用户（唯一性约束：username、phone、email）
        
        验证：
        - username 必须唯一
        - phone 必须唯一（如果提供）
        - email 必须唯一（如果提供）
        """
        import uuid
        
        # Arrange（准备）
        # 创建第一个用户，使用唯一的标识符
        unique_suffix = str(uuid.uuid4())[:8]
        user1_data = {
            "username": f"unique_user1_{unique_suffix}",
            "phone": f"138{unique_suffix}",
            "email": f"unique1_{unique_suffix}@example.com",
            "is_active": True
        }
        user1 = User(**user1_data)
        test_db_session.add(user1)
        await test_db_session.flush()
        await test_db_session.refresh(user1)
        
        # Act & Assert（执行和断言）
        # 测试重复的 username
        with pytest.raises(IntegrityError):
            user2 = User(
                username=user1_data["username"],  # 重复的 username
                phone="13900139000",
                email="test2@example.com"
            )
            test_db_session.add(user2)
            await test_db_session.flush()
        
        # 回滚到保存点
        await test_db_session.rollback()
        # 重新创建第一个用户，使用不同的唯一值
        unique_suffix2 = str(uuid.uuid4())[:8]
        user1_data = {
            "username": f"unique_user1_{unique_suffix2}",
            "phone": f"138{unique_suffix2}",
            "email": f"unique1_{unique_suffix2}@example.com",
            "is_active": True
        }
        user1 = User(**user1_data)
        test_db_session.add(user1)
        await test_db_session.flush()
        await test_db_session.refresh(user1)
        
        # 测试重复的 phone（SQLite 允许 NULL 值重复，所以只有当 phone 不为 NULL 时才测试）
        if user1_data.get("phone"):
            with pytest.raises(IntegrityError):
                user3 = User(
                    username="test_user2",
                    phone=user1_data["phone"],  # 重复的 phone
                    email="test3@example.com"
                )
                test_db_session.add(user3)
                await test_db_session.flush()
            
            await test_db_session.rollback()
            # 重新创建第一个用户，使用不同的唯一值
            unique_suffix3 = str(uuid.uuid4())[:8]
            user1_data = {
                "username": f"unique_user1_{unique_suffix3}",
                "phone": f"138{unique_suffix3}",
                "email": f"unique1_{unique_suffix3}@example.com",
                "is_active": True
            }
            user1 = User(**user1_data)
            test_db_session.add(user1)
            await test_db_session.flush()
            await test_db_session.refresh(user1)
        
        # 测试重复的 email（SQLite 允许 NULL 值重复，所以只有当 email 不为 NULL 时才测试）
        if user1_data.get("email"):
            with pytest.raises(IntegrityError):
                user4 = User(
                    username="test_user3",
                    phone="13900139000",
                    email=user1_data["email"]  # 重复的 email
                )
                test_db_session.add(user4)
                await test_db_session.flush()
            
            await test_db_session.rollback()
        
        # 测试不同的用户（应该成功）
        unique_suffix4 = str(uuid.uuid4())[:8]
        user5 = User(
            username=f"test_user4_{unique_suffix4}",
            phone=f"139{unique_suffix4}",
            email=f"test4_{unique_suffix4}@example.com"
        )
        test_db_session.add(user5)
        await test_db_session.flush()
        await test_db_session.refresh(user5)
        
        assert user5.id is not None
        assert user5.username == f"test_user4_{unique_suffix4}"
    
    @pytest.mark.asyncio
    async def test_user_relationships(self, test_db_session, test_user, test_blood_pressure_data, test_appointment_data):
        """
        测试用例：用户关系（blood_pressure_records、appointments）
        
        验证：
        - 用户可以通过关系访问血压记录
        - 用户可以通过关系访问预约记录
        - 级联删除功能正常
        """
        # Arrange（准备）
        # test_user 已通过 fixture 创建
        
        # 创建血压记录
        bp_record = BloodPressureRecord(
            user_id=test_user.id,
            **test_blood_pressure_data
        )
        test_db_session.add(bp_record)
        
        # 创建预约记录
        appointment = Appointment(
            user_id=test_user.id,
            **test_appointment_data
        )
        test_db_session.add(appointment)
        
        await test_db_session.commit()
        
        # Act（执行）
        # 重新加载用户及其关系（使用 selectinload 避免 lazy loading 问题）
        result = await test_db_session.execute(
            select(User)
            .options(selectinload(User.blood_pressure_records), selectinload(User.appointments))
            .where(User.id == test_user.id)
        )
        user_with_relations = result.scalar_one()
        
        # 通过关系访问
        blood_pressure_records = user_with_relations.blood_pressure_records
        appointments = user_with_relations.appointments
        
        # Assert（断言）
        assert len(blood_pressure_records) == 1
        assert blood_pressure_records[0].id == bp_record.id
        assert blood_pressure_records[0].systolic == test_blood_pressure_data["systolic"]
        
        assert len(appointments) == 1
        assert appointments[0].id == appointment.id
        assert appointments[0].department == test_appointment_data["department"]
        
        # 测试级联删除
        await test_db_session.delete(test_user)
        await test_db_session.flush()
        
        # 验证关联记录也被删除
        result = await test_db_session.execute(
            select(BloodPressureRecord).where(BloodPressureRecord.id == bp_record.id)
        )
        assert result.scalar_one_or_none() is None
        
        result = await test_db_session.execute(
            select(Appointment).where(Appointment.id == appointment.id)
        )
        assert result.scalar_one_or_none() is None
    
    @pytest.mark.asyncio
    async def test_user_timestamps(self, test_db_session, test_user_data):
        """
        测试用例：用户时间戳（created_at、updated_at）
        
        验证：
        - created_at 在创建时自动设置
        - updated_at 在创建时自动设置
        - updated_at 在更新时自动更新
        - created_at 在更新时不变
        """
        # Arrange（准备）
        import asyncio
        
        # Act（执行）
        # 创建用户
        user = User(**test_user_data)
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        
        created_at_before = user.created_at
        updated_at_before = user.updated_at
        
        # 等待一小段时间，确保时间戳会变化
        await asyncio.sleep(0.1)
        
        # 更新用户
        user.username = "updated_username"
        await test_db_session.flush()
        await test_db_session.refresh(user)
        
        # Assert（断言）
        assert user.created_at == created_at_before  # created_at 不应该改变
        assert user.updated_at > updated_at_before  # updated_at 应该更新
        assert user.updated_at >= created_at_before  # updated_at 应该 >= created_at
    
    @pytest.mark.asyncio
    async def test_user_repr(self, test_db_session, test_user_data):
        """
        测试用例：User 模型的 __repr__ 方法
        
        验证：
        - __repr__ 方法返回正确的字符串格式
        """
        # Arrange（准备）
        user = User(**test_user_data)
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        
        # Act（执行）
        repr_str = repr(user)
        
        # Assert（断言）
        assert "User" in repr_str
        assert str(user.id) in repr_str
        assert user.username in repr_str


class TestBloodPressureRecordModel:
    """BloodPressureRecord 模型测试类"""
    
    @pytest.mark.asyncio
    async def test_create_blood_pressure_record_success(self, test_db_session, test_user, test_blood_pressure_data):
        """
        测试用例：创建血压记录（正常情况）
        
        验证：
        - 血压记录能够成功创建
        - 所有字段正确保存
        - 默认值正确设置
        """
        # Arrange（准备）
        # test_user 和 test_blood_pressure_data 已通过 fixture 提供
        
        # Act（执行）
        record = BloodPressureRecord(
            user_id=test_user.id,
            **test_blood_pressure_data
        )
        test_db_session.add(record)
        await test_db_session.flush()
        await test_db_session.refresh(record)
        
        # Assert（断言）
        assert record.id is not None
        assert record.user_id == test_user.id
        assert record.systolic == test_blood_pressure_data["systolic"]
        assert record.diastolic == test_blood_pressure_data["diastolic"]
        assert record.heart_rate == test_blood_pressure_data["heart_rate"]
        assert record.record_time == test_blood_pressure_data["record_time"]
        assert record.notes == test_blood_pressure_data["notes"]
        assert record.created_at is not None
        assert record.updated_at is not None
        assert isinstance(record.created_at, datetime)
        assert isinstance(record.updated_at, datetime)
    
    @pytest.mark.asyncio
    async def test_create_blood_pressure_record_required_fields(self, test_db_session, test_user_data):
        """
        测试用例：创建血压记录（必填字段验证）
        
        验证：
        - user_id 是必填字段，不能为空
        - systolic 是必填字段，不能为空
        - diastolic 是必填字段，不能为空
        - record_time 是必填字段，不能为空
        """
        # Arrange（准备）
        # 创建用户用于测试（不使用 fixture，因为 rollback 会回滚它）
        user = User(**test_user_data)
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        user_id = user.id
        
        # Act & Assert（执行和断言）
        # 测试缺少 user_id
        with pytest.raises((IntegrityError, TypeError)):
            record = BloodPressureRecord(
                systolic=120,
                diastolic=80,
                record_time=datetime.utcnow()
            )
            test_db_session.add(record)
            await test_db_session.flush()
        
        await test_db_session.rollback()
        # 重新创建用户
        user = User(**test_user_data)
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        user_id = user.id
        
        # 测试缺少 systolic
        with pytest.raises((IntegrityError, TypeError)):
            record = BloodPressureRecord(
                user_id=user_id,
                diastolic=80,
                record_time=datetime.utcnow()
            )
            test_db_session.add(record)
            await test_db_session.flush()
        
        await test_db_session.rollback()
        # 重新创建用户
        user = User(**test_user_data)
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        user_id = user.id
        
        # 测试缺少 diastolic
        with pytest.raises((IntegrityError, TypeError)):
            record = BloodPressureRecord(
                user_id=user_id,
                systolic=120,
                record_time=datetime.utcnow()
            )
            test_db_session.add(record)
            await test_db_session.flush()
        
        await test_db_session.rollback()
        # 重新创建用户
        user = User(**test_user_data)
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        user_id = user.id
        
        # 测试只有必填字段（应该成功）
        record = BloodPressureRecord(
            user_id=user_id,
            systolic=120,
            diastolic=80,
            record_time=datetime.utcnow()
        )
        test_db_session.add(record)
        await test_db_session.flush()
        await test_db_session.refresh(record)
        
        assert record.id is not None
        assert record.heart_rate is None  # 可选字段
        assert record.notes is None  # 可选字段
    
    @pytest.mark.asyncio
    async def test_create_blood_pressure_record_optional_fields(self, test_db_session, test_user):
        """
        测试用例：创建血压记录（可选字段：heart_rate、notes）
        
        验证：
        - heart_rate 是可选的，可以为 None
        - notes 是可选的，可以为 None
        - 可选字段可以正常设置
        """
        # Arrange（准备）
        # 测试可选字段
        
        # Act（执行）
        # 测试不提供可选字段
        record1 = BloodPressureRecord(
            user_id=test_user.id,
            systolic=120,
            diastolic=80,
            record_time=datetime.utcnow()
        )
        test_db_session.add(record1)
        await test_db_session.flush()
        await test_db_session.refresh(record1)
        
        # 测试提供可选字段
        record2 = BloodPressureRecord(
            user_id=test_user.id,
            systolic=130,
            diastolic=85,
            heart_rate=72,
            record_time=datetime.utcnow(),
            notes="测试记录"
        )
        test_db_session.add(record2)
        await test_db_session.flush()
        await test_db_session.refresh(record2)
        
        # Assert（断言）
        assert record1.heart_rate is None
        assert record1.notes is None
        
        assert record2.heart_rate == 72
        assert record2.notes == "测试记录"
    
    @pytest.mark.asyncio
    async def test_blood_pressure_record_user_relationship(self, test_db_session, test_user, test_blood_pressure_data):
        """
        测试用例：血压记录与用户关系
        
        验证：
        - 血压记录可以通过关系访问用户
        - 用户可以通过关系访问血压记录
        """
        # Arrange（准备）
        # 创建血压记录
        record = BloodPressureRecord(
            user_id=test_user.id,
            **test_blood_pressure_data
        )
        test_db_session.add(record)
        await test_db_session.flush()
        await test_db_session.refresh(record)
        
        # Act（执行）
        # 通过关系访问用户
        user_from_record = record.user
        
        # 重新加载用户及其关系
        from sqlalchemy.orm import selectinload
        result = await test_db_session.execute(
            select(User)
            .options(selectinload(User.blood_pressure_records))
            .where(User.id == test_user.id)
        )
        user_with_records = result.scalar_one()
        records_from_user = user_with_records.blood_pressure_records
        
        # Assert（断言）
        assert user_from_record.id == test_user.id
        assert user_from_record.username == test_user.username
        
        assert len(records_from_user) >= 1
        assert any(r.id == record.id for r in records_from_user)
    
    @pytest.mark.asyncio
    async def test_blood_pressure_record_timestamps(self, test_db_session, test_user, test_blood_pressure_data):
        """
        测试用例：血压记录时间戳
        
        验证：
        - created_at 在创建时自动设置
        - updated_at 在创建时自动设置
        - updated_at 在更新时自动更新
        - created_at 在更新时不变
        """
        # Arrange（准备）
        import asyncio
        
        # Act（执行）
        # 创建血压记录
        record = BloodPressureRecord(
            user_id=test_user.id,
            **test_blood_pressure_data
        )
        test_db_session.add(record)
        await test_db_session.flush()
        await test_db_session.refresh(record)
        
        created_at_before = record.created_at
        updated_at_before = record.updated_at
        
        # 等待一小段时间，确保时间戳会变化
        await asyncio.sleep(0.1)
        
        # 更新血压记录
        record.systolic = 130
        await test_db_session.flush()
        await test_db_session.refresh(record)
        
        # Assert（断言）
        assert record.created_at == created_at_before  # created_at 不应该改变
        assert record.updated_at > updated_at_before  # updated_at 应该更新
        assert record.updated_at >= created_at_before  # updated_at 应该 >= created_at


class TestAppointmentModel:
    """Appointment 模型测试类"""
    
    @pytest.mark.asyncio
    async def test_create_appointment_success(self, test_db_session, test_user, test_appointment_data):
        """
        测试用例：创建预约（正常情况）
        
        验证：
        - 预约能够成功创建
        - 所有字段正确保存
        - 默认值正确设置
        """
        # Arrange（准备）
        # test_user 和 test_appointment_data 已通过 fixture 提供
        
        # Act（执行）
        appointment = Appointment(
            user_id=test_user.id,
            **test_appointment_data
        )
        test_db_session.add(appointment)
        await test_db_session.flush()
        await test_db_session.refresh(appointment)
        
        # Assert（断言）
        assert appointment.id is not None
        assert appointment.user_id == test_user.id
        assert appointment.department == test_appointment_data["department"]
        assert appointment.doctor_name == test_appointment_data["doctor_name"]
        assert appointment.appointment_time == test_appointment_data["appointment_time"]
        assert appointment.status == test_appointment_data["status"]
        assert appointment.notes == test_appointment_data["notes"]
        assert appointment.created_at is not None
        assert appointment.updated_at is not None
        assert isinstance(appointment.created_at, datetime)
        assert isinstance(appointment.updated_at, datetime)
    
    @pytest.mark.asyncio
    async def test_create_appointment_required_fields(self, test_db_session, test_user_data):
        """
        测试用例：创建预约（必填字段验证）
        
        验证：
        - user_id 是必填字段，不能为空
        - department 是必填字段，不能为空
        - appointment_time 是必填字段，不能为空
        """
        # Arrange（准备）
        # 创建用户用于测试（不使用 fixture，因为 rollback 会回滚它）
        user = User(**test_user_data)
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        user_id = user.id
        
        # Act & Assert（执行和断言）
        # 测试缺少 user_id
        with pytest.raises((IntegrityError, TypeError)):
            appointment = Appointment(
                department="内科",
                appointment_time=datetime.utcnow()
            )
            test_db_session.add(appointment)
            await test_db_session.flush()
        
        await test_db_session.rollback()
        # 重新创建用户
        user = User(**test_user_data)
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        user_id = user.id
        
        # 测试缺少 department
        with pytest.raises((IntegrityError, TypeError)):
            appointment = Appointment(
                user_id=user_id,
                appointment_time=datetime.utcnow()
            )
            test_db_session.add(appointment)
            await test_db_session.flush()
        
        await test_db_session.rollback()
        # 重新创建用户
        user = User(**test_user_data)
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        user_id = user.id
        
        # 测试缺少 appointment_time
        with pytest.raises((IntegrityError, TypeError)):
            appointment = Appointment(
                user_id=user_id,
                department="内科"
            )
            test_db_session.add(appointment)
            await test_db_session.flush()
        
        await test_db_session.rollback()
        # 重新创建用户
        user = User(**test_user_data)
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        user_id = user.id
        
        # 测试只有必填字段（应该成功，status 有默认值）
        appointment = Appointment(
            user_id=user_id,
            department="内科",
            appointment_time=datetime.utcnow()
        )
        test_db_session.add(appointment)
        await test_db_session.flush()
        await test_db_session.refresh(appointment)
        
        assert appointment.id is not None
        assert appointment.status == AppointmentStatus.PENDING  # 默认值
        assert appointment.doctor_name is None  # 可选字段
        assert appointment.notes is None  # 可选字段
    
    @pytest.mark.asyncio
    async def test_appointment_status_enum(self, test_db_session, test_user):
        """
        测试用例：预约状态枚举（pending、confirmed、completed、cancelled）
        
        验证：
        - 可以设置不同的状态值
        - 状态枚举值正确
        """
        # Arrange（准备）
        base_time = datetime.utcnow()
        
        # Act（执行）
        # 测试所有状态值
        pending_appointment = Appointment(
            user_id=test_user.id,
            department="内科",
            appointment_time=base_time,
            status=AppointmentStatus.PENDING
        )
        test_db_session.add(pending_appointment)
        
        confirmed_appointment = Appointment(
            user_id=test_user.id,
            department="外科",
            appointment_time=base_time,
            status=AppointmentStatus.CONFIRMED
        )
        test_db_session.add(confirmed_appointment)
        
        completed_appointment = Appointment(
            user_id=test_user.id,
            department="儿科",
            appointment_time=base_time,
            status=AppointmentStatus.COMPLETED
        )
        test_db_session.add(completed_appointment)
        
        cancelled_appointment = Appointment(
            user_id=test_user.id,
            department="骨科",
            appointment_time=base_time,
            status=AppointmentStatus.CANCELLED
        )
        test_db_session.add(cancelled_appointment)
        
        await test_db_session.flush()
        await test_db_session.refresh(pending_appointment)
        await test_db_session.refresh(confirmed_appointment)
        await test_db_session.refresh(completed_appointment)
        await test_db_session.refresh(cancelled_appointment)
        
        # Assert（断言）
        assert pending_appointment.status == AppointmentStatus.PENDING
        assert pending_appointment.status.value == "pending"
        
        assert confirmed_appointment.status == AppointmentStatus.CONFIRMED
        assert confirmed_appointment.status.value == "confirmed"
        
        assert completed_appointment.status == AppointmentStatus.COMPLETED
        assert completed_appointment.status.value == "completed"
        
        assert cancelled_appointment.status == AppointmentStatus.CANCELLED
        assert cancelled_appointment.status.value == "cancelled"
    
    @pytest.mark.asyncio
    async def test_appointment_user_relationship(self, test_db_session, test_user, test_appointment_data):
        """
        测试用例：预约与用户关系
        
        验证：
        - 预约可以通过关系访问用户
        - 用户可以通过关系访问预约
        """
        # Arrange（准备）
        # 创建预约
        appointment = Appointment(
            user_id=test_user.id,
            **test_appointment_data
        )
        test_db_session.add(appointment)
        await test_db_session.flush()
        await test_db_session.refresh(appointment)
        
        # Act（执行）
        # 通过关系访问用户
        user_from_appointment = appointment.user
        
        # 重新加载用户及其关系
        from sqlalchemy.orm import selectinload
        result = await test_db_session.execute(
            select(User)
            .options(selectinload(User.appointments))
            .where(User.id == test_user.id)
        )
        user_with_appointments = result.scalar_one()
        appointments_from_user = user_with_appointments.appointments
        
        # Assert（断言）
        assert user_from_appointment.id == test_user.id
        assert user_from_appointment.username == test_user.username
        
        assert len(appointments_from_user) >= 1
        assert any(a.id == appointment.id for a in appointments_from_user)
    
    @pytest.mark.asyncio
    async def test_appointment_timestamps(self, test_db_session, test_user, test_appointment_data):
        """
        测试用例：预约时间戳
        
        验证：
        - created_at 在创建时自动设置
        - updated_at 在创建时自动设置
        - updated_at 在更新时自动更新
        - created_at 在更新时不变
        """
        # Arrange（准备）
        import asyncio
        
        # Act（执行）
        # 创建预约
        appointment = Appointment(
            user_id=test_user.id,
            **test_appointment_data
        )
        test_db_session.add(appointment)
        await test_db_session.flush()
        await test_db_session.refresh(appointment)
        
        created_at_before = appointment.created_at
        updated_at_before = appointment.updated_at
        
        # 等待一小段时间，确保时间戳会变化
        await asyncio.sleep(0.1)
        
        # 更新预约
        appointment.status = AppointmentStatus.CONFIRMED
        await test_db_session.flush()
        await test_db_session.refresh(appointment)
        
        # Assert（断言）
        assert appointment.created_at == created_at_before  # created_at 不应该改变
        assert appointment.updated_at > updated_at_before  # updated_at 应该更新
        assert appointment.updated_at >= created_at_before  # updated_at 应该 >= created_at

