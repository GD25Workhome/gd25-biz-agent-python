"""
药品记录仓储实现
"""
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.medication import MedicationRecord


class MedicationRepository(BaseRepository[MedicationRecord]):
    """药品记录仓储类"""
    
    def __init__(self, session: AsyncSession):
        """
        初始化药品记录仓储
        
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
        根据用户ID查询药品记录
        
        Args:
            user_id: 用户ID
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            药品记录列表（按用药时间倒序）
        """
        result = await self.session.execute(
            select(MedicationRecord)
            .where(MedicationRecord.user_id == user_id)
            .order_by(desc(MedicationRecord.medication_time))
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
        根据日期范围查询药品记录
        
        Args:
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            药品记录列表（按用药时间倒序）
        """
        result = await self.session.execute(
            select(MedicationRecord)
            .where(
                and_(
                    MedicationRecord.user_id == user_id,
                    MedicationRecord.medication_time >= start_date,
                    MedicationRecord.medication_time <= end_date
                )
            )
            .order_by(desc(MedicationRecord.medication_time))
        )
        return list(result.scalars().all())
    
    async def get_recent_by_user_id(
        self,
        user_id: str,
        days: int = 14,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[MedicationRecord]:
        """
        获取用户最近N天的药品记录（默认14天）
        
        Args:
            user_id: 用户ID
            days: 天数（默认14天），如果指定了 start_date 和 end_date，则忽略此参数
            start_date: 开始日期（可选）
            end_date: 结束日期（可选，默认为当前时间）
            
        Returns:
            药品记录列表（按用药时间倒序）
            
        逻辑说明：
        - 如果指定了 start_date 和 end_date，使用日期范围查询
        - 如果只指定了 start_date，end_date 默认为当前时间
        - 如果只指定了 end_date，start_date = end_date - days
        - 如果都未指定，start_date = 当前时间 - days，end_date = 当前时间
        - 时间范围限制：最多查询14天内的数据
        """
        now = datetime.now()
        
        # 确定开始和结束时间
        if start_date and end_date:
            # 使用指定的日期范围
            query_start = start_date
            query_end = end_date
        elif start_date:
            # 只指定了开始日期，结束日期为当前时间
            query_start = start_date
            query_end = now
        elif end_date:
            # 只指定了结束日期，开始日期为结束日期减去days天
            query_end = end_date
            query_start = end_date - timedelta(days=min(days, 14))
        else:
            # 都未指定，使用默认的days天
            query_end = now
            query_start = now - timedelta(days=min(days, 14))
        
        # 确保时间范围不超过14天
        if (query_end - query_start).days > 14:
            query_start = query_end - timedelta(days=14)
        
        # 使用 get_by_date_range 方法查询
        return await self.get_by_date_range(user_id, query_start, query_end)
