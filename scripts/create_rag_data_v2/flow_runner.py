"""
Flow 执行模块（create_rag_data_v2）。

职责：
- 负责将 MarkdownSource 转换为 FlowState；
- 调用 LangGraph 流程（create_rag_agent），并由流程内部节点负责入库；
- 对单条与批次执行提供统一封装。
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any, List, Tuple

from backend.domain.tools.context import RuntimeContext
from backend.infrastructure.observability.langfuse_handler import create_langfuse_handler

from .config import CreateRagDataConfig
from .file_loader import MarkdownSource
from .state_builder import (
    TOKEN_ID_PLACEHOLDER,
    SESSION_ID_PREFIX,
    build_initial_state_from_source,
)

logger = logging.getLogger(__name__)


def _generate_trace_id() -> str:
    """
    生成 32 位小写十六进制 trace_id，满足 Langfuse 要求。
    """

    return secrets.token_hex(16)


async def run_for_single_source(
    source: MarkdownSource,
    cfg: CreateRagDataConfig,
    graph: Any,
) -> bool:
    """
    对单个 MarkdownSource 执行 create_rag_agent 流程。

    Args:
        source: 当前处理的 Markdown 源。
        cfg:    运行配置。
        graph:  FlowManager.get_flow 返回的 graph 对象。

    Returns:
        bool: 成功返回 True，失败返回 False 并记录日志。
    """

    trace_id = _generate_trace_id()
    session_id = f"{SESSION_ID_PREFIX}{source.source_path}"

    try:
        initial_state = build_initial_state_from_source(
            source=source,
            session_id=session_id,
            trace_id=trace_id,
        )
    except Exception as e:
        logger.warning(
            "组装 FlowState 失败 source_file=%s trace_id=%s error=%s",
            source.source_path,
            trace_id,
            e,
        )
        return False

    if cfg.dry_run:
        logger.info(
            "[dry_run] source_file=%s trace_id=%s session_id=%s 已组装 state，跳过 invoke",
            source.source_path,
            trace_id,
            session_id,
        )
        return True

    langfuse_handler = create_langfuse_handler(context={"trace_id": trace_id})
    config: dict = {"configurable": {"thread_id": session_id}}
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]

    try:
        with RuntimeContext(
            token_id=TOKEN_ID_PLACEHOLDER,
            session_id=session_id,
            trace_id=trace_id,
        ):
            await graph.ainvoke(initial_state, config)
        logger.info(
            "run_for_single_source 成功 source_file=%s trace_id=%s",
            source.source_path,
            trace_id,
        )
        return True
    except Exception as e:
        logger.warning(
            "run_for_single_source 失败 source_file=%s trace_id=%s error=%s",
            source.source_path,
            trace_id,
            e,
            exc_info=True,
        )
        return False


async def run_batch(
    sources: List[MarkdownSource],
    cfg: CreateRagDataConfig,
    graph: Any,
) -> Tuple[int, int]:
    """
    并发执行 create_rag_agent 流程。

    Args:
        sources: MarkdownSource 列表。
        cfg:     运行配置（控制并发与 dry_run）。
        graph:   FlowManager.get_flow 返回的 graph 对象。

    Returns:
        (成功文件数, 失败文件数)。
    """

    semaphore = asyncio.Semaphore(cfg.max_concurrency)
    ok = 0
    fail = 0

    async def _run_one(source: MarkdownSource) -> None:
        nonlocal ok, fail
        async with semaphore:
            success = await run_for_single_source(source, cfg, graph)
            if success:
                ok += 1
            else:
                fail += 1

    tasks = [asyncio.create_task(_run_one(src)) for src in sources]
    if tasks:
        await asyncio.gather(*tasks)
    return ok, fail


__all__ = [
    "run_for_single_source",
    "run_batch",
]

