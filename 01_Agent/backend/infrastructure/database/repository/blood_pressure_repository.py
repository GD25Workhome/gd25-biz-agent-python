"""
血压记录仓储实现
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.blood_pressure import BloodPressureRecord


class BloodPressureRepository(BaseRepository[BloodPressureRecord]):
    """血压记录仓储类"""
    
    def __init__(self, session: AsyncSession):
        """
        初始化血压记录仓储
        
        Args:
            session: 数据库会话
        """
        super().__init__(session, BloodPressureRecord)
    
    async def get_by_user_id(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[BloodPressureRecord]:
        """
        根据用户ID查询血压记录
        
        Args:
            user_id: 用户ID
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            血压记录列表（按记录时间倒序）
        """
        result = await self.session.execute(
            select(BloodPressureRecord)
            .where(BloodPressureRecord.user_id == user_id)
            .order_by(desc(BloodPressureRecord.record_time))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def get_by_date_range(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[BloodPressureRecord]:
        """
        根据日期范围查询血压记录
        
        Args:
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            血压记录列表（按记录时间倒序）
        """
        result = await self.session.execute(
            select(BloodPressureRecord)
            .where(
                and_(
                    BloodPressureRecord.user_id == user_id,
                    BloodPressureRecord.record_time >= start_date,
                    BloodPressureRecord.record_time <= end_date
                )
            )
            .order_by(desc(BloodPressureRecord.record_time))
        )
        return list(result.scalars().all())

