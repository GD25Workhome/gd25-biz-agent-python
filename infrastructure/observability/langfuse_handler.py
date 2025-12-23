"""
Langfuse 集成模块
负责与 Langfuse 的交互，提供 Traces、Spans 和 Generations 追踪功能
"""
import logging
from typing import Optional, TYPE_CHECKING

from app.core.config import settings
from infrastructure.observability.llm_logger import LlmLogContext

logger = logging.getLogger(__name__)


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

# 延迟导入 Langfuse，避免在未安装时出错
try:
    from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    LangfuseCallbackHandler = None  # type: ignore
    Langfuse = None  # type: ignore
    logger.warning("Langfuse未安装，可观测性功能将无法使用")

if TYPE_CHECKING:
    from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
    from langfuse import Langfuse

# 全局 Langfuse 客户端实例（延迟初始化）
_langfuse_client: Optional["Langfuse"] = None


def create_langfuse_handler(
    context: Optional[LlmLogContext] = None
) -> "LangfuseCallbackHandler":
    """
    创建 Langfuse Callback Handler
    
    Args:
        context: LLM 调用上下文（用于链路追踪、用户/会话标记）
        
    Returns:
        LangfuseCallbackHandler: Langfuse 回调处理器
        
    Raises:
        ValueError: Langfuse未启用或配置不完整
        ImportError: Langfuse未安装
    """
    if not LANGFUSE_AVAILABLE:
        raise ImportError("Langfuse未安装，请安装langfuse包")
    
    if not settings.LANGFUSE_ENABLED:
        raise ValueError("Langfuse未启用，请设置LANGFUSE_ENABLED=True")
    
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        raise ValueError("Langfuse配置不完整，请设置LANGFUSE_PUBLIC_KEY和LANGFUSE_SECRET_KEY")
    
    # 确保全局 Langfuse 客户端已初始化（用于 secret_key 和 host 配置）
    # langfuse 3.x 的 CallbackHandler 会使用全局客户端配置
    _get_langfuse_client()
    
    # 构建 trace_context（用于分布式追踪）
    trace_context = None
    if context and context.trace_id:
        trace_context = {"trace_id": context.trace_id}
        # 如果有 parent_span_id，也可以添加
        # trace_context["parent_span_id"] = context.parent_span_id
    
    # 创建 Langfuse Callback Handler
    # langfuse 3.x 中，CallbackHandler 只需要 public_key 和 trace_context
    # secret_key、host 等通过全局客户端配置（已在上面初始化）
    handler = LangfuseCallbackHandler(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        update_trace=True,  # 更新 trace 信息
        trace_context=trace_context,
    )
    
    logger.debug(
        f"创建Langfuse Callback Handler: "
        f"trace_context={trace_context}"
    )
    
    return handler


def _get_langfuse_client() -> Optional["Langfuse"]:
    """
    获取或创建 Langfuse 客户端实例
    
    Returns:
        Langfuse 客户端实例，如果未启用则返回 None
    """
    global _langfuse_client
    
    if not LANGFUSE_AVAILABLE:
        return None
    
    if not settings.LANGFUSE_ENABLED:
        return None
    
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        return None
    
    # 延迟初始化客户端
    if _langfuse_client is None:
        _langfuse_client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
    
    return _langfuse_client


def set_langfuse_trace_context(
    name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[str]:
    """
    设置 Langfuse trace 上下文
    
    在 API 路由层调用此函数，为整个请求链路创建 Trace。
    后续的 LLM 调用和节点执行会自动关联到此 Trace。
    
    Args:
        name: trace 名称（如 "chat_request"）
        user_id: 用户 ID
        session_id: 会话 ID
        trace_id: Trace ID（如果提供，使用该 ID；否则由 Langfuse 生成）
        metadata: 元数据（如 message_length、history_count 等）
        
    Returns:
        返回使用的 trace_id（如果 trace_id 为 None，返回传入的 trace_id）
    """
    if not LANGFUSE_AVAILABLE:
        logger.debug("Langfuse未安装，跳过Trace上下文设置")
        return trace_id
    
    if not settings.LANGFUSE_ENABLED:
        logger.debug("Langfuse未启用，跳过Trace上下文设置")
        return trace_id
    
    try:
        client = _get_langfuse_client()
        if client:
            # 如果提供了 trace_id，先转换为 Langfuse 要求的格式
            normalized_trace_id = None
            if trace_id:
                normalized_trace_id = normalize_langfuse_trace_id(trace_id)
            
            # 构建更新参数
            update_params = {
                "name": name,
                "user_id": user_id,
                "session_id": session_id,
                "metadata": metadata,
            }
            
            # 如果提供了 trace_id，尝试使用它（注意：Langfuse SDK 可能不支持 id 参数，需要根据实际 API 调整）
            # 目前先尝试使用 id 参数，如果失败则回退到不使用 id
            if normalized_trace_id:
                try:
                    # 尝试使用 id 参数（使用转换后的 trace_id）
                    client.update_current_trace(id=normalized_trace_id, **update_params)
                except (TypeError, AttributeError):
                    # 如果 SDK 不支持 id 参数，记录警告但继续执行
                    logger.warning(
                        f"Langfuse SDK 可能不支持 id 参数，将使用默认行为。trace_id={normalized_trace_id}"
                    )
                    client.update_current_trace(**update_params)
            else:
                # 由 Langfuse 生成 trace_id
                client.update_current_trace(**update_params)
            
            logger.debug(
                f"设置Langfuse Trace上下文: name={name}, "
                f"user_id={user_id}, session_id={session_id}, "
                f"trace_id={normalized_trace_id or trace_id}, metadata={metadata}"
            )
            
            return normalized_trace_id or trace_id
    except Exception as e:
        # 如果设置失败，记录警告但不影响主流程
        logger.warning(f"设置Langfuse Trace上下文失败: {e}，继续执行但不记录到Langfuse")
        return trace_id


def is_langfuse_available() -> bool:
    """
    检查 Langfuse 是否可用
    
    Returns:
        如果 Langfuse 已安装且已启用，返回 True；否则返回 False
    """
    if not LANGFUSE_AVAILABLE:
        return False
    if not settings.LANGFUSE_ENABLED:
        return False
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        return False
    return True


def get_langfuse_client():
    """
    获取 Langfuse 客户端实例（用于创建 Span）
    
    Returns:
        Langfuse 客户端实例，如果 Langfuse 不可用则返回 None
        
    注意：
        此函数返回的 Langfuse 客户端可以用于创建 Span：
        ```python
        from infrastructure.observability.langfuse_handler import get_langfuse_client
        
        langfuse_client = get_langfuse_client()
        if langfuse_client:
            with langfuse_client.start_as_current_span(
                name="span_name",
                input={},
                metadata={}
            ):
                # 执行代码
        ```
    """
    if not is_langfuse_available():
        return None
    
    return _get_langfuse_client()

