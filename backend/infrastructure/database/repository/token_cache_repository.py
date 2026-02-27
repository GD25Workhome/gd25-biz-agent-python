"""
Token缓存仓储实现
"""
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.token_cache import TokenCache


class TokenCacheRepository(BaseRepository[TokenCache]):
    """Token缓存仓储类"""
    
    def __init__(self, session: AsyncSession):
        """
        初始化Token缓存仓储
        
        Args:
            session: 数据库会话
        """
        super().__init__(session, TokenCache)
    
    async def upsert_token(self, token_id: str, data_info: Dict[str, Any]) -> TokenCache:
        """
        创建或更新Token缓存（upsert操作）
        
        Args:
            token_id: Token ID（即user_id）
            data_info: UserInfo对象序列化后的数据字典
            
        Returns:
            TokenCache: 创建或更新后的Token缓存记录
        """
        existing = await self.get_by_id(token_id)
        if existing:
            # 更新
            existing.data_info = data_info
            await self.session.flush()
            return existing
        else:
            # 创建
            return await self.create(
                id=token_id,
                data_info=data_info
            )
