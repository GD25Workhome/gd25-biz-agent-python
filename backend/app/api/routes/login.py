"""
登录相关路由

提供 Token / Session 的创建与查询接口，并将用户上下文写入内存缓存与数据库持久化。
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
        生成医生排班信息（用于 Session 中的 doctor_info）。

        规则：
        - 从今天开始，往后生成指定天数的排班
        - 每周休息 4 个半天：随机选 2 天，每天随机选上午或下午
        - 工作时段：上午 8:00-12:00，下午 14:00-18:00；休息时段不输出对应字段

        Args:
            days: 生成排班的天数，默认为 14 天

        Returns:
            排班列表，每项含 date（YYYY-MM-DD），以及可选的 morning / afternoon 时段字符串
    """
    schedule: List[Dict[str, Any]] = []
    today = datetime.now().date()

    # 1. 计算覆盖周数，并为每周预生成休息半天安排
    weeks = (days + 6) // 7
    # rest_periods_by_week: {week_num: [(day_in_week, 'morning'|'afternoon'), ...]}
    rest_periods_by_week: Dict[int, List[tuple[int, str]]] = {}

    for week in range(weeks):
        # 每周随机选 2 个休息日，从其 4 个半天中打乱顺序（保证每周共休 4 个半天）
        rest_days = random.sample(range(7), 2)
        day1, day2 = rest_days[0], rest_days[1]
        all_periods = [
            (day1, "morning"), (day1, "afternoon"),
            (day2, "morning"), (day2, "afternoon"),
        ]
        rest_periods = random.sample(all_periods, 4)

        # 校验：每周恰好 4 个半天，且每个休息日至少休 1 个半天
        assert len(rest_periods) == 4, f"每周应该有4个半天休息，实际有{len(rest_periods)}个"
        day1_count = sum(1 for d, _ in rest_periods if d == day1)
        day2_count = sum(1 for d, _ in rest_periods if d == day2)
        assert day1_count >= 1 and day2_count >= 1, "每个休息日至少有1个半天休息"

        rest_periods_by_week[week] = rest_periods

    # 2. 按天生成排班条目，跳过休息半天
    for day_offset in range(days):
        current_date = today + timedelta(days=day_offset)
        week_num = day_offset // 7
        day_in_week = day_offset % 7

        week_rest_periods = rest_periods_by_week.get(week_num, [])
        morning_rest = (day_in_week, "morning") in week_rest_periods
        afternoon_rest = (day_in_week, "afternoon") in week_rest_periods

        day_schedule: Dict[str, Any] = {
            "date": current_date.strftime("%Y-%m-%d"),
        }
        if not morning_rest:
            day_schedule["morning"] = "8:00-12:00"
        if not afternoon_rest:
            day_schedule["afternoon"] = "14:00-18:00"

        schedule.append(day_schedule)

    return schedule


