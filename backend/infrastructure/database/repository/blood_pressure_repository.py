"""
血压记录仓储实现
"""
from typing import List, Optional
from datetime import datetime, timedelta
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
    
    async def get_latest_by_user_id(
        self,
        user_id: str
    ) -> Optional[BloodPressureRecord]:
        """
        获取用户最新的血压记录
        
        Args:
            user_id: 用户ID
            
        Returns:
            最新的血压记录，如果不存在则返回None
        """
        result = await self.session.execute(
            select(BloodPressureRecord)
            .where(BloodPressureRecord.user_id == user_id)
            .order_by(desc(BloodPressureRecord.record_time), desc(BloodPressureRecord.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_recent_by_user_id(
        self,
        user_id: str,
        days: int = 14,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[BloodPressureRecord]:
        """
        获取用户最近N天的血压记录（默认14天）
        
        Args:
            user_id: 用户ID
            days: 天数（默认14天），如果指定了 start_date 和 end_date，则忽略此参数
            start_date: 开始日期（可选）
            end_date: 结束日期（可选，默认为当前时间）
            
        Returns:
            血压记录列表（按记录时间倒序）
            
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

