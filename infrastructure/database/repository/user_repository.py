"""
用户仓储实现
"""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from infrastructure.database.repository.base import BaseRepository
from infrastructure.database.models.user import User


class UserRepository(BaseRepository[User]):
    """用户仓储类"""
    
    def __init__(self, session: AsyncSession):
        """
        初始化用户仓储
        
        Args:
            session: 数据库会话
        """
        super().__init__(session, User)
    
    async def get_by_username(self, username: str) -> Optional[User]:
        """
        根据用户名查询
        
        Args:
            username: 用户名
            
        Returns:
            用户实例或None
        """
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()
    
    async def get_by_phone(self, phone: str) -> Optional[User]:
        """
        根据手机号查询
        
        Args:
            phone: 手机号
            
        Returns:
            用户实例或None
        """
        result = await self.session.execute(
            select(User).where(User.phone == phone)
        )
        return result.scalar_one_or_none()
    
    async def search_by_username(self, username: str, limit: int = 100, offset: int = 0) -> List[User]:
        """
        根据用户名模糊查询用户
        
        Args:
            username: 用户名（支持部分匹配）
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            用户列表
        """
        result = await self.session.execute(
            select(User)
            .where(User.username.ilike(f"%{username}%"))
            .limit(limit)
            .offset(offset)
            .order_by(User.created_at.desc())
        )
        return list(result.scalars().all())

