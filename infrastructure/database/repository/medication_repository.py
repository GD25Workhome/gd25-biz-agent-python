"""
用药记录仓储实现
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from infrastructure.database.repository.base import BaseRepository
from infrastructure.database.models.medication import MedicationRecord


class MedicationRepository(BaseRepository[MedicationRecord]):
    """用药记录仓储类"""
    
    def __init__(self, session: AsyncSession):
        """
        初始化用药记录仓储
        
        Args:
            session: 数据库会话
        """
        super().__init__(session, MedicationRecord)
    
    async def get_by_user_id(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[MedicationRecord]:
        """
        根据用户ID查询用药记录
        
        Args:
            user_id: 用户ID
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            用药记录列表
        """
        result = await self.session.execute(
            select(MedicationRecord)
            .where(MedicationRecord.user_id == user_id)
            .order_by(desc(MedicationRecord.start_date))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def get_by_date_range(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[MedicationRecord]:
        """
        根据日期范围查询用药记录
        
        Args:
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            用药记录列表
        """
        result = await self.session.execute(
            select(MedicationRecord)
            .where(
                and_(
                    MedicationRecord.user_id == user_id,
                    MedicationRecord.start_date >= start_date,
                    MedicationRecord.start_date <= end_date
                )
            )
            .order_by(desc(MedicationRecord.start_date))
        )
        return list(result.scalars().all())
