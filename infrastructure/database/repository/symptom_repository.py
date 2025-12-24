"""
症状记录仓储实现
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from infrastructure.database.repository.base import BaseRepository
from infrastructure.database.models.symptom import SymptomRecord


class SymptomRepository(BaseRepository[SymptomRecord]):
    """症状记录仓储类"""
    
    def __init__(self, session: AsyncSession):
        """
        初始化症状记录仓储
        
        Args:
            session: 数据库会话
        """
        super().__init__(session, SymptomRecord)
    
    async def get_by_user_id(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[SymptomRecord]:
        """
        根据用户ID查询症状记录
        
        Args:
            user_id: 用户ID
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            症状记录列表
        """
        result = await self.session.execute(
            select(SymptomRecord)
            .where(SymptomRecord.user_id == user_id)
            .order_by(desc(SymptomRecord.start_time))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
    
    async def get_by_date_range(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[SymptomRecord]:
        """
        根据日期范围查询症状记录
        
        Args:
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            症状记录列表
        """
        result = await self.session.execute(
            select(SymptomRecord)
            .where(
                and_(
                    SymptomRecord.user_id == user_id,
                    SymptomRecord.start_time >= start_date,
                    SymptomRecord.start_time <= end_date
                )
            )
            .order_by(desc(SymptomRecord.start_time))
        )
        return list(result.scalars().all())
