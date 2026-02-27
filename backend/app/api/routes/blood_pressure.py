"""
血压记录CRUD路由
"""
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.blood_pressure import (
    BloodPressureRecordCreate,
    BloodPressureRecordUpdate,
    BloodPressureRecordResponse,
)
from backend.infrastructure.database.connection import get_async_session
from backend.infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
from backend.app.api.helpers import parse_datetime

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/blood-pressure", response_model=List[BloodPressureRecordResponse])
async def list_blood_pressure(
    user_id: Optional[str] = None,
    start_date: Optional[str] = Query(None, description="开始日期，格式：YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期，格式：YYYY-MM-DD"),
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_async_session)
):
    """
    查询血压记录列表
    
    Args:
        user_id: 用户ID（可选，用于筛选）
        start_date: 开始日期（可选，格式：YYYY-MM-DD）
        end_date: 结束日期（可选，格式：YYYY-MM-DD）
        limit: 限制数量（默认100）
        offset: 偏移量（默认0）
        session: 数据库会话（依赖注入）
        
    Returns:
        血压记录列表
    """
    try:
        repo = BloodPressureRepository(session)
        
        # 解析日期参数
        parsed_start_date = None
        parsed_end_date = None
        
        if start_date:
            parsed_start_date = parse_datetime(start_date)
            if parsed_start_date is None:
                raise HTTPException(status_code=400, detail=f"开始日期格式不正确: {start_date}，请使用 YYYY-MM-DD 格式")
        
        if end_date:
            parsed_end_date = parse_datetime(end_date)
            if parsed_end_date is None:
                raise HTTPException(status_code=400, detail=f"结束日期格式不正确: {end_date}，请使用 YYYY-MM-DD 格式")
        
        # 使用新的通用查询方法
        records = await repo.get_by_filters(
            user_id=user_id,
            start_date=parsed_start_date,
            end_date=parsed_end_date,
            limit=limit,
            offset=offset
        )
        await session.commit()
        return records
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"查询血压记录列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/blood-pressure/{id}", response_model=BloodPressureRecordResponse)
async def get_blood_pressure(
    id: str,
    session: AsyncSession = Depends(get_async_session)
):
    """
    根据ID查询血压记录
    
    Args:
        id: 记录ID
        session: 数据库会话（依赖注入）
        
    Returns:
        血压记录
    """
    try:
        repo = BloodPressureRepository(session)
        record = await repo.get_by_id(id)
        if not record:
            raise HTTPException(status_code=404, detail=f"血压记录不存在: {id}")
        await session.commit()
        return record
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"查询血压记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/blood-pressure", response_model=BloodPressureRecordResponse)
async def create_blood_pressure(
    data: BloodPressureRecordCreate,
    session: AsyncSession = Depends(get_async_session)
):
    """
    创建血压记录
    
    Args:
        data: 创建请求数据
        session: 数据库会话（依赖注入）
        
    Returns:
        创建的血压记录
    """
    try:
        repo = BloodPressureRepository(session)
        record = await repo.create(**data.model_dump())
        await session.commit()
        # 刷新对象以确保所有字段（包括created_at）都从数据库加载
        await session.refresh(record)
        return record
    except Exception as e:
        await session.rollback()
        logger.error(f"创建血压记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.put("/blood-pressure/{id}", response_model=BloodPressureRecordResponse)
async def update_blood_pressure(
    id: str,
    data: BloodPressureRecordUpdate,
    session: AsyncSession = Depends(get_async_session)
):
    """
    更新血压记录
    
    Args:
        id: 记录ID
        data: 更新请求数据
        session: 数据库会话（依赖注入）
        
    Returns:
        更新后的血压记录
    """
    try:
        repo = BloodPressureRepository(session)
        # 只更新非None的字段
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        record = await repo.update(id, **update_data)
        if not record:
            raise HTTPException(status_code=404, detail=f"血压记录不存在: {id}")
        await session.commit()
        # 刷新对象以确保所有字段（包括updated_at）都从数据库加载
        await session.refresh(record)
        return record
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"更新血压记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.delete("/blood-pressure/{id}")
async def delete_blood_pressure(
    id: str,
    session: AsyncSession = Depends(get_async_session)
):
    """
    删除血压记录
    
    Args:
        id: 记录ID
        session: 数据库会话（依赖注入）
        
    Returns:
        删除结果
    """
    try:
        repo = BloodPressureRepository(session)
        success = await repo.delete(id)
        if not success:
            raise HTTPException(status_code=404, detail=f"血压记录不存在: {id}")
        await session.commit()
        return {"message": "删除成功", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"删除血压记录失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")

