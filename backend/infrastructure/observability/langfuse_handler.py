"""
Langfuse可观测性集成
提供 Trace 追踪、LLM 调用日志记录等功能

华院小镜像：langfuse 为可选依赖，未安装或未启用时全部降级为 no-op。
"""
from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Dict, Optional, TYPE_CHECKING

from backend.app.config import settings

if TYPE_CHECKING:
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler

logger = logging.getLogger(__name__)

# 全局 Langfuse 客户端实例
_langfuse_client: Optional["Langfuse"] = None

# Trace 上下文变量
_trace_context: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def _import_langfuse():
    """
        按需导入 langfuse SDK。

        Returns:
            (Langfuse, CallbackHandler) 或 (None, None)
    """
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler

        return Langfuse, LangfuseCallbackHandler
    except ImportError:
        logger.warning(
            "未安装 langfuse 包，可观测性功能不可用。"
            "如需启用请安装 langfuse 并设置 LANGFUSE_ENABLED=true"
        )
        return None, None


def set_langfuse_trace_context(
    name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
        设置 Langfuse Trace 上下文。

        Args:
            name: Trace 名称
            user_id: 用户 ID（可选）
            session_id: 会话 ID（可选）
            trace_id: 自定义 Trace ID（必需）
            metadata: 元数据（可选）

        Returns:
            Trace ID；不可用时原样返回传入的 trace_id
    """
    if not is_langfuse_available():
        logger.debug("Langfuse不可用，跳过Trace创建")
        return trace_id

    langfuse_client = get_langfuse_client()
    if not langfuse_client:
        logger.warning("Langfuse客户端获取失败，跳过Trace创建")
        return trace_id

    if not trace_id:
        raise ValueError("trace_id 是必需的参数，不能为 None 或空字符串")

    try:
        normalized_trace_id = normalize_langfuse_trace_id(trace_id)
        trace_params = {
            "name": name,
            "metadata": metadata or {},
            "trace_context": {"trace_id": normalized_trace_id},
        }
        langfuse_client.start_as_current_span(**trace_params).__enter__()
        langfuse_client.update_current_trace(
            name=name,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata or {},
        )
        _trace_context.set(normalized_trace_id)
        logger.info(
            f"[Langfuse] 设置Trace上下文成功: name={name}, trace_id={normalized_trace_id}, "
            f"user_id={user_id}, session_id={session_id}, metadata={metadata}"
        )
        return normalized_trace_id
    except Exception as e:
        logger.warning(
            f"[Langfuse] 设置Trace上下文失败: {e}，继续执行但不记录到Langfuse",
            exc_info=True,
        )
        return trace_id


def get_current_trace_id() -> Optional[str]:
    """获取当前上下文的 Trace ID。"""
    return _trace_context.get()


def create_langfuse_handler(
    context: Optional[Dict[str, Any]] = None,
) -> Optional["LangfuseCallbackHandler"]:
    """
        创建 Langfuse CallbackHandler；未启用或未安装时返回 None。

        Args:
            context: 可选上下文，可含 trace_id

        Returns:
            LangfuseCallbackHandler 或 None
    """
    if not settings.LANGFUSE_ENABLED:
        logger.debug("[Langfuse] CallbackHandler: Langfuse未启用")
        return None

    LangfuseCls, CallbackHandlerCls = _import_langfuse()
    if CallbackHandlerCls is None:
        return None

    public_key = settings.LANGFUSE_PUBLIC_KEY
    secret_key = settings.LANGFUSE_SECRET_KEY
    if not public_key or not secret_key:
        logger.warning(
            "[Langfuse] CallbackHandler: 配置不完整，缺少PUBLIC_KEY或SECRET_KEY。"
        )
        return None

    _get_langfuse_client()

    trace_id = None
    if context and isinstance(context, dict) and context.get("trace_id"):
        trace_id = context.get("trace_id")
    else:
        trace_id = get_current_trace_id()

    trace_context = None
    if trace_id:
        trace_context = {"trace_id": normalize_langfuse_trace_id(trace_id)}

    try:
        handler = CallbackHandlerCls(
            public_key=public_key,
            update_trace=True,
            trace_context=trace_context,
        )
        logger.debug(
            f"[Langfuse] CallbackHandler创建成功: trace_context={trace_context}"
        )
        return handler
    except Exception as e:
        logger.error(f"[Langfuse] CallbackHandler创建失败: {e}", exc_info=True)
        return None


def record_observation_span(
    name: str,
    *,
    input_data: Optional[Any] = None,
    output_data: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None,
    level: Optional[str] = None,
) -> None:
    """
        记录一次手工观测 span（用于非 LangChain 调用链路的指标，如知识库召回命中率）。

        ⚠️ 观测是旁路：未启用/未安装/任何异常都只打日志，**绝不向调用方抛异常**，
        以免可观测性故障影响评分主链路。

        Args:
            name: span 名称
            input_data: 输入（可选）
            output_data: 输出/指标（可选）
            metadata: 元数据（可选）
            trace_id: 归属 trace（可选；传入则并入同一 trace）
            level: 级别（DEBUG/DEFAULT/WARNING/ERROR，可选）
    """
    if not is_langfuse_available():
        logger.debug("[Langfuse] 观测 span 跳过（Langfuse 不可用）: name=%s", name)
        return

    client = get_langfuse_client()
    if client is None:
        return

    trace_context = None
    if trace_id:
        try:
            trace_context = {"trace_id": normalize_langfuse_trace_id(str(trace_id))}
        except Exception:
            trace_context = None

    kwargs: Dict[str, Any] = {
        "name": name,
        "input": input_data,
        "metadata": metadata or {},
    }
    if trace_context:
        kwargs["trace_context"] = trace_context
    if level:
        kwargs["level"] = level

    try:
        with client.start_as_current_span(**kwargs) as span:
            if output_data is not None:
                span.update(output=output_data)
    except Exception as e:
        logger.warning(f"[Langfuse] 观测 span 记录失败（已降级忽略）: name={name}, err={e}")


def normalize_langfuse_trace_id(trace_id: str) -> str:
    """
        将 trace_id 转为 Langfuse 要求的 32 位小写十六进制。

        Args:
            trace_id: 原始 trace_id

        Returns:
            规范化后的 trace_id
    """
    normalized = trace_id.replace("-", "").lower()
    try:
        int(normalized, 16)
    except ValueError:
        logger.warning(f"trace_id 不是有效的十六进制字符串: {trace_id}")
        return trace_id
    if len(normalized) != 32:
        logger.warning(
            f"trace_id 长度不是 32 位: {trace_id} "
            f"(转换后: {normalized}, 长度: {len(normalized)})"
        )
    return normalized


def _get_langfuse_client() -> Optional["Langfuse"]:
    """
        获取或创建 Langfuse 客户端（单例）。

        Returns:
            Langfuse 客户端；未启用/未安装/配置不全时返回 None
    """
    global _langfuse_client

    if not settings.LANGFUSE_ENABLED:
        logger.debug("Langfuse未启用（settings.LANGFUSE_ENABLED=False）")
        return None

    if _langfuse_client is not None:
        return _langfuse_client

    LangfuseCls, _ = _import_langfuse()
    if LangfuseCls is None:
        return None

    try:
        public_key = settings.LANGFUSE_PUBLIC_KEY
        secret_key = settings.LANGFUSE_SECRET_KEY
        base_url = settings.LANGFUSE_HOST or settings.LANGFUSE_BASE_URL

        if not public_key or not secret_key:
            logger.warning(
                "Langfuse配置不完整：缺少LANGFUSE_PUBLIC_KEY或LANGFUSE_SECRET_KEY"
            )
            return None

        if base_url is None:
            logger.warning(
                "LANGFUSE_HOST/LANGFUSE_BASE_URL 未设置，Langfuse 将使用默认 cloud host"
            )

        langfuse_kwargs: Dict[str, Any] = {
            "public_key": public_key,
            "secret_key": secret_key,
        }
        if base_url:
            langfuse_kwargs["base_url"] = base_url

        _langfuse_client = LangfuseCls(**langfuse_kwargs)
        logger.info(
            f"Langfuse客户端初始化成功: host={base_url or 'default'}, "
            f"public_key_prefix={public_key[:8] if public_key else 'None'}..."
        )
        return _langfuse_client
    except Exception as e:
        logger.error(f"Langfuse客户端初始化失败: {e}", exc_info=True)
        return None


def is_langfuse_available() -> bool:
    """检查 Langfuse 是否可用。"""
    if not settings.LANGFUSE_ENABLED:
        return False
    return get_langfuse_client() is not None


def get_langfuse_client() -> Optional["Langfuse"]:
    """获取 Langfuse 客户端实例（公共接口）。"""
    return _get_langfuse_client()
