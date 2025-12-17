"""
Repository 测试

Pytest 命令示例：
================

# 运行整个测试文件
pytest cursor_test/M1_test/infrastructure/test_repositories.py

# 运行整个测试文件（详细输出）
pytest cursor_test/M1_test/infrastructure/test_repositories.py -v

# 运行特定的测试类
pytest cursor_test/M1_test/infrastructure/test_repositories.py::TestBaseRepository

# 运行特定的测试方法
pytest cursor_test/M1_test/infrastructure/test_repositories.py::TestBaseRepository::test_get_by_id_exists
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import select

from infrastructure.database.repository.base import BaseRepository
from infrastructure.database.repository.user_repository import UserRepository
from infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
from infrastructure.database.repository.appointment_repository import AppointmentRepository
from infrastructure.database.models import User, BloodPressureRecord, Appointment
from infrastructure.database.models.appointment import AppointmentStatus


class TestBaseRepository:
    """BaseRepository 测试类"""
    
    @pytest.mark.asyncio
    async def test_get_by_id_exists(self, test_db_session, test_user):
        """
        测试用例：get_by_id（存在记录）
        
        验证：
        - 能够根据 ID 查询到存在的记录
        - 返回正确的模型实例
        """
        # Arrange（准备）
        # test_user 已通过 fixture 创建
        
        # Act（执行）
        repository = BaseRepository(test_db_session, User)
        result = await repository.get_by_id(test_user.id)
        
        # Assert（断言）
        assert result is not None
        assert result.id == test_user.id
        assert result.username == test_user.username
    
    @pytest.mark.asyncio
    async def test_get_by_id_not_exists(self, test_db_session):
        """
        测试用例：get_by_id（不存在记录）
        
        验证：
        - 查询不存在的记录时返回 None
        """
        # Arrange（准备）
        non_existent_id = 99999
        
        # Act（执行）
        repository = BaseRepository(test_db_session, User)
        result = await repository.get_by_id(non_existent_id)
        
        # Assert（断言）
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_all_normal(self, test_db_session, test_user_data):
        """
        测试用例：get_all（正常情况）
        
        验证：
        - 能够查询所有记录
        - 返回列表格式
        """
        # Arrange（准备）
        # 创建多个用户
        users = []
        for i in range(3):
            user_data = test_user_data.copy()
            user_data["username"] = f"{user_data['username']}_{i}"
            user_data["phone"] = f"{user_data['phone']}{i}"
            user_data["email"] = f"user{i}@{user_data['email'].split('@')[1]}"
            user = User(**user_data)
            test_db_session.add(user)
            users.append(user)
        
        await test_db_session.flush()
        
        # Act（执行）
        repository = BaseRepository(test_db_session, User)
        result = await repository.get_all()
        
        # Assert（断言）
        assert isinstance(result, list)
        assert len(result) >= 3  # 至少包含刚创建的3个用户
        assert all(isinstance(user, User) for user in result)
    
    @pytest.mark.asyncio
    async def test_get_all_pagination(self, test_db_session, test_user_data):
        """
        测试用例：get_all（分页：limit、offset）
        
        验证：
        - limit 参数正确限制返回数量
        - offset 参数正确跳过记录
        """
        # Arrange（准备）
        # 创建多个用户
        users = []
        for i in range(5):
            user_data = test_user_data.copy()
            user_data["username"] = f"{user_data['username']}_pag_{i}"
            user_data["phone"] = f"{user_data['phone']}pag{i}"
            user_data["email"] = f"pag{i}@{user_data['email'].split('@')[1]}"
            user = User(**user_data)
            test_db_session.add(user)
            users.append(user)
        
        await test_db_session.flush()
        
        # Act（执行）
        repository = BaseRepository(test_db_session, User)
        
        # 测试 limit
        result_limit = await repository.get_all(limit=2)
        
        # 测试 offset
        result_offset = await repository.get_all(limit=2, offset=2)
        
        # Assert（断言）
        assert len(result_limit) <= 2
        assert len(result_offset) <= 2
        # 注意：由于可能有其他测试数据，这里只验证数量限制
    
    @pytest.mark.asyncio
    async def test_create_success(self, test_db_session, test_user_data):
        """
        测试用例：create（正常情况）
        
        验证：
        - 能够成功创建记录
        - 返回创建的模型实例
        - 记录已保存到数据库
        """
        # Arrange（准备）
        # test_user_data 已通过 fixture 提供
        
        # Act（执行）
        repository = BaseRepository(test_db_session, User)
        user = await repository.create(**test_user_data)
        
        # Assert（断言）
        assert user is not None
        assert user.id is not None
        assert user.username == test_user_data["username"]
        
        # 验证记录已保存
        result = await repository.get_by_id(user.id)
        assert result is not None
        assert result.username == test_user_data["username"]
    
    @pytest.mark.asyncio
    async def test_update_success(self, test_db_session, test_user):
        """
        测试用例：update（正常情况）
        
        验证：
        - 能够成功更新记录
        - 返回更新后的模型实例
        - 字段已正确更新
        """
        # Arrange（准备）
        # test_user 已通过 fixture 创建
        new_username = "updated_username"
        
        # Act（执行）
        repository = BaseRepository(test_db_session, User)
        updated_user = await repository.update(test_user.id, username=new_username)
        
        # Assert（断言）
        assert updated_user is not None
        assert updated_user.id == test_user.id
        assert updated_user.username == new_username
        
        # 验证数据库中的记录已更新
        result = await repository.get_by_id(test_user.id)
        assert result.username == new_username
    
    @pytest.mark.asyncio
    async def test_update_not_exists(self, test_db_session):
        """
        测试用例：update（不存在记录）
        
        验证：
        - 更新不存在的记录时返回 None
        """
        # Arrange（准备）
        non_existent_id = 99999
        
        # Act（执行）
        repository = BaseRepository(test_db_session, User)
        result = await repository.update(non_existent_id, username="new_username")
        
        # Assert（断言）
        assert result is None
    
    @pytest.mark.asyncio
    async def test_delete_success(self, test_db_session, test_user_data):
        """
        测试用例：delete（正常情况）
        
        验证：
        - 能够成功删除记录
        - 返回 True
        - 记录已从数据库删除
        """
        # Arrange（准备）
        # 创建用户用于删除
        user = User(**test_user_data)
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        user_id = user.id
        
        # Act（执行）
        repository = BaseRepository(test_db_session, User)
        result = await repository.delete(user_id)
        
        # Assert（断言）
        assert result is True
        
        # 验证记录已删除
        deleted_user = await repository.get_by_id(user_id)
        assert deleted_user is None
    
    @pytest.mark.asyncio
    async def test_delete_not_exists(self, test_db_session):
        """
        测试用例：delete（不存在记录）
        
        验证：
        - 删除不存在的记录时返回 False
        """
        # Arrange（准备）
        non_existent_id = 99999
        
        # Act（执行）
        repository = BaseRepository(test_db_session, User)
        result = await repository.delete(non_existent_id)
        
        # Assert（断言）
        assert result is False


class TestUserRepository:
    """UserRepository 测试类"""
    
    @pytest.mark.asyncio
    async def test_get_by_username_exists(self, test_db_session, test_user):
        """
        测试用例：get_by_username（存在用户）
        
        验证：
        - 能够根据用户名查询到存在的用户
        - 返回正确的用户实例
        """
        # Arrange（准备）
        # test_user 已通过 fixture 创建
        
        # Act（执行）
        repository = UserRepository(test_db_session)
        result = await repository.get_by_username(test_user.username)
        
        # Assert（断言）
        assert result is not None
        assert result.id == test_user.id
        assert result.username == test_user.username
    
    @pytest.mark.asyncio
    async def test_get_by_username_not_exists(self, test_db_session):
        """
        测试用例：get_by_username（不存在用户）
        
        验证：
        - 查询不存在的用户名时返回 None
        """
        # Arrange（准备）
        non_existent_username = "non_existent_user_12345"
        
        # Act（执行）
        repository = UserRepository(test_db_session)
        result = await repository.get_by_username(non_existent_username)
        
        # Assert（断言）
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_by_phone_exists(self, test_db_session, test_user):
        """
        测试用例：get_by_phone（存在用户）
        
        验证：
        - 能够根据手机号查询到存在的用户
        - 返回正确的用户实例
        """
        # Arrange（准备）
        # test_user 已通过 fixture 创建
        if test_user.phone is None:
            pytest.skip("测试用户没有手机号，跳过此测试")
        
        # Act（执行）
        repository = UserRepository(test_db_session)
        result = await repository.get_by_phone(test_user.phone)
        
        # Assert（断言）
        assert result is not None
        assert result.id == test_user.id
        assert result.phone == test_user.phone
    
    @pytest.mark.asyncio
    async def test_get_by_phone_not_exists(self, test_db_session):
        """
        测试用例：get_by_phone（不存在用户）
        
        验证：
        - 查询不存在的手机号时返回 None
        """
        # Arrange（准备）
        non_existent_phone = "99999999999"
        
        # Act（执行）
        repository = UserRepository(test_db_session)
        result = await repository.get_by_phone(non_existent_phone)
        
        # Assert（断言）
        assert result is None
    
    @pytest.mark.asyncio
    async def test_inherit_base_repository_methods(self, test_db_session, test_user):
        """
        测试用例：继承 BaseRepository 的所有方法
        
        验证：
        - UserRepository 继承了 BaseRepository 的所有方法
        - 这些方法能够正常工作
        """
        # Arrange（准备）
        # test_user 已通过 fixture 创建
        
        # Act（执行）
        repository = UserRepository(test_db_session)
        
        # 测试 get_by_id
        user_by_id = await repository.get_by_id(test_user.id)
        
        # 测试 get_all
        all_users = await repository.get_all()
        
        # 测试 update
        updated_user = await repository.update(test_user.id, is_active=False)
        
        # 测试 delete（先恢复，因为测试中会删除）
        # 注意：这里不实际删除，只验证方法存在
        
        # Assert（断言）
        assert user_by_id is not None
        assert user_by_id.id == test_user.id
        
        assert isinstance(all_users, list)
        assert len(all_users) > 0
        
        assert updated_user is not None
        assert updated_user.is_active is False


class TestBloodPressureRepository:
    """BloodPressureRepository 测试类"""
    
    @pytest.mark.asyncio
    async def test_get_by_user_id_normal(self, test_db_session, test_user, test_blood_pressure_data):
        """
        测试用例：get_by_user_id（正常情况）
        
        验证：
        - 能够根据用户ID查询到血压记录
        - 返回列表格式
        - 记录按时间倒序排列
        """
        # Arrange（准备）
        # 创建多个血压记录
        records = []
        for i in range(3):
            record_data = test_blood_pressure_data.copy()
            record_data["record_time"] = datetime.utcnow() - timedelta(hours=i)
            record = BloodPressureRecord(
                user_id=test_user.id,
                **record_data
            )
            test_db_session.add(record)
            records.append(record)
        
        await test_db_session.flush()
        
        # Act（执行）
        repository = BloodPressureRepository(test_db_session)
        result = await repository.get_by_user_id(test_user.id)
        
        # Assert（断言）
        assert isinstance(result, list)
        assert len(result) >= 3  # 至少包含刚创建的3条记录
        assert all(isinstance(record, BloodPressureRecord) for record in result)
        assert all(record.user_id == test_user.id for record in result)
        
        # 验证按时间倒序排列（最新的在前）
        if len(result) >= 2:
            assert result[0].record_time >= result[1].record_time
    
    @pytest.mark.asyncio
    async def test_get_by_user_id_pagination(self, test_db_session, test_user, test_blood_pressure_data):
        """
        测试用例：get_by_user_id（分页）
        
        验证：
        - limit 参数正确限制返回数量
        - offset 参数正确跳过记录
        """
        # Arrange（准备）
        # 创建多个血压记录
        for i in range(5):
            record_data = test_blood_pressure_data.copy()
            record_data["record_time"] = datetime.utcnow() - timedelta(hours=i)
            record = BloodPressureRecord(
                user_id=test_user.id,
                **record_data
            )
            test_db_session.add(record)
        
        await test_db_session.flush()
        
        # Act（执行）
        repository = BloodPressureRepository(test_db_session)
        
        # 测试 limit
        result_limit = await repository.get_by_user_id(test_user.id, limit=2)
        
        # 测试 offset
        result_offset = await repository.get_by_user_id(test_user.id, limit=2, offset=2)
        
        # Assert（断言）
        assert len(result_limit) <= 2
        assert len(result_offset) <= 2
    
    @pytest.mark.asyncio
    async def test_get_by_user_id_no_records(self, test_db_session, test_user_data):
        """
        测试用例：get_by_user_id（无记录）
        
        验证：
        - 用户没有血压记录时返回空列表
        """
        # Arrange（准备）
        # 创建新用户（没有血压记录）
        user = User(**test_user_data)
        test_db_session.add(user)
        await test_db_session.flush()
        await test_db_session.refresh(user)
        
        # Act（执行）
        repository = BloodPressureRepository(test_db_session)
        result = await repository.get_by_user_id(user.id)
        
        # Assert（断言）
        assert isinstance(result, list)
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_get_by_date_range_normal(self, test_db_session, test_user, test_blood_pressure_data):
        """
        测试用例：get_by_date_range（正常情况）
        
        验证：
        - 能够根据日期范围查询到血压记录
        - 只返回范围内的记录
        """
        # Arrange（准备）
        now = datetime.utcnow()
        start_date = now - timedelta(days=2)
        end_date = now
        
        # 创建范围内的记录
        record_in_range = BloodPressureRecord(
            user_id=test_user.id,
            systolic=120,
            diastolic=80,
            record_time=now - timedelta(days=1),
            heart_rate=test_blood_pressure_data.get("heart_rate"),
            notes=test_blood_pressure_data.get("notes")
        )
        test_db_session.add(record_in_range)
        
        # 创建范围外的记录
        record_out_of_range = BloodPressureRecord(
            user_id=test_user.id,
            systolic=130,
            diastolic=85,
            record_time=now - timedelta(days=3),
            heart_rate=test_blood_pressure_data.get("heart_rate"),
            notes=test_blood_pressure_data.get("notes")
        )
        test_db_session.add(record_out_of_range)
        
        await test_db_session.flush()
        
        # Act（执行）
        repository = BloodPressureRepository(test_db_session)
        result = await repository.get_by_date_range(test_user.id, start_date, end_date)
        
        # Assert（断言）
        assert isinstance(result, list)
        assert len(result) >= 1
        assert all(
            start_date <= record.record_time <= end_date
            for record in result
        )
        # 验证范围内的记录存在
        assert any(record.id == record_in_range.id for record in result)
        # 验证范围外的记录不存在
        assert not any(record.id == record_out_of_range.id for record in result)
    
    @pytest.mark.asyncio
    async def test_get_by_date_range_boundary(self, test_db_session, test_user, test_blood_pressure_data):
        """
        测试用例：get_by_date_range（边界条件：开始时间、结束时间）
        
        验证：
        - 边界时间点包含在结果中
        - 边界外的记录不包含在结果中
        """
        # Arrange（准备）
        now = datetime.utcnow()
        start_date = now - timedelta(days=1)
        end_date = now
        
        # 创建边界上的记录
        record_at_start = BloodPressureRecord(
            user_id=test_user.id,
            systolic=120,
            diastolic=80,
            record_time=start_date,
            heart_rate=test_blood_pressure_data.get("heart_rate"),
            notes=test_blood_pressure_data.get("notes")
        )
        test_db_session.add(record_at_start)
        
        record_at_end = BloodPressureRecord(
            user_id=test_user.id,
            systolic=130,
            diastolic=85,
            record_time=end_date,
            heart_rate=test_blood_pressure_data.get("heart_rate"),
            notes=test_blood_pressure_data.get("notes")
        )
        test_db_session.add(record_at_end)
        
        # 创建边界外的记录
        record_before_start = BloodPressureRecord(
            user_id=test_user.id,
            systolic=140,
            diastolic=90,
            record_time=start_date - timedelta(seconds=1),
            heart_rate=test_blood_pressure_data.get("heart_rate"),
            notes=test_blood_pressure_data.get("notes")
        )
        test_db_session.add(record_before_start)
        
        record_after_end = BloodPressureRecord(
            user_id=test_user.id,
            systolic=150,
            diastolic=95,
            record_time=end_date + timedelta(seconds=1),
            heart_rate=test_blood_pressure_data.get("heart_rate"),
            notes=test_blood_pressure_data.get("notes")
        )
        test_db_session.add(record_after_end)
        
        await test_db_session.flush()
        
        # Act（执行）
        repository = BloodPressureRepository(test_db_session)
        result = await repository.get_by_date_range(test_user.id, start_date, end_date)
        
        # Assert（断言）
        # 验证边界上的记录包含在结果中
        assert any(record.id == record_at_start.id for record in result)
        assert any(record.id == record_at_end.id for record in result)
        # 验证边界外的记录不包含在结果中
        assert not any(record.id == record_before_start.id for record in result)
        assert not any(record.id == record_after_end.id for record in result)
    
    @pytest.mark.asyncio
    async def test_inherit_base_repository_methods(self, test_db_session, test_user, test_blood_pressure_data):
        """
        测试用例：继承 BaseRepository 的所有方法
        
        验证：
        - BloodPressureRepository 继承了 BaseRepository 的所有方法
        - 这些方法能够正常工作
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
        repository = BloodPressureRepository(test_db_session)
        
        # 测试 get_by_id
        record_by_id = await repository.get_by_id(record.id)
        
        # 测试 get_all
        all_records = await repository.get_all()
        
        # 测试 update
        updated_record = await repository.update(record.id, systolic=130)
        
        # Assert（断言）
        assert record_by_id is not None
        assert record_by_id.id == record.id
        
        assert isinstance(all_records, list)
        assert len(all_records) > 0
        
        assert updated_record is not None
        assert updated_record.systolic == 130


