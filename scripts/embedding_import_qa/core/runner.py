"""
单条执行与批次逻辑：组装 state、RuntimeContext、Langfuse、graph.ainvoke。

设计文档：cursor_docs/012901-知识库Embedding导入脚本设计.md §4
"""
import asyncio
import logging
import secrets
from typing import Any, List, Tuple, TYPE_CHECKING

from backend.domain.tools.context import RuntimeContext
from backend.infrastructure.observability.langfuse_handler import create_langfuse_handler

from scripts.embedding_import_qa.core.config import (
    TOKEN_ID_PLACEHOLDER,
    SESSION_ID_PREFIX,
)
from scripts.embedding_import_qa.core.state_builder import build_initial_state_from_record

if TYPE_CHECKING:
    from backend.infrastructure.database.models.knowledge_base import (
        KnowledgeBaseRecord,
    )

logger = logging.getLogger(__name__)


def _generate_trace_id() -> str:
    """32 位小写十六进制，满足 Langfuse 要求。"""
    return secrets.token_hex(16)


async def run_one(
    record: "KnowledgeBaseRecord",
    graph: Any,
    *,
    dry_run: bool = False,
) -> bool:
    """
    对单条知识库记录：生成 trace_id、session_id，组装 state，RuntimeContext + Langfuse，
    graph.ainvoke；成功返回 True，否则 False 并打日志。dry_run 时仅组装 state、不 invoke。
    """
    record_id = getattr(record, "id", "?")
    trace_id = _generate_trace_id()
    session_id = f"{SESSION_ID_PREFIX}{record_id}"

    try:
        initial_state = build_initial_state_from_record(record, session_id, trace_id)
    except Exception as e:
        logger.warning(
            "组装 state 失败 record_id=%s trace_id=%s error=%s",
            record_id,
            trace_id,
            e,
        )
        return False

    if dry_run:
        logger.info(
            "[dry_run] record_id=%s trace_id=%s session_id=%s 已组装 state，跳过 invoke",
            record_id,
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
        logger.info("run_one 成功 record_id=%s trace_id=%s", record_id, trace_id)
        return True
    except Exception as e:
        logger.warning(
            "run_one 失败 record_id=%s trace_id=%s error=%s",
            record_id,
            trace_id,
            e,
            exc_info=True,
        )
        return False


async def run_batch_parallel(
    records: List["KnowledgeBaseRecord"],
    graph: Any,
    *,
    max_concurrent: int = 5,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """
    并行执行批次处理。使用 asyncio.Semaphore 控制并发数。
    """
    if not records:
        return (0, 0)

    semaphore = asyncio.Semaphore(max_concurrent)

    async def run_with_semaphore(r):
        async with semaphore:
            return await run_one(r, graph, dry_run=dry_run)

    tasks = [run_with_semaphore(r) for r in records]
    logger.info("创建 %d 个并行任务，最大并发数=%d", len(tasks), max_concurrent)
    results = await asyncio.gather(*tasks, return_exceptions=True)

    ok, fail = 0, 0
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                "任务执行异常 record_id=%s error=%s",
                getattr(records[i], "id", "?"),
                result,
                exc_info=result,
            )
            fail += 1
        elif result:
            ok += 1
        else:
            fail += 1
    return (ok, fail)
