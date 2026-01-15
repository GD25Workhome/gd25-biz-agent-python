"""
Session缓存仓储实现
"""
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.session_cache import SessionCache


class SessionCacheRepository(BaseRepository[SessionCache]):
    """Session缓存仓储类"""
    
    def __init__(self, session: AsyncSession):
        """
        初始化Session缓存仓储
        
        Args:
            session: 数据库会话
        """
        super().__init__(session, SessionCache)
    
    async def upsert_session(self, session_id: str, data_info: Dict[str, Any]) -> SessionCache:
        """
        创建或更新Session缓存（upsert操作）
        
        Args:
            session_id: Session ID
            data_info: Session上下文字典数据
            
        Returns:
            SessionCache: 创建或更新后的Session缓存记录
        """
        existing = await self.get_by_id(session_id)
        if existing:
            # 更新
            existing.data_info = data_info
            await self.session.flush()
            return existing
        else:
            # 创建
            return await self.create(
                id=session_id,
                data_info=data_info
            )
