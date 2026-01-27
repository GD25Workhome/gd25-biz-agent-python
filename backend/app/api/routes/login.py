"""
登录相关路由
"""
import logging
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.login import (
    CreateTokenRequest,
    CreateTokenResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    TokenInfoResponse,
    SessionInfoResponse,
)
from backend.domain.context.context_manager import get_context_manager
from backend.domain.context.user_info import UserInfo
from backend.domain.flows.manager import FlowManager
from backend.infrastructure.database.connection import get_async_session
from backend.infrastructure.database.repository.user_repository import UserRepository
from backend.infrastructure.database.repository.token_cache_repository import TokenCacheRepository
from backend.infrastructure.database.repository.session_cache_repository import SessionCacheRepository

logger = logging.getLogger(__name__)
router = APIRouter()


def generate_doctor_schedule(days: int = 14) -> List[Dict[str, Any]]:
    """
    生成医生排班信息
    
    规则：
    - 从今天开始，往后生成指定天数的排班
    - 一周医生休息两天，两天分为4个随机的半天（每周随机选择2天，每天随机选择上午或下午休息，共4个半天）
    - 工作时间为国内医院的白班时间：上午 8:00-12:00，下午 14:00-18:00
    - 如果没有排班就不显示对应的时间段
    
    Args:
        days: 生成排班的天数，默认为14天
        
    Returns:
        List[Dict]: 排班信息列表，每个元素包含：
            - date: 日期字符串（YYYY-MM-DD格式）
            - morning: 上午时间段（8:00-12:00），如果休息则不包含此字段
            - afternoon: 下午时间段（14:00-18:00），如果休息则不包含此字段
    """
    schedule = []
    today = datetime.now().date()
    
    # 计算需要生成的周数（向上取整）
    weeks = (days + 6) // 7
    
    # 为每周生成休息时间安排
    # rest_periods_by_week: {week_num: [(day_in_week, 'morning'|'afternoon'), ...]}
    rest_periods_by_week = {}
    
    for week in range(weeks):
        # 每周随机选择2天
        rest_days = random.sample(range(7), 2)
        rest_periods = []
        
        # 为这2天随机分配4个半天（确保总共4个半天休息）
        # 策略：从2个休息日的4个半天中随机选择4个
        day1, day2 = rest_days[0], rest_days[1]
        
        # 所有可能的半天：2个休息日 × 2个半天 = 4个半天
        all_periods = [
            (day1, 'morning'), (day1, 'afternoon'),
            (day2, 'morning'), (day2, 'afternoon')
        ]
        
        # 从4个半天中随机选择4个（即全部选择，但顺序随机）
        # 这样可以确保每个休息日至少有1个半天休息（因为总共只有4个半天，2个休息日）
        rest_periods = random.sample(all_periods, 4)
        
        # 验证：确保正好有4个半天休息，且每个休息日至少有1个半天
        assert len(rest_periods) == 4, f"每周应该有4个半天休息，实际有{len(rest_periods)}个"
        day1_count = sum(1 for d, p in rest_periods if d == day1)
        day2_count = sum(1 for d, p in rest_periods if d == day2)
        assert day1_count >= 1 and day2_count >= 1, f"每个休息日至少有1个半天休息"
        
        rest_periods_by_week[week] = rest_periods
    
    # 生成每天的排班信息
    for day_offset in range(days):
        current_date = today + timedelta(days=day_offset)
        week_num = day_offset // 7
        day_in_week = day_offset % 7
        
        # 获取本周的休息安排
        week_rest_periods = rest_periods_by_week.get(week_num, [])
        
        # 检查今天上午和下午是否休息
        morning_rest = (day_in_week, 'morning') in week_rest_periods
        afternoon_rest = (day_in_week, 'afternoon') in week_rest_periods
        
        # 构建当天的排班信息
        day_schedule = {
            "date": current_date.strftime("%Y-%m-%d")
        }
        
        # 添加上午时间段（如果不休息）
        if not morning_rest:
            day_schedule["morning"] = "8:00-12:00"
        
        # 添加下午时间段（如果不休息）
        if not afternoon_rest:
            day_schedule["afternoon"] = "14:00-18:00"
        
        schedule.append(day_schedule)
    
    return schedule


@router.post("/login/token", response_model=CreateTokenResponse)
async def create_token(
    request: CreateTokenRequest,
    session: AsyncSession = Depends(get_async_session)
) -> CreateTokenResponse:
    """
    创建Token接口
    
    为ContextManager的_token_contexts设置一个key为用户id，value为UserInfo对象。
    用户信息从数据库查询，如果用户不存在则抛出异常。
    
    Args:
        request: 创建Token请求（包含用户ID）
        session: 数据库会话（依赖注入）
        
    Returns:
        CreateTokenResponse: 创建的Token响应（包含token_id）
    """
    try:
        user_id = request.user_id
        
        # 从数据库查询用户信息
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        
        if user is None:
            raise HTTPException(status_code=404, detail=f"用户不存在: {user_id}")
        
        # 创建UserInfo对象
        user_info = UserInfo(user_id=user_id)
        # 设置用户基本信息（从数据库获取）
        if user.user_info:
            user_info.set_user_info(user.user_info)
        
        # 获取上下文管理器
        context_manager = get_context_manager()
        
        # 为_token_contexts设置key为用户id，value为UserInfo对象
        context_manager._token_contexts[user_id] = user_info
        
        # 持久化到数据库（新增）
        token_repo = TokenCacheRepository(session)
        await token_repo.upsert_token(
            token_id=user_id,  # 使用user_id作为token_id
            data_info=user_info.data  # 序列化UserInfo数据到data_info字段
        )
        
        await session.commit()
        
        logger.info(f"创建Token: user_id={user_id}, token_id={user_id}")
        
        return CreateTokenResponse(token_id=user_id)
        
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"创建Token失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建Token失败: {str(e)}")


