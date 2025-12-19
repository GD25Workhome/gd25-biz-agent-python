"""
健康事件记录仓储实现
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from infrastructure.database.repository.base import BaseRepository
from infrastructure.database.models.health_event import HealthEventRecord


class HealthEventRepository(BaseRepository[HealthEventRecord]):
    """健康事件记录仓储类"""
    
    def __init__(self, session: AsyncSession):
        """
        初始化健康事件记录仓储
        
        Args:
            session: 数据库会话
        """
        super().__init__(session, HealthEventRecord)
    
    async def get_by_user_id(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[HealthEventRecord]:
        """
        根据用户ID查询健康事件记录
        
        Args:
            user_id: 用户ID
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            健康事件记录列表
        """
        result = await self.session.execute(
            select(HealthEventRecord)
            .where(HealthEventRecord.user_id == user_id)
            .order_by(desc(HealthEventRecord.event_date))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def get_by_date_range(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[HealthEventRecord]:
        """
        根据日期范围查询健康事件记录
        
        Args:
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            健康事件记录列表
        """
        result = await self.session.execute(
            select(HealthEventRecord)
            .where(
                and_(
                    HealthEventRecord.user_id == user_id,
                    HealthEventRecord.event_date >= start_date,
                    HealthEventRecord.event_date <= end_date
                )
            )
            .order_by(desc(HealthEventRecord.event_date))
        )
        return list(result.scalars().all())
