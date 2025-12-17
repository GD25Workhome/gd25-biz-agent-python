"""
预约仓储实现
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from infrastructure.database.repository.base import BaseRepository
from infrastructure.database.models.appointment import Appointment, AppointmentStatus


class AppointmentRepository(BaseRepository[Appointment]):
    """预约仓储类"""
    
    def __init__(self, session: AsyncSession):
        """
        初始化预约仓储
        
        Args:
            session: 数据库会话
        """
        super().__init__(session, Appointment)
    
    async def get_by_user_id(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Appointment]:
        """
        根据用户ID查询预约
        
        Args:
            user_id: 用户ID
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            预约列表
        """
        result = await self.session.execute(
            select(Appointment)
            .where(Appointment.user_id == user_id)
            .order_by(desc(Appointment.appointment_time))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def get_by_status(
        self,
        user_id: str,
        status: AppointmentStatus,
        limit: int = 100
    ) -> List[Appointment]:
        """
        根据状态查询预约
        
        Args:
            user_id: 用户ID
            status: 预约状态
            limit: 限制数量
            
        Returns:
            预约列表
        """
        result = await self.session.execute(
            select(Appointment)
            .where(
                and_(
                    Appointment.user_id == user_id,
                    Appointment.status == status
                )
            )
            .order_by(desc(Appointment.appointment_time))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_by_date_range(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Appointment]:
        """
        根据日期范围查询预约
        
        Args:
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            预约列表
        """
        result = await self.session.execute(
            select(Appointment)
            .where(
                and_(
                    Appointment.user_id == user_id,
                    Appointment.appointment_time >= start_date,
                    Appointment.appointment_time <= end_date
                )
            )
            .order_by(desc(Appointment.appointment_time))
        )
        return list(result.scalars().all())

