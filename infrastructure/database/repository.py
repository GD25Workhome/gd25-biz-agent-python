from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database.models import User, BloodPressureRecord, Appointment

class BaseRepository:
    """
    基础仓储类 (Base Repository)
    
    封装了基础的数据库会话操作。
    """
    def __init__(self, session: AsyncSession):
        """
        初始化 Repository。
        
        Args:
            session (AsyncSession): SQLAlchemy 异步会话对象。
        """
        self.session = session

class UserRepository(BaseRepository):
    """
    用户仓储类 (User Repository)
    
    处理 User 表的 CRUD 操作。
    """
    
    async def get_by_username(self, username: str) -> Optional[User]:
        """
        根据用户名查询用户。
        
        Args:
            username (str): 用户名。
            
        Returns:
            Optional[User]: 找到的用户对象，如果不存在则返回 None。
        """
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalars().first()

    async def get_or_create(self, username: str) -> User:
        """
        获取用户，如果不存在则创建。
        
        Args:
            username (str): 用户名。
            
        Returns:
            User: 现有的或新创建的用户对象。
        """
        user = await self.get_by_username(username)
        if not user:
            user = User(username=username)
            self.session.add(user)
            await self.session.flush() # 立即执行 SQL 以获取自增 ID，但不提交事务
        return user

class BloodPressureRepository(BaseRepository):
    """
    血压记录仓储类 (Blood Pressure Repository)
    
    处理 BloodPressureRecord 表的 CRUD 操作。
    """
    
    async def add_record(self, user_id: int, systolic: int, diastolic: int, heart_rate: int) -> BloodPressureRecord:
        """
        添加一条血压记录。
        
        Args:
            user_id (int): 用户 ID。
            systolic (int): 收缩压 (高压)。
            diastolic (int): 舒张压 (低压)。
            heart_rate (int): 心率。
            
        Returns:
            BloodPressureRecord: 创建的记录对象。
        """
        record = BloodPressureRecord(
            user_id=user_id,
            systolic=systolic,
            diastolic=diastolic,
            heart_rate=heart_rate
        )
        self.session.add(record)
        # 实际应用中，提交通常由 Service 层或 Unit of Work 控制
        # 这里为了简化 Tool 调用，直接提交
        await self.session.commit() 
        return record

    async def get_history(self, user_id: int, limit: int = 10) -> List[BloodPressureRecord]:
        """
        查询用户的历史血压记录。
        
        Args:
            user_id (int): 用户 ID。
            limit (int): 返回记录的最大数量。
            
        Returns:
            List[BloodPressureRecord]: 按时间倒序排列的记录列表。
        """
        stmt = (
            select(BloodPressureRecord)
            .where(BloodPressureRecord.user_id == user_id)
            .order_by(desc(BloodPressureRecord.measured_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

class AppointmentRepository(BaseRepository):
    """
    预约仓储类 (Appointment Repository)
    
    处理 Appointment 表的 CRUD 操作。
    """
    
    async def create_appointment(self, user_id: int, doctor: str, department: str, time: datetime) -> Appointment:
        """
        创建新的预约。
        
        Args:
            user_id (int): 用户 ID。
            doctor (str): 医生姓名。
            department (str): 科室。
            time (datetime): 预约时间。
            
        Returns:
            Appointment: 创建的预约对象。
        """
        appt = Appointment(
            user_id=user_id,
            doctor_name=doctor,
            department=department,
            appointment_time=time
        )
        self.session.add(appt)
        await self.session.commit()
        return appt