@router.post("/login/session", response_model=CreateSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    session: AsyncSession = Depends(get_async_session)
) -> CreateSessionResponse:
    """
    创建Session接口
    
    为ContextManager的_session_contexts设置一个key为用户id_医生id_流程name，
    然后value为字典对象，包含user_id、flow_info、doctor_info。
    
    Args:
        request: 创建Session请求（包含用户ID、流程名称、医生ID）
        session: 数据库会话（依赖注入）
        
    Returns:
        CreateSessionResponse: 创建的Session响应（包含session_id）
    """
    try:
        user_id = request.user_id
        flow_name = request.flow_name
        # 固定参数：医生ID
        doctor_id = "doctorId001"
        
        # 从流程缓存中获取流程定义（参考 flows.py 的逻辑）
        # 如果流程定义不存在，先尝试扫描
        if flow_name not in FlowManager._flow_definitions:
            FlowManager.scan_flows()
        
        # 验证流程名称是否有效
        if flow_name not in FlowManager._flow_definitions:
            # 获取所有可用的流程名称
            available_flows = list(FlowManager._flow_definitions.keys())
            raise HTTPException(
                status_code=400,
                detail=f"无效的流程名称: {flow_name}。支持的流程: {available_flows}"
            )
        
        # 获取流程定义
        flow_def = FlowManager._flow_definitions[flow_name]
        
        # 构建session_id：用户id_医生id_流程name
        session_id = f"{user_id}_{doctor_id}_{flow_name}"
        
        # 获取流程信息（从流程定义中获取）
        flow_info = {
            "flow_key": flow_def.name,
            "flow_name": flow_def.description or flow_def.name
        }
        
        # 构建医生信息
        doctor_info = {
            "doctor_id": doctor_id,
            "doctor_name": "张医生",
            "schedule": generate_doctor_schedule(days=14)  # 生成14天的排班信息
        }
        
        # 构建session上下文字典
        session_context = {
            "user_id": user_id,
            "flow_info": flow_info,
            "doctor_info": doctor_info
        }
        
        # 获取上下文管理器
        context_manager = get_context_manager()
        
        # 为_session_contexts设置key为session_id，value为字典对象
        context_manager._session_contexts[session_id] = session_context
        
        # 持久化到数据库（新增）
        session_repo = SessionCacheRepository(session)
        await session_repo.upsert_session(
            session_id=session_id,
            data_info=session_context  # Session上下文数据存储到data_info字段
        )
        
        await session.commit()
        
        logger.info(
            f"创建Session: user_id={user_id}, flow_name={flow_name}, "
            f"doctor_id={doctor_id}, session_id={session_id}"
        )
        
        return CreateSessionResponse(session_id=session_id)
        
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"创建Session失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建Session失败: {str(e)}")


@router.get("/login/token/{token_id}", response_model=TokenInfoResponse)
async def get_token_info(token_id: str) -> TokenInfoResponse:
    """
    根据Token ID查询Token信息
    
    Args:
        token_id: Token ID
        
    Returns:
        TokenInfoResponse: Token信息响应
    """
    try:
        # 获取上下文管理器
        context_manager = get_context_manager()
        
        # 从_token_contexts获取UserInfo对象
        user_info_obj = context_manager._token_contexts.get(token_id)
        
        if user_info_obj is None:
            raise HTTPException(status_code=404, detail=f"Token不存在: {token_id}")
        
        # 如果存储的是UserInfo对象，提取信息
        if isinstance(user_info_obj, UserInfo):
            user_id = user_info_obj.user_id
            user_info = user_info_obj.get_user_info()
        else:
            # 兼容其他格式
            user_id = token_id
            user_info = None
        
        logger.info(f"查询Token信息: token_id={token_id}")
        
        return TokenInfoResponse(
            token_id=token_id,
            user_id=user_id,
            user_info=user_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询Token信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询Token信息失败: {str(e)}")


@router.get("/login/session/{session_id}", response_model=SessionInfoResponse)
async def get_session_info(session_id: str) -> SessionInfoResponse:
    """
    根据Session ID查询Session信息
    
    Args:
        session_id: Session ID
        
    Returns:
        SessionInfoResponse: Session信息响应
    """
    try:
        # 获取上下文管理器
        context_manager = get_context_manager()
        
        # 从_session_contexts获取session上下文
        session_context = context_manager._session_contexts.get(session_id)
        
        if session_context is None:
            raise HTTPException(status_code=404, detail=f"Session不存在: {session_id}")
        
        # 提取信息
        user_id = session_context.get("user_id")
        flow_info = session_context.get("flow_info", {})
        doctor_info = session_context.get("doctor_info", {})
        
        if not user_id:
            raise HTTPException(status_code=500, detail="Session数据格式错误：缺少user_id")
        
        logger.info(f"查询Session信息: session_id={session_id}")
        
        return SessionInfoResponse(
            session_id=session_id,
            user_id=user_id,
            flow_info=flow_info,
            doctor_info=doctor_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询Session信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询Session信息失败: {str(e)}")

