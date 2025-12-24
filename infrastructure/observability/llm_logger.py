"""
LLM 调用日志服务与回调
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.core.config import settings
from infrastructure.database.connection import get_async_session_factory
from infrastructure.database.repository.llm_call_log_repository import LlmCallLogRepository

logger = logging.getLogger(__name__)

# 全局存储原始 API 响应（用于提取 reasoning_content）
# key: run_id, value: 原始 API 响应字典
_raw_api_responses: Dict[str, Dict[str, Any]] = {}


# 注意：HTTP 拦截器的实现需要能够关联 run_id 和原始响应
# 由于 LangChain 的 HTTP 客户端封装，直接拦截比较困难
# 当前实现通过其他方式（如检查 response_metadata）来提取 reasoning_content
# 如果这些方式都失败，可以考虑：
# 1. 使用 monkey patch 拦截 httpx 的响应
# 2. 修改 LangChain 的响应解析逻辑
# 3. 直接调用 API（不通过 LangChain）来获取完整的响应


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
        # 存储原始 API 响应（用于提取 reasoning_content）
        self._raw_responses: Dict[str, Dict[str, Any]] = {}
    
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[Any], **kwargs: Any) -> None:
        """LLM 开始回调"""
        # 控制台日志总是打印，数据库日志由 log_enabled 控制
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
        
        # 打印请求日志到控制台
        context_info = []
        if self.context:
            if self.context.session_id:
                context_info.append(f"session_id={self.context.session_id}")
            if self.context.user_id:
                context_info.append(f"user_id={self.context.user_id}")
            if self.context.agent_key:
                context_info.append(f"agent_key={self.context.agent_key}")
            if self.context.trace_id:
                context_info.append(f"trace_id={self.context.trace_id}")
        
        context_str = ", ".join(context_info) if context_info else "无上下文"
        
        logger.info(
            f"[LLM请求开始] call_id={call_id}, model={self.model}, "
            f"temperature={self.temperature}, top_p={self.top_p}, "
            f"max_tokens={self.max_tokens}, {context_str}"
        )
        
        logger.info(f"[LLM请求提示词] call_id={call_id}\n{prompt_snapshot}")
        # 打印提示词内容（截断过长内容以便阅读）
        # prompt_preview = prompt_snapshot[:500] + "..." if len(prompt_snapshot) > 500 else prompt_snapshot
        # logger.info(f"[LLM请求提示词] call_id={call_id}\n{prompt_preview}")
        
        # 只在启用数据库日志时写入数据库
        if self.log_enabled:
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
        # 控制台日志总是打印，数据库日志由 log_enabled 控制
        run_id = str(kwargs.get("run_id") or "")
        info = self._call_info.pop(run_id, None)
        if not info:
            return
        
        call_id = info["call_id"]
        started_ts = info.get("started_ts")
        latency_ms = None
        if started_ts:
            latency_ms = int((time.monotonic() - started_ts) * 1000)
        
        # 提取响应内容和思考过程
        response_text = None
        reasoning_content = None  # DeepSeek R1 的思考过程
        response_messages: List[Dict[str, Any]] = []
        try:
            generations = response.generations if hasattr(response, "generations") else []
            if generations and generations[0]:
                message = generations[0][0].message
                content = getattr(message, "content", None)
                
                # ===== 优先从 additional_kwargs 提取 reasoning_content =====
                # 这是 Monkey Patch 方案的核心：reasoning_content 会被放入 additional_kwargs
                if hasattr(message, "additional_kwargs"):
                    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
                    reasoning_content = additional_kwargs.get("reasoning_content")
                    if reasoning_content:
                        logger.debug(f"✅ 从 additional_kwargs 中提取到 reasoning_content，长度: {len(reasoning_content)} 字符")
                
                # 处理结构化内容（当使用 reasoning 参数时，content 可能是列表）
                if isinstance(content, list):
                    # 结构化响应：包含 reasoning 和 text 类型的块
                    reasoning_parts = []
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            block_type = block.get("type", "")
                            if block_type == "reasoning":
                                # 提取 reasoning 内容
                                summary = block.get("summary", [])
                                if summary:
                                    for summary_item in summary:
                                        if isinstance(summary_item, dict):
                                            reasoning_parts.append(summary_item.get("text", ""))
                                        else:
                                            reasoning_parts.append(str(summary_item))
                                # 如果没有 summary，尝试直接获取 text
                                if not reasoning_parts and "text" in block:
                                    reasoning_parts.append(str(block.get("text", "")))
                            elif block_type == "text":
                                text_parts.append(str(block.get("text", "")))
                        else:
                            # 如果不是字典，直接作为文本处理
                            text_parts.append(str(block))
                    
                    if reasoning_parts:
                        reasoning_content = "\n".join(reasoning_parts)
                    if text_parts:
                        response_text = "\n".join(text_parts)
                    elif not text_parts and not reasoning_parts:
                        # 如果都没有，将整个列表转为字符串
                        response_text = str(content)
                elif content:
                    # 字符串内容：可能包含 <think> 标签
                    content_str = str(content)
                    
                    # 尝试从 <think> 标签中提取思考过程
                    think_pattern = r'<think>(.*?)</think>'
                    think_matches = re.findall(think_pattern, content_str, re.DOTALL)
                    if think_matches:
                        reasoning_content = "\n".join(think_matches)
                        # 移除 <think> 标签，保留最终答案
                        response_text = re.sub(think_pattern, "", content_str, flags=re.DOTALL).strip()
                    else:
                        response_text = content_str
                
                # 如果还没有找到思考过程，尝试从 additional_kwargs 中查找其他可能的字段名（后备方案）
                if not reasoning_content and hasattr(message, "additional_kwargs"):
                    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
                    # 检查常见的思考过程字段名（作为后备方案）
                    reasoning_content = (
                        additional_kwargs.get("reasoning") or
                        additional_kwargs.get("thinking") or
                        additional_kwargs.get("thought") or
                        additional_kwargs.get("thinking_content")
                    )
                    # 如果没有找到，检查是否有其他可能的字段
                    if not reasoning_content:
                        for key in additional_kwargs.keys():
                            if "reason" in key.lower() or "think" in key.lower() or "thought" in key.lower():
                                reasoning_content = additional_kwargs.get(key)
                                break
                
                # 如果还没有找到思考过程，尝试从存储的原始响应中提取
                # 火山引擎 API 返回的 reasoning_content 在 message.reasoning_content 字段中
                # 但 LangChain 没有将其传递到 AIMessage 对象中
                # 我们需要通过其他方式获取，比如检查 response_metadata 或使用自定义 HTTP 客户端
                # 这里先尝试从 response_metadata 中查找
                if not reasoning_content and hasattr(message, "response_metadata"):
                    response_metadata = getattr(message, "response_metadata", {}) or {}
                    # 检查是否有原始响应数据
                    if isinstance(response_metadata, dict):
                        # 检查是否有 raw_response 或类似的字段
                        raw_response = response_metadata.get("raw_response") or response_metadata.get("response")
                        if isinstance(raw_response, dict):
                            # 检查 choices 中的 message.reasoning_content
                            choices = raw_response.get("choices", [])
                            if choices and len(choices) > 0:
                                choice = choices[0]
                                message_data = choice.get("message", {})
                                if isinstance(message_data, dict) and "reasoning_content" in message_data:
                                    reasoning_content = message_data.get("reasoning_content")
                                    logger.debug(f"从 response_metadata.raw_response 中提取到 reasoning_content")
                
                # 如果仍然没有找到，尝试从全局存储的原始响应中提取
                if not reasoning_content:
                    raw_response = _raw_api_responses.get(run_id)
                    if raw_response:
                        try:
                            choices = raw_response.get("choices", [])
                            if choices and len(choices) > 0:
                                choice = choices[0]
                                message_data = choice.get("message", {})
                                if isinstance(message_data, dict) and "reasoning_content" in message_data:
                                    reasoning_content = message_data.get("reasoning_content")
                                    logger.debug(f"从全局存储的原始响应中提取到 reasoning_content")
                                    # 清理已使用的响应
                                    _raw_api_responses.pop(run_id, None)
                        except Exception as e:
                            logger.debug(f"从原始响应提取 reasoning_content 失败: {str(e)}")
                
                # 记录响应消息
                if response_text:
                    response_messages.append({
                        "role": getattr(message, "type", "assistant"),
                        "content": response_text,
                        "token_estimate": _estimate_tokens(response_text),
                    })
                    if reasoning_content:
                        response_messages.append({
                            "role": "reasoning",
                            "content": reasoning_content,
                            "token_estimate": _estimate_tokens(reasoning_content),
                        })
        except Exception as e:
            logger.debug(f"响应内容解析失败: {str(e)}", exc_info=True)
        
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
        
        # 打印响应日志到控制台
        token_info = []
        if prompt_tokens is not None:
            token_info.append(f"prompt_tokens={prompt_tokens}")
        if completion_tokens is not None:
            token_info.append(f"completion_tokens={completion_tokens}")
        if total_tokens is not None:
            token_info.append(f"total_tokens={total_tokens}")
        
        token_str = ", ".join(token_info) if token_info else "token信息不可用"
        latency_str = f"{latency_ms}ms" if latency_ms is not None else "未知"
        
        logger.info(
            f"[LLM响应完成] call_id={call_id}, latency={latency_str}, {token_str}"
        )
        
        # 打印思考过程（如果存在）
        if reasoning_content:
            reasoning_str = str(reasoning_content)
            logger.info(f"[LLM思考过程] call_id={call_id}\n{reasoning_str}")
        else:
            logger.debug(f"[LLM思考过程] call_id={call_id}, 未检测到思考过程")
        
        # 打印最终响应内容
        if response_text:
            logger.info(f"[LLM响应内容] call_id={call_id}\n{response_text}")
        else:
            logger.warning(f"[LLM响应内容] call_id={call_id}, 响应内容为空")
        
        # 构建包含思考过程的响应快照（用于数据库日志）
        response_snapshot = response_text
        if reasoning_content and response_text:
            # 将思考过程和最终答案组合在一起
            response_snapshot = f"[思考过程]\n{reasoning_content}\n\n[最终答案]\n{response_text}"
        elif reasoning_content:
            # 只有思考过程，没有最终答案
            response_snapshot = f"[思考过程]\n{reasoning_content}"
        
        # 只在启用数据库日志时写入数据库
        if self.log_enabled:
            _run_in_background(_finish_log(
                call_id=call_id,
                response_snapshot=response_snapshot,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                response_messages=response_messages if settings.LLM_LOG_ENABLE else None,
            ))
    
    def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        """LLM 失败回调"""
        # 控制台日志总是打印，数据库日志由 log_enabled 控制
        run_id = str(kwargs.get("run_id") or "")
        info = self._call_info.pop(run_id, None)
        if not info:
            return
        call_id = info["call_id"]
        started_ts = info.get("started_ts")
        latency_ms = None
        if started_ts:
            latency_ms = int((time.monotonic() - started_ts) * 1000)
        
        # 打印错误日志到控制台
        latency_str = f"{latency_ms}ms" if latency_ms is not None else "未知"
        logger.error(
            f"[LLM调用失败] call_id={call_id}, error_code={error.__class__.__name__}, "
            f"error_message={str(error)}, latency={latency_str}",
            exc_info=True
        )
        
        # 只在启用数据库日志时写入数据库
        if self.log_enabled:
            _run_in_background(_fail_log(
                call_id=call_id,
                error_code=error.__class__.__name__,
                error_message=str(error),
                latency_ms=latency_ms,
            ))
