"""
API 路由定义
"""
import logging
import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Header
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserListResponse
from app.core.config import settings
from domain.router.state import RouterState
from infrastructure.database.connection import get_async_session
from infrastructure.database.repository.user_repository import UserRepository
from infrastructure.observability.langfuse_handler import set_langfuse_trace_context

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    app_request: Request,
    x_trace_id: Optional[str] = Header(None, alias="X-Trace-ID")
) -> ChatResponse:
    """
    聊天接口
    
    Args:
        request: 聊天请求
        app_request: FastAPI 请求对象（用于获取应用状态）
        x_trace_id: 请求头中的 Trace ID（可选，如果未提供则自动生成）
        
    Returns:
        聊天响应
    """
    # 获取或生成 traceId
    trace_id = x_trace_id or str(uuid.uuid4())
    
    # 设置 Langfuse trace 上下文（如果启用）
    if settings.LANGFUSE_ENABLED:
        set_langfuse_trace_context(
            name="chat_request",
            user_id=request.user_id,
            session_id=request.session_id,
            trace_id=trace_id,
            metadata={
                "message_length": len(request.message),
                "history_count": len(request.conversation_history) if request.conversation_history else 0,
            }
        )
    
    # 记录请求开始
    logger.info(
        f"[Chat请求开始] session_id={request.session_id}, "
        f"user_id={request.user_id}, "
        f"message_length={len(request.message)}, "
        f"history_count={len(request.conversation_history) if request.conversation_history else 0}"
    )
    
    # 记录用户消息内容（截断过长内容）
    message_preview = request.message[:100] + "..." if len(request.message) > 100 else request.message
    logger.debug(f"[Chat消息内容] session_id={request.session_id}, message={message_preview}")
    
    # 获取路由图
    router_graph = app_request.app.state.router_graph
    checkpointer = app_request.app.state.checkpointer
    
    if not router_graph:
        logger.error(f"[Chat错误] session_id={request.session_id}, 路由图未初始化")
        raise HTTPException(status_code=500, detail="路由图未初始化")
    
    # 构建消息列表
    messages = []
    if request.conversation_history:
        for msg in request.conversation_history:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))
    
    # 添加当前用户消息
    messages.append(HumanMessage(content=request.message))
    
    logger.debug(f"[Chat消息构建] session_id={request.session_id}, total_messages={len(messages)}")
    
    # 构建初始状态（包含 trace_id）
    initial_state: RouterState = {
        "messages": messages,
        "current_intent": None,
        "current_agent": None,
        "need_reroute": True,
        "session_id": request.session_id,
        "user_id": request.user_id,
        "trace_id": trace_id
    }
    
    # 配置（包含 checkpointer）
    # 注意：checkpointer 应该在编译图时传入，而不是在运行时配置
    config: Dict[str, Any] = {
        "configurable": {
            "thread_id": request.session_id
        }
    }
    
    # 执行路由图
    try:
        logger.info(f"[Chat路由图执行] session_id={request.session_id}, 开始执行路由图")
        result = None
        event_count = 0
        async for event in router_graph.astream(initial_state, config=config):
            event_count += 1
            # 获取最后一个节点的输出
            for node_name, node_output in event.items():
                result = node_output
                logger.debug(
                    f"[Chat路由图节点] session_id={request.session_id}, "
                    f"node={node_name}, event_count={event_count}"
                )
        
        logger.info(
            f"[Chat路由图完成] session_id={request.session_id}, "
            f"total_events={event_count}"
        )
        
        if not result:
            logger.error(f"[Chat错误] session_id={request.session_id}, 路由图执行失败，无返回结果")
            raise HTTPException(status_code=500, detail="路由图执行失败")
        
        # 获取最后一条助手消息
        response_message = None
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage):
                response_message = msg
                break
        
        if not response_message:
            response_message = "抱歉，我无法理解您的问题。"
            logger.warning(f"[Chat警告] session_id={request.session_id}, 未找到助手消息，使用默认回复")
        else:
            response_message = response_message.content
        
        # 获取意图和智能体信息
        intent = result.get("current_intent")
        agent = result.get("current_agent")
        
        logger.info(
            f"[Chat请求完成] session_id={request.session_id}, "
            f"intent={intent}, agent={agent}, "
            f"response_length={len(response_message)}"
        )
        
        # 记录响应内容预览（截断过长内容）
        response_preview = response_message[:100] + "..." if len(response_message) > 100 else response_message
        logger.debug(f"[Chat响应内容] session_id={request.session_id}, response={response_preview}")
        
        return ChatResponse(
            response=response_message,
            session_id=request.session_id,
            intent=intent,
            agent=agent
        )
    
    except HTTPException:
        # HTTPException 需要重新抛出，不记录为错误
        raise
    except Exception as e:
        logger.error(
            f"[Chat异常] session_id={request.session_id}, "
            f"error={str(e)}, error_type={type(e).__name__}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"处理请求时出错: {str(e)}")


# ==================== 用户管理接口 ====================

@router.get("/users", response_model=UserListResponse)
async def list_users(
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_async_session)
) -> UserListResponse:
    """
    获取用户列表
    
    Args:
        limit: 限制数量
        offset: 偏移量
        session: 数据库会话
        
    Returns:
        用户列表响应
    """
    try:
        user_repo = UserRepository(session)
        users = await user_repo.get_all(limit=limit, offset=offset)
        
        # 转换为响应模型
        user_responses = [UserResponse.model_validate(user) for user in users]
        
        # 获取总数（简单实现，实际可以使用 count 查询）
        total = len(await user_repo.get_all(limit=10000, offset=0))
        
        return UserListResponse(users=user_responses, total=total)
    except Exception as e:
        logger.error(f"[用户列表错误] error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取用户列表失败: {str(e)}")


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    session: AsyncSession = Depends(get_async_session)
) -> UserResponse:
    """
    根据ID获取用户
    
    Args:
        user_id: 用户ID
        session: 数据库会话
        
    Returns:
        用户响应
    """
    try:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        
        if not user:
            raise HTTPException(status_code=404, detail=f"用户不存在: {user_id}")
        
        return UserResponse.model_validate(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[获取用户错误] user_id={user_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取用户失败: {str(e)}")


@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    session: AsyncSession = Depends(get_async_session)
) -> UserResponse:
    """
    创建用户
    
    Args:
        user_data: 用户创建数据
        session: 数据库会话
        
    Returns:
        创建的用户响应
    """
    try:
        user_repo = UserRepository(session)
        
        # 检查用户名是否已存在
        existing_user = await user_repo.get_by_username(user_data.username)
        if existing_user:
            raise HTTPException(status_code=400, detail=f"用户名已存在: {user_data.username}")
        
        # 创建用户
        user = await user_repo.create(**user_data.model_dump())
        await session.commit()
        await session.refresh(user)
        
        return UserResponse.model_validate(user)
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"[创建用户错误] error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建用户失败: {str(e)}")


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    session: AsyncSession = Depends(get_async_session)
) -> UserResponse:
    """
    更新用户
    
    Args:
        user_id: 用户ID
        user_data: 用户更新数据
        session: 数据库会话
        
    Returns:
        更新后的用户响应
    """
    try:
        user_repo = UserRepository(session)
        
        # 检查用户是否存在
        user = await user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"用户不存在: {user_id}")
        
        # 如果更新用户名，检查是否与其他用户冲突
        if user_data.username and user_data.username != user.username:
            existing_user = await user_repo.get_by_username(user_data.username)
            if existing_user:
                raise HTTPException(status_code=400, detail=f"用户名已存在: {user_data.username}")
        
        # 更新用户（只更新提供的字段）
        update_data = {k: v for k, v in user_data.model_dump().items() if v is not None}
        updated_user = await user_repo.update(user_id, **update_data)
        await session.commit()
        await session.refresh(updated_user)
        
        return UserResponse.model_validate(updated_user)
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"[更新用户错误] user_id={user_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新用户失败: {str(e)}")


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    session: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    删除用户
    
    Args:
        user_id: 用户ID
        session: 数据库会话
        
    Returns:
        删除结果
    """
    try:
        user_repo = UserRepository(session)
        
        # 检查用户是否存在
        user = await user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"用户不存在: {user_id}")
        
        # 删除用户
        success = await user_repo.delete(user_id)
        await session.commit()
        
        if not success:
            raise HTTPException(status_code=500, detail="删除用户失败")
        
        return {"message": "用户删除成功", "user_id": user_id}
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"[删除用户错误] user_id={user_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除用户失败: {str(e)}")


# ==================== Agent管理接口 ====================

@router.post("/agents/{agent_key}/reload")
async def reload_agent(agent_key: str) -> Dict[str, Any]:
    """
    重新加载指定Agent（热更新）
    
    Args:
        agent_key: Agent键名（如 "blood_pressure_agent"）
        
    Returns:
        重新加载结果
    """
    try:
        from domain.agents.factory import AgentFactory
        
        # 检查Agent是否存在
        if agent_key not in AgentFactory.list_agents():
            raise HTTPException(status_code=404, detail=f"Agent不存在: {agent_key}")
        
        # 重新加载Agent
        agent = AgentFactory.reload_agent(agent_key)
        
        logger.info(f"[Agent热更新] agent_key={agent_key}, 重新加载成功")
        
        return {
            "message": "Agent重新加载成功",
            "agent_key": agent_key,
            "cached": AgentFactory.is_cached(agent_key)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Agent热更新错误] agent_key={agent_key}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重新加载Agent失败: {str(e)}")


@router.post("/agents/reload-all")
async def reload_all_agents() -> Dict[str, Any]:
    """
    重新加载所有Agent（热更新）
    
    Returns:
        重新加载结果
    """
    try:
        from domain.agents.factory import AgentFactory
        
        # 重新加载所有Agent
        agents = AgentFactory.reload_all_agents()
        
        logger.info(f"[Agent热更新] 重新加载所有Agent成功, 共 {len(agents)} 个Agent")
        
        return {
            "message": "所有Agent重新加载成功",
            "agent_count": len(agents),
            "agent_keys": list(agents.keys())
        }
    except Exception as e:
        logger.error(f"[Agent热更新错误] 重新加载所有Agent失败, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重新加载所有Agent失败: {str(e)}")


@router.get("/agents/cache/stats")
async def get_agent_cache_stats() -> Dict[str, Any]:
    """
    获取Agent缓存统计信息
    
    Returns:
        缓存统计信息
    """
    try:
        from domain.agents.factory import AgentFactory
        
        stats = AgentFactory.get_cache_stats()
        
        return {
            "cache_stats": stats
        }
    except Exception as e:
        logger.error(f"[获取缓存统计错误] error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取缓存统计失败: {str(e)}")


@router.delete("/agents/cache")
async def clear_agent_cache(agent_key: Optional[str] = None) -> Dict[str, Any]:
    """
    清除Agent缓存
    
    Args:
        agent_key: Agent键名（可选，如果不提供则清除所有缓存）
        
    Returns:
        清除结果
    """
    try:
        from domain.agents.factory import AgentFactory
        
        if agent_key:
            # 检查Agent是否存在
            if agent_key not in AgentFactory.list_agents():
                raise HTTPException(status_code=404, detail=f"Agent不存在: {agent_key}")
            AgentFactory.clear_cache(agent_key)
            message = f"Agent缓存已清除: {agent_key}"
        else:
            AgentFactory.clear_cache()
            message = "所有Agent缓存已清除"
        
        logger.info(f"[清除Agent缓存] {message}")
        
        return {
            "message": message,
            "agent_key": agent_key
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[清除Agent缓存错误] agent_key={agent_key}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"清除Agent缓存失败: {str(e)}")

