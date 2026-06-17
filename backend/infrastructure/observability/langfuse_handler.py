"""
Langfuse可观测性集成
提供Trace追踪、LLM调用日志记录等功能
"""
import logging
from typing import Optional, Dict, Any
from contextvars import ContextVar

from backend.app.config import settings

# 直接导入，如果模块不存在会直接报错，便于及时发现配置问题
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler

logger = logging.getLogger(__name__)

# 全局Langfuse客户端实例
_langfuse_client: Optional["Langfuse"] = None

# Trace上下文变量（用于在异步上下文中传递Trace ID）
_trace_context: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def set_langfuse_trace_context(
    name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    设置Langfuse Trace上下文
    
    在API路由层调用此函数创建Trace，后续的LLM调用和节点执行会自动关联到此Trace。
    
    Args:
        name: Trace名称
        user_id: 用户ID（可选）
        session_id: 会话ID（可选）
        trace_id: 自定义Trace ID（可选，如果不提供则自动生成）
        metadata: 元数据（可选）
        
    Returns:
        str: Trace ID（用于后续关联）
    """
    # 先检查Langfuse是否可用
    if not is_langfuse_available():
        logger.debug("Langfuse不可用，跳过Trace创建")
        return trace_id
    
    langfuse_client = get_langfuse_client()
    if not langfuse_client:
        logger.warning("Langfuse客户端获取失败，跳过Trace创建")
        return trace_id
    
    # trace_id 必须提供，否则抛出异常（放在 try 块外，确保异常能直接传播）
    if not trace_id:
        raise ValueError("trace_id 是必需的参数，不能为 None 或空字符串")
    
    try:
        # 规范化 trace_id
        normalized_trace_id = normalize_langfuse_trace_id(trace_id)
        
        # 构建 trace 参数（参考 test_flow_trace.py 的实现方式）
        trace_params = {
            "name": name,
            "metadata": metadata or {},
        }
        
        # 如果提供了 trace_id，通过 trace_context 参数传入（参考 test_flow_trace.py 的做法）
        trace_params["trace_context"] = {"trace_id": normalized_trace_id}
        
        # 使用 start_as_current_span() 创建 Trace（参考 test_flow_trace.py 的正确调用方式）
        # 这会创建一个活动的 span 上下文，后续的所有 span 都会自动关联到这个 trace
        # 注意：start_as_current_span 使用 contextvars 管理上下文，即使不在 with 语句中也能保持活动状态
        langfuse_client.start_as_current_span(**trace_params).__enter__()
        
        # 在 Trace 上下文中，更新 trace 元数据（参考 test_flow_trace.py 的做法）
        langfuse_client.update_current_trace(
            name=name,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata or {},
        )
        
        # 将Trace ID存储到上下文变量中
        _trace_context.set(normalized_trace_id)
        
        logger.info(
            f"[Langfuse] 设置Trace上下文成功: name={name}, trace_id={normalized_trace_id}, "
            f"user_id={user_id}, session_id={session_id}, metadata={metadata}"
        )
        
        return normalized_trace_id
    
    except Exception as e:
        # 如果设置失败，记录警告但不影响主流程
        logger.warning(f"[Langfuse] 设置Trace上下文失败: {e}，继续执行但不记录到Langfuse", exc_info=True)
        return trace_id


def get_current_trace_id() -> Optional[str]:
    """
    获取当前上下文的Trace ID
    
    Returns:
        str: Trace ID，如果未设置则返回None
    """
    return _trace_context.get()


def create_langfuse_handler(
    context: Optional[Dict[str, Any]] = None,
) -> Optional["LangfuseCallbackHandler"]:
    """
        创建 Langfuse CallbackHandler，供 LangGraph / LLM 调用链自动上报观测数据。

        Handler 通过 trace_context 将本次 LLM 调用挂到已有 Trace（chat 路由传入的
        trace_id 或 set_langfuse_trace_context 写入的 ContextVar）。

        Args:
            context: 可选上下文字典；含 trace_id 时优先用于关联 Trace

        Returns:
            Langfuse CallbackHandler；未启用、配置缺失或创建失败时返回 None
    """
    # 1. 校验 Langfuse 开关与密钥配置
    if not settings.LANGFUSE_ENABLED:
        logger.debug("[Langfuse] CallbackHandler: Langfuse未启用")
        return None

    public_key = settings.LANGFUSE_PUBLIC_KEY
    secret_key = settings.LANGFUSE_SECRET_KEY
    if not public_key or not secret_key:
        logger.warning(
            "[Langfuse] CallbackHandler: 配置不完整，缺少PUBLIC_KEY或SECRET_KEY。"
            "请检查.env文件配置。"
        )
        return None

    # 2. 初始化全局客户端（langfuse 3.x CallbackHandler 复用其 host / secret_key）
    # _get_langfuse_client：单例初始化 Langfuse 客户端
    _get_langfuse_client()

    # 3. 解析 trace_id：context 参数优先，否则回退 ContextVar
    trace_context: Optional[Dict[str, str]] = None
    trace_id: Optional[str] = None
    if context and isinstance(context, dict) and context.get("trace_id"):
        trace_id = context.get("trace_id")
        logger.debug(f"[Langfuse] CallbackHandler: 从 context 参数获取 trace_id={trace_id}")
    else:
        trace_id = get_current_trace_id()
        if trace_id:
            logger.debug(f"[Langfuse] CallbackHandler: 从 ContextVar 获取 trace_id={trace_id}")
        else:
            logger.warning("[Langfuse] CallbackHandler: 无法获取 trace_id，将创建新的 trace")

    # 4. 规范化 trace_id 并构建 trace_context
    if trace_id:
        # normalize_langfuse_trace_id：转为 Langfuse 要求的 32 位小写十六进制
        normalized_trace_id = normalize_langfuse_trace_id(trace_id)
        trace_context = {"trace_id": normalized_trace_id}

    # 5. 实例化 CallbackHandler（secret_key 经全局客户端传递，此处仅传 public_key）
    try:
        handler = LangfuseCallbackHandler(
            public_key=public_key,
            update_trace=True,
            trace_context=trace_context,
        )
        logger.debug(
            f"[Langfuse] CallbackHandler创建成功: "
            f"trace_context={trace_context}, context={context}"
        )
        return handler

    except Exception as e:
        logger.error(f"[Langfuse] CallbackHandler创建失败: {e}", exc_info=True)
        return None

def normalize_langfuse_trace_id(trace_id: str) -> str:
    """
    将 trace_id 转换为 Langfuse 要求的格式
    
    Langfuse SDK 要求 trace_id 必须是 32 个小写十六进制字符（不带连字符）。
    如果传入的是 UUID v4 格式（带连字符），需要转换为 32 位十六进制字符串。
    
    Args:
        trace_id: 原始的 trace_id（可能是 UUID v4 格式或其他格式）
        
    Returns:
        符合 Langfuse 要求的 trace_id（32 个小写十六进制字符）
        
    Example:
        >>> normalize_langfuse_trace_id("2ae02464-a2ed-48dc-9802-ea8200e1ca6a")
        "2ae02464a2ed48dc9802ea8200e1ca6a"
    """
    # 移除连字符并转换为小写
    normalized = trace_id.replace("-", "").lower()
    
    # 验证是否为有效的十六进制字符串
    try:
        int(normalized, 16)
    except ValueError:
        logger.warning(f"trace_id 不是有效的十六进制字符串: {trace_id}")
        # 如果无效，返回原值（让 Langfuse SDK 自己处理）
        return trace_id
    
    # 如果长度不是 32，记录警告但返回转换后的值
    if len(normalized) != 32:
        logger.warning(
            f"trace_id 长度不是 32 位: {trace_id} (转换后: {normalized}, 长度: {len(normalized)})"
        )
    
    return normalized

def _get_langfuse_client() -> Optional["Langfuse"]:
    """
    获取或创建Langfuse客户端实例（单例模式）
    
    Returns:
        Langfuse: Langfuse客户端实例，如果未启用或初始化失败则返回None
    """
    global _langfuse_client
    
    # 检查是否启用Langfuse（从统一配置读取）
    if not settings.LANGFUSE_ENABLED:
        logger.debug("Langfuse未启用（settings.LANGFUSE_ENABLED=False）")
        return None
    
    # 如果已创建，直接返回
    if _langfuse_client is not None:
        return _langfuse_client
    
    try:
        # 从统一配置读取配置（支持 LANGFUSE_HOST 或 LANGFUSE_BASE_URL）
        public_key = settings.LANGFUSE_PUBLIC_KEY
        secret_key = settings.LANGFUSE_SECRET_KEY
        host = settings.langfuse_host_resolved
        
        if not public_key or not secret_key:
            logger.warning(
                "Langfuse配置不完整：缺少LANGFUSE_PUBLIC_KEY或LANGFUSE_SECRET_KEY，"
                "Langfuse功能将不可用。请检查.env文件配置。"
            )
            return None
        
        # 创建Langfuse客户端
        # 如果 host 为 None，Langfuse 会使用默认值（云端），本地不会收到数据
        if host is None:
            logger.warning(
                "LANGFUSE_HOST 与 LANGFUSE_BASE_URL 均未设置，Langfuse 将使用默认 host，"
                "数据会发往云端而非本地。请在 .env 中设置 LANGFUSE_HOST 或 LANGFUSE_BASE_URL"
            )
        
        langfuse_kwargs = {
            "public_key": public_key,
            "secret_key": secret_key,
        }
        if host:
            langfuse_kwargs["host"] = host
        
        _langfuse_client = Langfuse(**langfuse_kwargs)
        
        logger.info(
            f"Langfuse客户端初始化成功: host={host or 'default'}, "
            f"public_key_prefix={public_key[:8] if public_key else 'None'}..."
        )
        return _langfuse_client
    
    except Exception as e:
        logger.error(f"Langfuse客户端初始化失败: {e}", exc_info=True)
        return None

def is_langfuse_available() -> bool:
    """
    检查Langfuse是否可用
    
    Returns:
        bool: 如果Langfuse可用返回True，否则返回False
    """
    # 从统一配置读取
    if not settings.LANGFUSE_ENABLED:
        return False
    
    client = get_langfuse_client()
    return client is not None

def get_langfuse_client() -> Optional["Langfuse"]:
    """
    获取Langfuse客户端实例（公共接口）
    
    Returns:
        Langfuse: Langfuse客户端实例，如果未启用或初始化失败则返回None
    """
    return _get_langfuse_client()



