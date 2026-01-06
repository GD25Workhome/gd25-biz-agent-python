"""
用户仓储实现
"""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.user import User


class UserRepository(BaseRepository[User]):
    """用户仓储类"""
    
    def __init__(self, session: AsyncSession):
        """
        初始化用户仓储
        
        Args:
            session: 数据库会话
        """
        super().__init__(session, User)
    
    async def get_by_user_name(self, user_name: str) -> Optional[User]:
        """
        根据用户名查询用户
        
        Args:
            user_name: 用户名
            
        Returns:
            用户对象或None
        """
        result = await self.session.execute(
            select(User).where(User.user_name == user_name)
        )
        return result.scalar_one_or_none()

