"""
API 装饰器
用于拦截请求并验证上下文缓存
"""
import logging
import functools
import secrets
from typing import Callable, Any, Optional
from fastapi import Request, HTTPException

from backend.domain.context.context_manager import get_context_manager
from backend.app.api.schemas.chat import ChatRequest

logger = logging.getLogger(__name__)


def validate_context_cache(func: Callable) -> Callable:
    """
    验证上下文缓存的装饰器
    
    功能：
    1. 从请求头（X-Token-Id、X-Session-Id）或 ChatRequest 中提取 token_id 和 session_id
    2. 检查 ContextManager 缓存中是否存在对应的上下文
    3. 如果不存在，抛出 HTTPException
    4. 如果存在，将值设置到 ChatRequest 对象的 session_id 和 token_id 字段
    
    使用方式：
        @router.post("/chat")
        @validate_context_cache
        async def chat(request: ChatRequest, app_request: Request):
            ...
    
    Raises:
        HTTPException: 如果上下文缓存中不存在对应的 token_id 或 session_id
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        # 从参数中提取 Request 和 ChatRequest 对象
        request: Optional[Request] = None
        chat_request: Optional[ChatRequest] = None
        
        # 从位置参数中查找
        for arg in args:
            if isinstance(arg, Request):
                request = arg
            elif isinstance(arg, ChatRequest):
                chat_request = arg
        
        # 从关键字参数中查找
        for key, value in kwargs.items():
            if isinstance(value, Request):
                request = value
            elif isinstance(value, ChatRequest):
                chat_request = value
        
        # 提取 token_id、session_id 和 trace_id
        token_id: Optional[str] = None
        session_id: Optional[str] = None
        trace_id: Optional[str] = None
        
        # 优先级1：从请求头获取
        if request:
            token_id = request.headers.get("X-Token-Id")
            session_id = request.headers.get("X-Session-Id")
            trace_id = request.headers.get("X-Trace-ID")
        
        # 优先级2：从 ChatRequest 中获取（如果请求头中没有）
        if chat_request:
            if not token_id:
                token_id = chat_request.token_id
            if not session_id:
                session_id = chat_request.session_id
            if not trace_id:
                trace_id = chat_request.trace_id
        
        # 验证参数是否存在
        if not token_id:
            logger.error("无法获取 token_id：请求头和请求体中都不存在")
            raise HTTPException(
                status_code=400,
                detail="缺少必要的参数：token_id（请通过请求头 X-Token-Id 或请求体提供）"
            )
        
        if not session_id:
            logger.error("无法获取 session_id：请求头和请求体中都不存在")
            raise HTTPException(
                status_code=400,
                detail="缺少必要的参数：session_id（请通过请求头 X-Session-Id 或请求体提供）"
            )
        
        # 获取上下文管理器
        context_manager = get_context_manager()
        
        # 检查缓存中是否存在
        session_context_exists = session_id in context_manager._session_contexts
        token_context_exists = token_id in context_manager._token_contexts
        
        # 如果不存在，抛出异常
        if not session_context_exists:
            logger.warning(
                f"SessionContext 不存在于缓存中: session_id={session_id}"
            )
            raise HTTPException(
                status_code=404,
                detail=f"会话上下文不存在：session_id={session_id}（请先创建会话上下文）"
            )
        
        if not token_context_exists:
            logger.warning(
                f"TokenContext 不存在于缓存中: token_id={token_id}"
            )
            raise HTTPException(
                status_code=404,
                detail=f"令牌上下文不存在：token_id={token_id}（请先创建令牌上下文）"
            )
        
        # 如果存在，将值设置到 ChatRequest 对象
        if chat_request:
            # 检查并生成 traceId（如果不存在）
            if not trace_id:
                # 使用 secrets.token_hex(16) 生成32位十六进制字符（16字节 = 32个十六进制字符）
                trace_id = secrets.token_hex(16)
                logger.debug(f"自动生成 trace_id: {trace_id}")
            
            # 使用 Pydantic 的 model_copy 方法创建新实例并更新字段
            # 这样可以确保字段值正确更新
            updated_chat_request = chat_request.model_copy(
                update={
                    "token_id": token_id,
                    "session_id": session_id,
                    "trace_id": trace_id
                }
            )
            
            # 替换参数中的 ChatRequest 对象
            # 更新位置参数
            new_args = []
            for arg in args:
                if isinstance(arg, ChatRequest):
                    new_args.append(updated_chat_request)
                else:
                    new_args.append(arg)
            
            # 更新关键字参数
            new_kwargs = {}
            for key, value in kwargs.items():
                if isinstance(value, ChatRequest):
                    new_kwargs[key] = updated_chat_request
                else:
                    new_kwargs[key] = value
            
            logger.debug(
                f"装饰器验证通过并设置值: token_id={token_id}, session_id={session_id}, trace_id={trace_id}"
            )
            
            # 使用更新后的参数执行原函数
            return await func(*new_args, **new_kwargs)
        
        # 如果没有 ChatRequest 对象，直接执行原函数
        return await func(*args, **kwargs)
    
    return wrapper

