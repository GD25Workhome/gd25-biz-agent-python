"""
数据清洗（Step02 rewritten）服务

从 DataSetsItemsRecord 查询数据，构建 state，并发执行 rewritten_data_service_agent 流程。
支持批量创建 + 异步 Worker 轮询执行模式。
设计文档：cursor_docs/021001-Rewritten流程批量异步执行技术设计.md
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.state import FlowState
from backend.domain.tools.context import RuntimeContext
from backend.infrastructure.database.connection import get_session_factory
from backend.infrastructure.database.models.data_items_rewritten import (
    DataItemsRewrittenRecord,
)
from backend.infrastructure.database.models.data_sets_items import DataSetsItemsRecord
from backend.infrastructure.database.repository.data_items_rewritten_repository import (
    DataItemsRewrittenRepository,
    STATUS_FAILED,
    STATUS_INIT,
    STATUS_PROCESSING,
)
from backend.infrastructure.database.repository.data_sets_items_repository import (
    DataSetsItemsRepository,
)
from backend.infrastructure.observability.langfuse_handler import create_langfuse_handler

logger = logging.getLogger(__name__)

# 流程 key，与 config/flows/pipeline_step2/flow.yaml 的 name 一致
FLOW_KEY = "rewritten_data_service_agent"
# 最大并发数（后端常量，不开放给前端）
MAX_CONCURRENT = 4
# Worker 配置（设计文档 5.3.2.1）
POLL_INTERVAL_SECONDS = 2
BATCH_SIZE = 10
# 占位 token_id（无真实 Token 时使用）
TOKEN_ID_PLACEHOLDER = "rewritten_data_service"
SESSION_ID_PREFIX = "rewritten_"


@dataclass
class RewrittenExecuteStats:
    """执行统计（旧接口兼容）"""

    total: int
    success: int
    failed: int

    def to_dict(self) -> Dict[str, int]:
        return {"total": self.total, "success": self.success, "failed": self.failed}


@dataclass
class RewrittenBatchCreateResult:
    """批量创建改写任务结果"""

    batch_code: str
    total: int


def _safe_str(v: Any) -> str:
    """None 或空转为 ''，否则 str。"""
    if v is None:
        return ""
    s = str(v).strip()
    return s if s else ""


def _safe_list(v: Any) -> List[Any]:
    """None 转为 []，否则确保为 list。"""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return list(v)


def _format_history_messages(history_messages: Any) -> str:
    """将 history_messages 格式化为提示词可用的字符串。"""
    if history_messages is None:
        return ""
    if isinstance(history_messages, str):
        return history_messages.strip()
    if isinstance(history_messages, list):
        try:
            return json.dumps(history_messages, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(history_messages)
    return str(history_messages)


def build_state_from_record(
    record: DataSetsItemsRecord,
    dataset_id: str,
    session_id: str,
    trace_id: str,
    rewritten_record_id: Optional[str] = None,
) -> FlowState:
    """
    从 DataSetsItemsRecord 构建 FlowState。

    映射规则（设计文档 §4.3）：
    - q_context: 来自 metadata.content_info.user_info，若不存在则不填充
    - manual_ext: 来自 metadata.content_info.ext 与 metadata.content_info.user_info.response_tags
    - prompt_vars: rewritten_record_id（供 update_rewritten_data_func 按 id 更新）
    """
    meta = getattr(record, "metadata_", None) or {}
    content_info = meta.get("content_info") if isinstance(meta, dict) else {}

    # q_context：从 item.metadata.content_info.user_info 取值
    user_info = content_info.get("user_info") if isinstance(content_info, dict) else None
    q_context = ""
    if user_info is not None:
        if isinstance(user_info, dict):
            q_context = json.dumps(user_info, ensure_ascii=False, indent=2)
        else:
            q_context = _safe_str(user_info)

    # manual_ext：从 item.metadata.content_info.ext 与 item.metadata.content_info.user_info.response_tags
    ext_parts: List[str] = []
    ext_val = content_info.get("ext") if isinstance(content_info, dict) else None
    if ext_val is not None and _safe_str(ext_val):
        ext_parts.append(_safe_str(ext_val))
    response_tags = (
        user_info.get("response_tags") if isinstance(user_info, dict) else None
    )
    if response_tags is not None:
        if isinstance(response_tags, list):
            ext_parts.append(json.dumps(response_tags, ensure_ascii=False, indent=2))
        else:
            ext_parts.append(_safe_str(response_tags))
    manual_ext = "\n".join(ext_parts) if ext_parts else ""

    # input / output
    inp = getattr(record, "input", None) or {}
    outp = getattr(record, "output", None) or {}
    if not isinstance(inp, dict):
        inp = {}
    if not isinstance(outp, dict):
        outp = {}

    current_message = _safe_str(inp.get("current_msg") or inp.get("current_message"))
    history_messages = _format_history_messages(inp.get("history_messages"))
    response_message = _safe_str(outp.get("response_message"))
    response_rule = _safe_str(outp.get("response_rule"))

    prompt_vars: Dict[str, Any] = {
        "q_context": q_context,
        "current_message": current_message,
        "history_messages": history_messages,
        "manual_ext": manual_ext,
        "response_message": response_message,
        "response_rule": response_rule,
        "rewritten_record_id": rewritten_record_id,
    }

    # 构建顶层 current_message，供 Agent 节点判断「有消息需处理」并触发 LLM 调用
    # 若 record 有当前发言则使用之，否则用占位符（实际上下文在 prompt_vars 中，由 system prompt 注入）
    current_msg_content = current_message if current_message else "请根据上下文信息进行改写"
    state_current_message = HumanMessage(content=current_msg_content)

    return {
        "session_id": session_id,
        "token_id": TOKEN_ID_PLACEHOLDER,
        "trace_id": trace_id,
        "prompt_vars": prompt_vars,
        "current_message": state_current_message,
        "history_messages": [],
        "flow_msgs": [],
    }


async def _run_one(
    record: DataSetsItemsRecord,
    dataset_id: str,
    graph: Any,
    rewritten_record_id: Optional[str] = None,
) -> bool:
    """对单条 record 执行 flow，成功返回 True。"""
    record_id = getattr(record, "id", "?")
    trace_id = secrets.token_hex(16)
    session_id = f"{SESSION_ID_PREFIX}{record_id}"

    try:
        initial_state = build_state_from_record(
            record, dataset_id, session_id, trace_id,
            rewritten_record_id=rewritten_record_id,
        )
    except Exception as e:
        logger.warning(
            "组装 state 失败 record_id=%s trace_id=%s error=%s",
            record_id,
            trace_id,
            e,
        )
        return False

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


async def _run_batch_parallel(
    records: List[DataSetsItemsRecord],
    dataset_id: str,
    graph: Any,
) -> Tuple[int, int]:
    """并行执行批次，返回 (success, failed)。"""
    if not records:
        return (0, 0)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def run_with_semaphore(r: DataSetsItemsRecord) -> bool:
        async with semaphore:
            return await _run_one(r, dataset_id, graph)

    tasks = [run_with_semaphore(r) for r in records]
    logger.info("创建 %d 个并行任务，最大并发数=%d", len(tasks), MAX_CONCURRENT)
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


async def create_rewritten_batch(
    dataset_id: str,
    session: AsyncSession,
    *,
    item_ids: Optional[List[str]] = None,
    query_params: Optional[Dict[str, Any]] = None,
) -> RewrittenBatchCreateResult:
    """
    批量创建改写任务。查询待处理记录，在 pipeline_data_items_rewritten 中创建 init 记录，
    立即返回 batch_code 和 total，由后台 Worker 异步执行。
    """
    ds_repo = DataSetsItemsRepository(session)
    records: List[DataSetsItemsRecord] = []

    if item_ids:
        records = await ds_repo.get_by_ids(dataset_id, item_ids)
    elif query_params is not None:
        # query_params 为 {} 时表示无筛选条件，命中该 dataset 下全部记录
        records = await ds_repo.get_list_by_conditions(
            dataset_id=dataset_id,
            status=query_params.get("status"),
            unique_key=query_params.get("unique_key"),
            source=query_params.get("source"),
            keyword=query_params.get("keyword"),
        )
    else:
        return RewrittenBatchCreateResult(batch_code="", total=0)

    if not records:
        return RewrittenBatchCreateResult(batch_code="", total=0)

    batch_code = datetime.now().strftime("%Y%m%d%H%M%S")
    rewritten_repo = DataItemsRewrittenRepository(session)
    created = await rewritten_repo.create_init_batch(
        records=records,
        batch_code=batch_code,
        dataset_id=dataset_id,
    )
    return RewrittenBatchCreateResult(batch_code=batch_code, total=created)


async def run_one_rewritten(rec: DataItemsRewrittenRecord) -> None:
    """
    对单条 DataItemsRewrittenRecord 执行改写流程。
    根据 source_dataset_id、source_item_id 查 DataSetsItemsRecord，调用 _run_one。
    查不到则更新为 failed。内部使用独立 session。
    """
    from backend.domain.flows.manager import FlowManager

    session_factory = get_session_factory()
    dataset_id = rec.source_dataset_id or ""
    item_id = rec.source_item_id or ""

    if not dataset_id or not item_id:
        async with session_factory() as session:
            repo = DataItemsRewrittenRepository(session)
            await repo.update_status(
                rec.id,
                STATUS_FAILED,
                execution_metadata={
                    "failure_reason": "source_dataset_id 或 source_item_id 为空",
                    "stage": "run_one_rewritten",
                },
            )
            await session.commit()
        return

    async with session_factory() as session:
        ds_repo = DataSetsItemsRepository(session)
        item_record = await ds_repo.get_by_dataset_and_item_id(
            dataset_id=dataset_id,
            item_id=item_id,
        )
        if not item_record:
            rewritten_repo = DataItemsRewrittenRepository(session)
            await rewritten_repo.update_status(
                rec.id,
                STATUS_FAILED,
                execution_metadata={
                    "failure_reason": "来源 data_sets_items 记录不存在",
                    "stage": "run_one_rewritten",
                },
            )
            await session.commit()
            return

    graph = FlowManager.get_flow(FLOW_KEY)
    await _run_one(
        item_record, dataset_id, graph, rewritten_record_id=rec.id
    )


async def _mark_failed(record_id: str, reason: str) -> None:
    """将 record 标记为 failed。"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = DataItemsRewrittenRepository(session)
        await repo.update_status(
            record_id,
            STATUS_FAILED,
            execution_metadata={"failure_reason": reason, "stage": "run_one"},
        )
        await session.commit()


