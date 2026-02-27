"""
insert_rag_data_node 节点实现。

职责：
- 从 FlowState 中读取 create_rag_agent 节点输出的 cases；
- 将 cases 转换为 KnowledgeBaseRecordData 列表；
- 写入知识库表 gd25_knowledge_base。

代码风格参考 InsertDataToVectorDbNode，注释与异常信息均使用简体中文。
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.flows.nodes.base_function import BaseFunctionNode
from backend.domain.state import FlowState
from backend.infrastructure.database.connection import get_session_factory
from backend.infrastructure.database.models.knowledge_base import KnowledgeBaseRecord
from backend.infrastructure.database.repository.knowledge_base_repository import (
    KnowledgeBaseRepository,
)

logger = logging.getLogger(__name__)


class InvalidAgentOutputError(Exception):
    """Agent 输出格式不合法时抛出的业务异常。"""


class CaseFieldMissingError(Exception):
    """单个 case 关键字段缺失时抛出的业务异常。"""


class KnowledgeBaseRecordData:
    """
    知识库记录的领域模型（与 KnowledgeBaseRecord 字段一一对应的子集）。

    说明：
    - 不直接依赖 ORM 模型，便于测试与复用；
    - 真正写库时由仓储层负责转换为 ORM 实例。
    """

    def __init__(
        self,
        scene_summary: str,
        optimization_question: Optional[str],
        reply_example_or_rule: Optional[str],
        scene_category: Optional[str],
        input_tags: List[str],
        response_tags: List[str],
        raw_material_full_text: str,
        source_meta: Dict[str, Any],
    ) -> None:
        self.scene_summary = scene_summary
        self.optimization_question = optimization_question
        self.reply_example_or_rule = reply_example_or_rule
        self.scene_category = scene_category
        self.input_tags = input_tags
        self.response_tags = response_tags
        self.raw_material_full_text = raw_material_full_text
        self.source_meta = source_meta


def _normalize_optimization_question(value: Any) -> Optional[str]:
    """
    规范化 optimization_question 字段。

    规则：
    - 若为 list/tuple，则以 JSON 字符串形式存储，保持所有问句；
    - 若为字符串，去除首尾空白后直接使用；
    - 其它类型或空值，返回 None。
    """

    import json

    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _normalize_str(value: Any) -> Optional[str]:
    """
    将任意值转换为字符串（若为空字符串则返回 None）。
    """

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_tags(value: Any) -> List[str]:
    """
    规范化标签字段（input_tags / response_tags）。

    规则：
    - 若为 list/tuple：保留其中为非空字符串的元素；
    - 若为单个字符串：包装为长度为 1 的数组；
    - 其它情况：返回空列表。
    """

    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        result: List[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                result.append(text)
        return result
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def _parse_cases_from_cases(
    cases: Any,
    source_file: str,
    raw_material_full_text: str,
) -> List[KnowledgeBaseRecordData]:
    """
    将 Agent 输出解析为 KnowledgeBaseRecordData 列表。

    该函数的行为与 scripts.create_rag_data_v2.parser.parse_cases_from_agent_output 保持一致，
    但为避免跨层依赖，此处直接实现一份。
    """

    if not isinstance(cases, list):
        raise InvalidAgentOutputError(
            f"'cases' 字段类型错误，期望 list，实际为 {type(cases)!r}"
        )

    records: List[KnowledgeBaseRecordData] = []

    for idx, case in enumerate(cases):
        if not isinstance(case, dict):
            raise InvalidAgentOutputError(
                f"cases[{idx}] 类型错误，期望 dict，实际为 {type(case)!r}"
            )

        scene_summary = _normalize_str(case.get("scene_summary"))
        if not scene_summary:
            raise CaseFieldMissingError(
                f"cases[{idx}] 缺少必填字段 scene_summary 或内容为空"
            )

        optimization_question = _normalize_optimization_question(
            case.get("optimization_question")
        )
        reply_example_or_rule = _normalize_str(case.get("reply_example_or_rule"))
        scene_category = _normalize_str(case.get("scene_category"))
        input_tags = _normalize_tags(case.get("input_tags"))
        response_tags = _normalize_tags(case.get("response_tags"))

        record = KnowledgeBaseRecordData(
            scene_summary=scene_summary,
            optimization_question=optimization_question,
            reply_example_or_rule=reply_example_or_rule,
            scene_category=scene_category,
            input_tags=input_tags,
            response_tags=response_tags,
            raw_material_full_text=raw_material_full_text,
            source_meta={"source_file": source_file},
        )
        records.append(record)

    return records


class KnowledgeBaseWriter:
    """
    知识库写入封装类。

    使用方式：
        async with session_factory() as session:
            writer = KnowledgeBaseWriter(session)
            await writer.insert_records(records)
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        初始化写入器。

        Args:
            session: AsyncSession 实例。
        """

        self._session = session
        self._repo = KnowledgeBaseRepository(session)

    async def insert_records(
        self,
        records: Iterable[KnowledgeBaseRecordData],
    ) -> int:
        """
        批量插入知识库记录。

        Args:
            records: 待写入的领域数据对象列表。

        Returns:
            int: 实际成功插入的记录数量。
        """

        count = 0
        for data in records:
            await self._repo.create(
                scene_summary=data.scene_summary,
                optimization_question=data.optimization_question,
                reply_example_or_rule=data.reply_example_or_rule,
                scene_category=data.scene_category,
                input_tags=data.input_tags or None,
                response_tags=data.response_tags or None,
                raw_material_full_text=data.raw_material_full_text or None,
                raw_material_scene_summary=None,
                raw_material_question=None,
                raw_material_answer=None,
                raw_material_other=None,
                source_meta=data.source_meta,
                technical_tag_classification=None,
                business_tag_classification=None,
            )
            count += 1

        # 由调用方负责提交事务（commit），这里仅返回计数
        return count


class InsertRagDataNode(BaseFunctionNode):
    """
    insert_rag_data_node 节点。

    本节点在 create_rag_agent 节点之后执行，负责将 Agent 输出入库。
    """

    @classmethod
    def get_key(cls) -> str:
        """
        返回节点的唯一标识 key。

        注意：必须与 flow.yaml 中 function_key 保持一致：
            config/flows/create_rag_agent/flow.yaml: function_key: "insert_rag_data_func"
        """

        return "insert_rag_data_func"

    @staticmethod
    def _extract_cases_from_state(state: FlowState) -> Any:
        """
        从 FlowState 中提取 Agent 节点解析后的 cases 数组。

        约定：
        - create_rag_agent 节点会将解析后的 cases 放入 state["edges_var"]["cases"]；
          本节点直接从 edges_var 中读取该字段。
        """

        try:
            edges_var = state.get("edges_var", {}) or {}
            cases = edges_var.get("cases")
        except KeyError as exc:  # pragma: no cover - 极端异常路径
            raise InvalidAgentOutputError("在 FlowState 中未找到 edges_var 或 cases 字段") from exc

        if cases is None:
            raise InvalidAgentOutputError("edges_var 中未找到 'cases' 字段")

        return cases

    async def _insert_records(
        self,
        session: AsyncSession,
        records: list[KnowledgeBaseRecordData],
    ) -> int:
        """
        使用 KnowledgeBaseWriter 将记录写入数据库。
        """

        writer = KnowledgeBaseWriter(session)
        inserted = await writer.insert_records(records)
        await session.commit()
        return inserted

    async def execute(self, state: FlowState) -> FlowState:
        """
        执行 insert_rag_data_node 节点逻辑。

        步骤：
        1. 从 FlowState 中读取 create_rag_agent 节点输出；
        2. 将输出解析为 KnowledgeBaseRecordData 列表；
        3. 打开数据库会话并批量写入；
        4. 在 state 中记录本次入库结果摘要。
        """

        try:
            # 1. 提取 Agent 输出
            cases = self._extract_cases_from_state(state)
            prompt_vars: Dict[str, Any] = state.get("prompt_vars", {}) or {}
            # 按约定：scripts.create_rag_data_v2.state_builder 将 source_file 写入 prompt_vars
            source_file = str(prompt_vars.get("source_file", "unknown_source"))
            raw_material_full_text = str(
                prompt_vars.get("scene_record_content", "")
            )

            # 2. 解析 cases
            records = _parse_cases_from_cases(
                cases=cases,
                source_file=source_file,
                raw_material_full_text=raw_material_full_text,
            )
            if not records:
                logger.warning(
                    "insert_rag_data_node 未解析到任何 case，source_file=%s",
                    source_file,
                )

            # 3. 写入数据库
            session_factory = get_session_factory()
            async with session_factory() as session:
                inserted_count = 0
                if records:
                    inserted_count = await self._insert_records(session, records)

            # 4. 回写状态
            result_summary = {
                "inserted": inserted_count,
                "source_file": source_file,
            }
            # 避免污染原始 state，复制一份再写入
            new_state = state.copy()
            new_state["insert_rag_data_result"] = result_summary

            logger.info(
                "insert_rag_data_node 执行完成: source_file=%s, inserted=%d",
                source_file,
                inserted_count,
            )

            return new_state

        except (InvalidAgentOutputError, CaseFieldMissingError) as biz_err:
            # 业务异常：记录错误信息并继续向上抛出，中断流程
            logger.error("insert_rag_data_node 业务异常: %s", biz_err)
            raise
        except Exception as exc:  # pragma: no cover - 防御性兜底
            # 未预期异常：记录完整堆栈信息
            tb = traceback.format_exc()
            logger.error(
                "insert_rag_data_node 执行失败: %s\n%s",
                exc,
                tb,
            )
            raise


__all__ = [
    "InsertRagDataNode",
]