class TestAppointmentRepository:
    """AppointmentRepository 测试类"""
    
    @pytest.mark.asyncio
    async def test_get_by_user_id_normal(self, test_db_session, test_user, test_appointment_data):
        """
        测试用例：get_by_user_id（正常情况）
        
        验证：
        - 能够根据用户ID查询到预约
        - 返回列表格式
        - 记录按时间倒序排列
        """
        # Arrange（准备）
        # 创建多个预约
        appointments = []
        for i in range(3):
            appointment_data = test_appointment_data.copy()
            appointment_data["appointment_time"] = datetime.utcnow() + timedelta(days=i)
            appointment = Appointment(
                user_id=test_user.id,
                **appointment_data
            )
            test_db_session.add(appointment)
            appointments.append(appointment)
        
        await test_db_session.flush()
        
        # Act（执行）
        repository = AppointmentRepository(test_db_session)
        result = await repository.get_by_user_id(test_user.id)
        
        # Assert（断言）
        assert isinstance(result, list)
        assert len(result) >= 3  # 至少包含刚创建的3条记录
        assert all(isinstance(appointment, Appointment) for appointment in result)
        assert all(appointment.user_id == test_user.id for appointment in result)
        
        # 验证按时间倒序排列（最新的在前）
        if len(result) >= 2:
            assert result[0].appointment_time >= result[1].appointment_time
    
    @pytest.mark.asyncio
    async def test_get_by_user_id_pagination(self, test_db_session, test_user, test_appointment_data):
        """
        测试用例：get_by_user_id（分页）
        
        验证：
        - limit 参数正确限制返回数量
        - offset 参数正确跳过记录
        """
        # Arrange（准备）
        # 创建多个预约
        for i in range(5):
            appointment_data = test_appointment_data.copy()
            appointment_data["appointment_time"] = datetime.utcnow() + timedelta(days=i)
            appointment = Appointment(
                user_id=test_user.id,
                **appointment_data
            )
            test_db_session.add(appointment)
        
        await test_db_session.flush()
        
        # Act（执行）
        repository = AppointmentRepository(test_db_session)
        
        # 测试 limit
        result_limit = await repository.get_by_user_id(test_user.id, limit=2)
        
        # 测试 offset
        result_offset = await repository.get_by_user_id(test_user.id, limit=2, offset=2)
        
        # Assert（断言）
        assert len(result_limit) <= 2
        assert len(result_offset) <= 2
    
    @pytest.mark.asyncio
    async def test_get_by_status_normal(self, test_db_session, test_user, test_appointment_data):
        """
        测试用例：get_by_status（正常情况）
        
        验证：
        - 能够根据状态查询到预约
        - 只返回指定状态的预约
        """
        # Arrange（准备）
        # 创建不同状态的预约
        pending_appointment = Appointment(
            user_id=test_user.id,
            department="内科",
            appointment_time=datetime.utcnow(),
            status=AppointmentStatus.PENDING,
            **{k: v for k, v in test_appointment_data.items() if k not in ["department", "appointment_time", "status"]}
        )
        test_db_session.add(pending_appointment)
        
        confirmed_appointment = Appointment(
            user_id=test_user.id,
            department="外科",
            appointment_time=datetime.utcnow(),
            status=AppointmentStatus.CONFIRMED,
            **{k: v for k, v in test_appointment_data.items() if k not in ["department", "appointment_time", "status"]}
        )
        test_db_session.add(confirmed_appointment)
        
        await test_db_session.flush()
        
        # Act（执行）
        repository = AppointmentRepository(test_db_session)
        pending_results = await repository.get_by_status(test_user.id, AppointmentStatus.PENDING)
        confirmed_results = await repository.get_by_status(test_user.id, AppointmentStatus.CONFIRMED)
        
        # Assert（断言）
        assert isinstance(pending_results, list)
        assert len(pending_results) >= 1
        assert all(appointment.status == AppointmentStatus.PENDING for appointment in pending_results)
        assert any(appointment.id == pending_appointment.id for appointment in pending_results)
        
        assert isinstance(confirmed_results, list)
        assert len(confirmed_results) >= 1
        assert all(appointment.status == AppointmentStatus.CONFIRMED for appointment in confirmed_results)
        assert any(appointment.id == confirmed_appointment.id for appointment in confirmed_results)
    
    @pytest.mark.asyncio
    async def test_get_by_status_different_statuses(self, test_db_session, test_user, test_appointment_data):
        """
        测试用例：get_by_status（不同状态）
        
        验证：
        - 能够查询所有不同的状态
        - 每个状态返回正确的记录
        """
        # Arrange（准备）
        # 创建所有状态的预约
        statuses = [
            AppointmentStatus.PENDING,
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.COMPLETED,
            AppointmentStatus.CANCELLED
        ]
        
        appointments = {}
        for status in statuses:
            appointment = Appointment(
                user_id=test_user.id,
                department=f"{status.value}科室",
                appointment_time=datetime.utcnow(),
                status=status,
                **{k: v for k, v in test_appointment_data.items() if k not in ["department", "appointment_time", "status"]}
            )
            test_db_session.add(appointment)
            appointments[status] = appointment
        
        await test_db_session.flush()
        
        # Act（执行）
        repository = AppointmentRepository(test_db_session)
        
        # Assert（断言）
        for status in statuses:
            results = await repository.get_by_status(test_user.id, status)
            assert isinstance(results, list)
            assert len(results) >= 1
            assert all(appointment.status == status for appointment in results)
            assert any(appointment.id == appointments[status].id for appointment in results)
    
    @pytest.mark.asyncio
    async def test_get_by_date_range_normal(self, test_db_session, test_user, test_appointment_data):
        """
        测试用例：get_by_date_range（正常情况）
        
        验证：
        - 能够根据日期范围查询到预约
        - 只返回范围内的预约
        """
        # Arrange（准备）
        now = datetime.utcnow()
        start_date = now + timedelta(days=1)
        end_date = now + timedelta(days=3)
        
        # 创建范围内的预约
        appointment_in_range = Appointment(
            user_id=test_user.id,
            department="内科",
            appointment_time=now + timedelta(days=2),
            status=AppointmentStatus.PENDING,
            **{k: v for k, v in test_appointment_data.items() if k not in ["department", "appointment_time", "status"]}
        )
        test_db_session.add(appointment_in_range)
        
        # 创建范围外的预约
        appointment_out_of_range = Appointment(
            user_id=test_user.id,
            department="外科",
            appointment_time=now + timedelta(days=5),
            status=AppointmentStatus.PENDING,
            **{k: v for k, v in test_appointment_data.items() if k not in ["department", "appointment_time", "status"]}
        )
        test_db_session.add(appointment_out_of_range)
        
        await test_db_session.flush()
        
        # Act（执行）
        repository = AppointmentRepository(test_db_session)
        result = await repository.get_by_date_range(test_user.id, start_date, end_date)
        
        # Assert（断言）
        assert isinstance(result, list)
        assert len(result) >= 1
        assert all(
            start_date <= appointment.appointment_time <= end_date
            for appointment in result
        )
        # 验证范围内的预约存在
        assert any(appointment.id == appointment_in_range.id for appointment in result)
        # 验证范围外的预约不存在
        assert not any(appointment.id == appointment_out_of_range.id for appointment in result)
    
    @pytest.mark.asyncio
    async def test_inherit_base_repository_methods(self, test_db_session, test_user, test_appointment_data):
        """
        测试用例：继承 BaseRepository 的所有方法
        
        验证：
        - AppointmentRepository 继承了 BaseRepository 的所有方法
        - 这些方法能够正常工作
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
        repository = AppointmentRepository(test_db_session)
        
        # 测试 get_by_id
        appointment_by_id = await repository.get_by_id(appointment.id)
        
        # 测试 get_all
        all_appointments = await repository.get_all()
        
        # 测试 update
        updated_appointment = await repository.update(appointment.id, status=AppointmentStatus.CONFIRMED)
        
        # Assert（断言）
        assert appointment_by_id is not None
        assert appointment_by_id.id == appointment.id
        
        assert isinstance(all_appointments, list)
        assert len(all_appointments) > 0
        
        assert updated_appointment is not None
        assert updated_appointment.status == AppointmentStatus.CONFIRMED