async def rewritten_worker_loop() -> None:
    """
    后台 Worker 主循环。子方案 B（并行）：拉取 init → 更新 processing → 并行执行。
    由 main.py lifespan 启动。
    """
    session_factory = get_session_factory()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def run_with_semaphore(
        rec: DataItemsRewrittenRecord,
    ) -> Tuple[str, bool, Optional[Exception]]:
        async with semaphore:
            try:
                await run_one_rewritten(rec)
                return (rec.id, True, None)
            except Exception as e:
                return (rec.id, False, e)

    while True:
        try:
            async with session_factory() as session:
                repo = DataItemsRewrittenRepository(session)
                records = await repo.get_init_records(limit=BATCH_SIZE)
                if not records:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                updated_records: List[DataItemsRewrittenRecord] = []
                for rec in records:
                    try:
                        ok = await repo.update_status(rec.id, STATUS_PROCESSING)
                        if ok:
                            updated_records.append(rec)
                    except Exception as e:
                        await session.rollback()
                        logger.exception(
                            "更新 status=processing 失败 record_id=%s", rec.id
                        )
                        updated_records = []
                        break
                await session.commit()
                records = updated_records

                if not records:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                results = await asyncio.gather(
                    *[run_with_semaphore(rec) for rec in records],
                    return_exceptions=True,
                )

                for i, res in enumerate(results):
                    if i >= len(records):
                        break
                    rec = records[i]
                    if isinstance(res, Exception):
                        await _mark_failed(rec.id, str(res))
                    elif isinstance(res, tuple) and not res[1] and res[2]:
                        await _mark_failed(rec.id, str(res[2]))

        except Exception as e:
            logger.exception("rewritten_worker_loop 异常: %s", e)

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
