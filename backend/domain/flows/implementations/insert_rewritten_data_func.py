"""
insert_rewritten_data_node 节点实现。

职责：
- 从 FlowState 中读取 rewritten_agent_node 节点输出的 JSON 解析结果；
- 将数据映射到 DataItemsRewrittenRecord 并写入 pipeline_data_items_rewritten 表；
- 支持「拿不到数据」场景，写入 status=failed 记录。

设计文档：cursor_docs/020901-insert_rewritten_data_func技术设计.md
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.flows.nodes.base_function import BaseFunctionNode
from backend.domain.state import FlowState
from backend.infrastructure.database.connection import get_session_factory
from backend.infrastructure.database.repository.data_items_rewritten_repository import (
    DataItemsRewrittenRepository,
)

logger = logging.getLogger(__name__)

# Agent 输出字段（中文）到 ORM 字段的映射
EDGES_VAR_TO_ORM: Dict[str, str] = {
    "场景描述": "scenario_description",
    "患者提问": "rewritten_question",
    "回复案例": "rewritten_answer",
    "回复规则": "rewritten_rule",
    "场景": "scenario_type",
    "子场景": "sub_scenario_type",
    "改写依据": "rewrite_basis",
    "场景置信度": "scenario_confidence",
    "标签": "ai_tags",
}

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


def _normalize_str(value: Any) -> Optional[str]:
    """将任意值转换为字符串（若为空字符串则返回 None）。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_scenario_confidence(value: Any) -> Optional[Decimal]:
    """
    规范化场景置信度，0–1 范围，无效则 None。
    """
    if value is None:
        return None
    try:
        v = float(value)
        if 0 <= v <= 1:
            return Decimal(str(v))
    except (ValueError, TypeError):
        pass
    return None


def _normalize_ai_tags(value: Any) -> Optional[Dict[str, Any]]:
    """
    规范化标签字段。若为 dict 则原样返回，否则返回 None。
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return None


def _extract_source_ids(state: FlowState) -> tuple[Optional[str], Optional[str]]:
    """
    从 state 中提取 source_dataset_id、source_item_id。
    优先从 persistence_edges_var 读取，其次 prompt_vars。
    """
    persistence = state.get("persistence_edges_var") or {}
    prompt_vars = state.get("prompt_vars") or {}
    merged = {**persistence, **prompt_vars}
    return (
        _normalize_str(merged.get("source_dataset_id")),
        _normalize_str(merged.get("source_item_id")),
    )


def _has_valid_rewritten_data(edges_var: Dict[str, Any]) -> bool:
    """
    判断 edges_var 是否包含有效改写数据。
    至少需要有一个业务字段非空。
    """
    if not edges_var or not isinstance(edges_var, dict):
        return False
    for cn_key in ["场景描述", "患者提问", "回复案例", "回复规则", "场景", "子场景"]:
        v = edges_var.get(cn_key)
        if v is not None and str(v).strip():
            return True
    return False


def _build_create_kwargs(
    state: FlowState,
    edges_var: Dict[str, Any],
    status: str,
    execution_metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    构建 DataItemsRewrittenRepository.create 的参数字典。
    """
    source_dataset_id, source_item_id = _extract_source_ids(state)
    trace_id = _normalize_str(state.get("trace_id"))

    kwargs: Dict[str, Any] = {
        "source_dataset_id": source_dataset_id,
        "source_item_id": source_item_id,
        "trace_id": trace_id,
        "status": status,
        "execution_metadata": execution_metadata,
    }

    if status == STATUS_SUCCESS and edges_var:
        for cn_key, orm_key in EDGES_VAR_TO_ORM.items():
            raw = edges_var.get(cn_key)
            if raw is None:
                continue
            if orm_key == "scenario_confidence":
                kwargs[orm_key] = _normalize_scenario_confidence(raw)
            elif orm_key == "ai_tags":
                kwargs[orm_key] = _normalize_ai_tags(raw)
            else:
                kwargs[orm_key] = _normalize_str(raw)

    return kwargs


class InsertRewrittenDataNode(BaseFunctionNode):
    """
    insert_rewritten_data_node 节点。

    本节点在 rewritten_agent_node 之后执行，负责将 Agent 输出入库。
    """

    @classmethod
    def get_key(cls) -> str:
        """
        返回节点的唯一标识 key。

        注意：必须与 flow.yaml 中 function_key 保持一致：
            config/flows/pipeline_step2/flow.yaml: function_key: "insert_rewritten_data_func"
        """
        return "insert_rewritten_data_func"

    async def execute(self, state: FlowState) -> FlowState:
        """
        执行 insert_rewritten_data_node 节点逻辑。

        步骤：
        1. 从 state 提取 trace_id、source_dataset_id、source_item_id；
        2. 从 state.edges_var 提取改写结果；
        3. 若无有效数据，写入 status=failed 记录；
        4. 若有有效数据，映射并写入 status=success 记录；
        5. 将入库结果摘要写入 state。
        """
        edges_var: Dict[str, Any] = state.get("edges_var") or {}

        if not isinstance(edges_var, dict):
            edges_var = {}

        has_data = _has_valid_rewritten_data(edges_var)

        if has_data:
            status = STATUS_SUCCESS
            execution_metadata = None
        else:
            status = STATUS_FAILED
            execution_metadata = {
                "failure_reason": "edges_var 中无有效改写结果",
                "stage": "extract_edges_var",
            }
            if not state.get("trace_id"):
                execution_metadata["trace_id_missing"] = True

        kwargs = _build_create_kwargs(
            state=state,
            edges_var=edges_var if has_data else {},
            status=status,
            execution_metadata=execution_metadata,
        )

        session_factory = get_session_factory()
        async with session_factory() as session:
            repo = DataItemsRewrittenRepository(session)
            record = await repo.create(**kwargs)
            await session.commit()
            record_id = record.id

        result_summary = {
            "record_id": record_id,
            "status": status,
            "inserted": 1,
        }
        new_state = state.copy()
        if "edges_var" not in new_state:
            new_state["edges_var"] = {}
        new_state["edges_var"]["insert_rewritten_data_result"] = result_summary

        logger.info(
            "insert_rewritten_data_node 执行完成: record_id=%s, status=%s",
            record_id,
            status,
        )

        return new_state


__all__ = [
    "InsertRewrittenDataNode",
]