@router.post("/login/token", response_model=CreateTokenResponse)
async def create_token(
    request: CreateTokenRequest,
    session: AsyncSession = Depends(get_async_session),
) -> CreateTokenResponse:
    """
        创建 Token：以 user_id 为 token_id，加载用户信息并写入内存与数据库缓存。

        Args:
            request: 创建 Token 请求（含用户 ID）
            session: 数据库会话（依赖注入）

        Returns:
            含 token_id 的响应（token_id 与 user_id 相同）

        Raises:
            HTTPException: 用户不存在（404）或持久化失败（500）
    """
    try:
        user_id = request.user_id

        # 1. 从数据库加载用户，不存在则拒绝创建 Token
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail=f"用户不存在: {user_id}")

        # 2. 组装 UserInfo 并写入内存 _token_contexts
        user_info = UserInfo(user_id=user_id)
        if user.user_info:
            # set_user_info：将数据库中的用户扩展字段合并进 UserInfo
            user_info.set_user_info(user.user_info)

        context_manager = get_context_manager()
        context_manager._token_contexts[user_id] = user_info

        # 3. 持久化 Token 缓存并提交事务
        token_repo = TokenCacheRepository(session)
        # upsert_token：将 UserInfo.data 序列化写入 token_cache 表
        await token_repo.upsert_token(
            token_id=user_id,
            data_info=user_info.data,
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
    session: AsyncSession = Depends(get_async_session),
) -> CreateSessionResponse:
    """
        创建 Session：绑定用户、医生与流程，生成 session_id 并写入内存与数据库缓存。

        session_id 格式：{user_id}_{doctor_id}_{flow_name}。

        Args:
            request: 创建 Session 请求（含用户 ID、流程名称）
            session: 数据库会话（依赖注入）

        Returns:
            含 session_id 的响应

        Raises:
            HTTPException: 流程无效（400）、持久化失败（500）
    """
    try:
        user_id = request.user_id
        flow_name = request.flow_name
        doctor_id = "doctorId001"

        # 1. 校验流程名称：缓存未命中时先扫描 flows 目录
        if flow_name not in FlowManager._flow_definitions:
            # scan_flows：扫描 config/flows 并刷新流程定义缓存
            FlowManager.scan_flows()

        if flow_name not in FlowManager._flow_definitions:
            available_flows = list(FlowManager._flow_definitions.keys())
            raise HTTPException(
                status_code=400,
                detail=f"无效的流程名称: {flow_name}。支持的流程: {available_flows}",
            )

        flow_def = FlowManager._flow_definitions[flow_name]

        # 2. 组装 session 上下文（流程信息 + 医生排班）
        session_id = f"{user_id}_{doctor_id}_{flow_name}"
        flow_info = {
            "flow_key": flow_def.name,
            "flow_name": flow_def.description or flow_def.name,
        }
        doctor_info = {
            "doctor_id": doctor_id,
            "doctor_name": "张医生",
            "schedule": generate_doctor_schedule(days=14),
        }
        session_context = {
            "user_id": user_id,
            "flow_info": flow_info,
            "doctor_info": doctor_info,
        }

        # 3. 写入内存 _session_contexts 并持久化到数据库
        context_manager = get_context_manager()
        context_manager._session_contexts[session_id] = session_context

        session_repo = SessionCacheRepository(session)
        # upsert_session：将 session 上下文字典写入 session_cache 表
        await session_repo.upsert_session(
            session_id=session_id,
            data_info=session_context,
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
        根据 token_id 从内存缓存查询 Token 关联的用户信息。

        Args:
            token_id: Token ID（与 user_id 相同）

        Returns:
            Token 及用户扩展信息

        Raises:
            HTTPException: Token 不存在（404）或查询失败（500）
    """
    try:
        context_manager = get_context_manager()
        user_info_obj = context_manager._token_contexts.get(token_id)

        if user_info_obj is None:
            raise HTTPException(status_code=404, detail=f"Token不存在: {token_id}")

        # 从 UserInfo 对象提取字段；兼容非 UserInfo 的历史缓存格式
        if isinstance(user_info_obj, UserInfo):
            user_id = user_info_obj.user_id
            user_info = user_info_obj.get_user_info()
        else:
            user_id = token_id
            user_info = None

        logger.info(f"查询Token信息: token_id={token_id}")
        return TokenInfoResponse(
            token_id=token_id,
            user_id=user_id,
            user_info=user_info,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询Token信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询Token信息失败: {str(e)}")


@router.get("/login/session/{session_id}", response_model=SessionInfoResponse)
async def get_session_info(session_id: str) -> SessionInfoResponse:
    """
        根据 session_id 从内存缓存查询 Session 上下文（用户、流程、医生信息）。

        Args:
            session_id: Session ID

        Returns:
            Session 上下文详情

        Raises:
            HTTPException: Session 不存在（404）、数据格式错误（500）或查询失败（500）
    """
    try:
        context_manager = get_context_manager()
        session_context = context_manager._session_contexts.get(session_id)

        if session_context is None:
            raise HTTPException(status_code=404, detail=f"Session不存在: {session_id}")

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
            doctor_info=doctor_info,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询Session信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询Session信息失败: {str(e)}")
