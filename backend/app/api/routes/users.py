"""
用户CRUD路由
"""
import logging
import json
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.users import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
)
from backend.infrastructure.database.connection import get_async_session
from backend.infrastructure.database.repository.user_repository import UserRepository

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/users", response_model=UserListResponse)
async def list_users(
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_async_session)
):
    """
    查询用户列表
    
    Args:
        limit: 限制数量（默认100）
        offset: 偏移量（默认0）
        session: 数据库会话（依赖注入）
        
    Returns:
        用户列表响应（包含users字段）
    """
    try:
        repo = UserRepository(session)
        users = await repo.get_all(limit, offset)
        await session.commit()
        # 转换为响应对象，添加前端兼容字段
        user_responses = [UserResponse.from_orm_with_compat(user) for user in users]
        return UserListResponse(users=user_responses)
    except Exception as e:
        await session.rollback()
        logger.error(f"查询用户列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/users/{id}", response_model=UserResponse)
async def get_user(
    id: str,
    session: AsyncSession = Depends(get_async_session)
):
    """
    根据ID查询用户
    
    Args:
        id: 用户ID
        session: 数据库会话（依赖注入）
        
    Returns:
        用户信息
    """
    try:
        repo = UserRepository(session)
        user = await repo.get_by_id(id)
        if not user:
            raise HTTPException(status_code=404, detail=f"用户不存在: {id}")
        await session.commit()
        return UserResponse.from_orm_with_compat(user)
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"查询用户失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/users", response_model=UserResponse)
async def create_user(
    data: UserCreate,
    session: AsyncSession = Depends(get_async_session)
):
    """
    创建用户
    
    Args:
        data: 创建请求数据
        session: 数据库会话（依赖注入）
        
    Returns:
        创建的用户
    """
    try:
        repo = UserRepository(session)
        # 检查用户名是否已存在
        existing_user = await repo.get_by_user_name(data.user_name)
        if existing_user:
            raise HTTPException(status_code=400, detail=f"用户名已存在: {data.user_name}")
        
        # 解析user_info JSON字符串
        user_info_dict = None
        if data.user_info:
            try:
                user_info_dict = json.loads(data.user_info)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="user_info必须是有效的JSON格式")
        
        user = await repo.create(
            user_name=data.user_name,
            user_info=user_info_dict
        )
        await session.commit()
        # 刷新对象以确保所有字段都从数据库加载
        await session.refresh(user)
        return UserResponse.from_orm_with_compat(user)
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"创建用户失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.put("/users/{id}", response_model=UserResponse)
async def update_user(
    id: str,
    data: UserUpdate,
    session: AsyncSession = Depends(get_async_session)
):
    """
    更新用户
    
    Args:
        id: 用户ID
        data: 更新请求数据
        session: 数据库会话（依赖注入）
        
    Returns:
        更新后的用户
    """
    try:
        repo = UserRepository(session)
        
        # 构建更新数据
        update_data = {}
        if data.user_name is not None:
            # 检查新用户名是否与其他用户冲突
            existing_user = await repo.get_by_user_name(data.user_name)
            if existing_user and existing_user.id != id:
                raise HTTPException(status_code=400, detail=f"用户名已存在: {data.user_name}")
            update_data["user_name"] = data.user_name
        
        if data.user_info is not None:
            # 解析user_info JSON字符串
            try:
                update_data["user_info"] = json.loads(data.user_info) if data.user_info else None
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="user_info必须是有效的JSON格式")
        
        user = await repo.update(id, **update_data)
        if not user:
            raise HTTPException(status_code=404, detail=f"用户不存在: {id}")
        await session.commit()
        # 刷新对象以确保所有字段（包括updated_at）都从数据库加载
        await session.refresh(user)
        return UserResponse.from_orm_with_compat(user)
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"更新用户失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.delete("/users/{id}")
async def delete_user(
    id: str,
    session: AsyncSession = Depends(get_async_session)
):
    """
    删除用户
    
    Args:
        id: 用户ID
        session: 数据库会话（依赖注入）
        
    Returns:
        删除结果
    """
    try:
        repo = UserRepository(session)
        success = await repo.delete(id)
        if not success:
            raise HTTPException(status_code=404, detail=f"用户不存在: {id}")
        await session.commit()
        return {"message": "删除成功", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"删除用户失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")

