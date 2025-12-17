"""
LLM 调用日志服务与回调
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.core.config import settings
from infrastructure.database.connection import get_async_session_factory
from infrastructure.database.repository.llm_call_log_repository import LlmCallLogRepository

logger = logging.getLogger(__name__)


@dataclass
class LlmLogContext:
    """LLM 调用上下文（用于链路追踪与审计）"""
    
    trace_id: Optional[str] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    agent_key: Optional[str] = None


def _truncate_text(text: Optional[str]) -> Optional[str]:
    """
    截断长文本，避免日志膨胀
    
    Args:
        text: 原始文本
        
    Returns:
        截断后的文本
    """
    if text is None:
        return None
    max_len = max(settings.LLM_LOG_MAX_TEXT_LENGTH, 0)
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"...[truncated {len(text) - max_len} chars]"


def _estimate_tokens(text: Optional[str]) -> Optional[int]:
    """
    粗略估算 token 数量（以 4 字符 ≈ 1 token 粗估）
    """
    if not text:
        return None
    return max(len(text) // 4, 1)


async def _start_log(
    call_id: str,
    model: str,
    temperature: Optional[float],
    top_p: Optional[float],
    max_tokens: Optional[int],
    prompt_snapshot: Optional[str],
    context: Optional[LlmLogContext],
    prompt_messages: Optional[List[Dict[str, Any]]] = None,
    started_at: Optional[datetime] = None,
) -> None:
    """
    创建调用日志记录
    """
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = LlmCallLogRepository(session)
        await repo.create_call_log(
            call_id=call_id,
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            prompt_snapshot=_truncate_text(prompt_snapshot),
            trace_id=context.trace_id if context else None,
            session_id=context.session_id if context else None,
            conversation_id=context.conversation_id if context else None,
            user_id=context.user_id if context else None,
            agent_key=context.agent_key if context else None,
            started_at=started_at,
        )
        if prompt_messages:
            await repo.save_messages(call_id, prompt_messages)
        await session.commit()


async def _finish_log(
    call_id: str,
    response_snapshot: Optional[str],
    latency_ms: Optional[int],
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    total_tokens: Optional[int],
    response_messages: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    完成调用日志记录
    """
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = LlmCallLogRepository(session)
        await repo.mark_success(
            call_id=call_id,
            response_snapshot=_truncate_text(response_snapshot),
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            finished_at=datetime.utcnow(),
        )
        if response_messages:
            await repo.save_messages(call_id, response_messages)
        await session.commit()


async def _fail_log(
    call_id: str,
    error_code: Optional[str],
    error_message: Optional[str],
    latency_ms: Optional[int],
) -> None:
    """
    记录调用失败
    """
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = LlmCallLogRepository(session)
        await repo.mark_failure(
            call_id=call_id,
            error_code=error_code,
            error_message=_truncate_text(error_message),
            latency_ms=latency_ms,
            finished_at=datetime.utcnow(),
        )
        await session.commit()


def _run_in_background(coro) -> None:
    """
    在后台运行协程，失败时仅记录日志，不影响主流程
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        asyncio.run(coro)
    except Exception as exc:  # pragma: no cover - 容错兜底
        logger.warning(f"启动后台日志任务失败: {exc}")


def _convert_prompt(prompts: List[Any]) -> str:
    """
    将提示词列表转换为字符串
    """
    try:
        prompt_texts = []
        for prompt in prompts:
            if isinstance(prompt, list):
                # Chat 模式：BaseMessage 列表
                prompt_texts.append("\n".join([getattr(msg, "content", str(msg)) for msg in prompt]))
            else:
                prompt_texts.append(str(prompt))
        return "\n\n".join(prompt_texts)
    except Exception:
        return str(prompts)


class LlmLogCallbackHandler(BaseCallbackHandler):
    """LLM 日志回调处理器"""
    
    def __init__(
        self,
        context: Optional[LlmLogContext],
        model: str,
        temperature: Optional[float],
        top_p: Optional[float],
        max_tokens: Optional[int],
        log_enabled: bool = True,
    ):
        self.context = context
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.log_enabled = log_enabled
        self._call_info: Dict[str, Dict[str, Any]] = {}
    
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[Any], **kwargs: Any) -> None:
        """LLM 开始回调"""
        if not self.log_enabled:
            return
        run_id = str(kwargs.get("run_id") or uuid.uuid4())
        call_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        started_ts = time.monotonic()
        prompt_snapshot = _convert_prompt(prompts)
        
        self._call_info[run_id] = {
            "call_id": call_id,
            "started_at": started_at,
            "started_ts": started_ts,
        }
        
        prompt_messages = []
        try:
            if isinstance(prompts, list):
                for p in prompts:
                    if isinstance(p, list):
                        for msg in p:
                            content = getattr(msg, "content", str(msg))
                            role = getattr(msg, "type", getattr(msg, "role", "unknown"))
                            prompt_messages.append({
                                "role": role,
                                "content": content,
                                "token_estimate": _estimate_tokens(content),
                            })
                    else:
                        content = getattr(p, "content", str(p))
                        prompt_messages.append({
                            "role": getattr(p, "type", getattr(p, "role", "unknown")),
                            "content": content,
                            "token_estimate": _estimate_tokens(content),
                        })
        except Exception:
            logger.debug("提示词转存失败，继续执行", exc_info=True)
        
        _run_in_background(_start_log(
            call_id=call_id,
            model=self.model,
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            prompt_snapshot=prompt_snapshot,
            context=self.context,
            prompt_messages=prompt_messages if settings.LLM_LOG_ENABLE else None,
            started_at=started_at,
        ))
    
    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """LLM 成功结束回调"""
        if not self.log_enabled:
            return
        run_id = str(kwargs.get("run_id") or "")
        info = self._call_info.pop(run_id, None)
        if not info:
            return
        
        call_id = info["call_id"]
        started_ts = info.get("started_ts")
        latency_ms = None
        if started_ts:
            latency_ms = int((time.monotonic() - started_ts) * 1000)
        
        # 提取响应内容
        response_text = None
        response_messages: List[Dict[str, Any]] = []
        try:
            generations = response.generations if hasattr(response, "generations") else []
            if generations and generations[0]:
                content = getattr(generations[0][0].message, "content", None)
                if content:
                    response_text = str(content)
                    response_messages.append({
                        "role": getattr(generations[0][0].message, "type", "assistant"),
                        "content": response_text,
                        "token_estimate": _estimate_tokens(response_text),
                    })
        except Exception:
            logger.debug("响应内容解析失败", exc_info=True)
        
        # Token 统计
        prompt_tokens = None
        completion_tokens = None
        total_tokens = None
        try:
            llm_output = getattr(response, "llm_output", {}) or {}
            usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens") or usage.get("total")
        except Exception:
            logger.debug("token 统计解析失败", exc_info=True)
        
        _run_in_background(_finish_log(
            call_id=call_id,
            response_snapshot=response_text,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            response_messages=response_messages if settings.LLM_LOG_ENABLE else None,
        ))
    
    def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        """LLM 失败回调"""
        if not self.log_enabled:
            return
        run_id = str(kwargs.get("run_id") or "")
        info = self._call_info.pop(run_id, None)
        if not info:
            return
        call_id = info["call_id"]
        started_ts = info.get("started_ts")
        latency_ms = None
        if started_ts:
            latency_ms = int((time.monotonic() - started_ts) * 1000)
        
        _run_in_background(_fail_log(
            call_id=call_id,
            error_code=error.__class__.__name__,
            error_message=str(error),
            latency_ms=latency_ms,
        ))
