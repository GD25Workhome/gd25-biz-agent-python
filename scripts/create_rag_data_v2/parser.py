"""
Agent 输出解析模块。

负责将 create_rag_agent 节点返回的 JSON 结果转换为领域数据对象，
并补充原始 Markdown 相关的信息（raw_material_full_text、source_meta）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .file_loader import MarkdownSource


class InvalidAgentOutputError(Exception):
    """Agent 输出格式不合法时抛出的业务异常。"""


class CaseFieldMissingError(Exception):
    """单个 case 关键字段缺失时抛出的业务异常。"""


@dataclass
class KnowledgeBaseRecordData:
    """
    知识库记录的领域模型（与 KnowledgeBaseRecord 字段一一对应的子集）。

    注意：
    - 此数据类不直接依赖数据库模型，便于单元测试；
    - 真正写库时再由 repository 模块负责转换为 ORM 实例。
    """

    scene_summary: str
    optimization_question: Optional[str]
    reply_example_or_rule: Optional[str]
    scene_category: Optional[str]
    input_tags: List[str]
    response_tags: List[str]
    raw_material_full_text: str
    source_meta: Dict[str, Any]


def _normalize_optimization_question(value: Any) -> Optional[str]:
    """
    规范化 optimization_question 字段。

    规则：
        - 若为 list/tuple，则以 JSON 字符串形式存储，保持所有问句；
        - 若为字符串，去除首尾空白后直接使用；
        - 其它类型或空值，返回 None。
    """

    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        # 使用 ensure_ascii=False 保留中文
        return json.dumps(list(value), ensure_ascii=False)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    # 其他类型一律视为无效
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


def parse_cases_from_agent_output(
    agent_output: Dict[str, Any],
    markdown: MarkdownSource,
) -> List[KnowledgeBaseRecordData]:
    """
    将 Agent 输出解析为 KnowledgeBaseRecordData 列表。

    Args:
        agent_output: Agent 节点返回的 JSON 对象，必须包含 "cases" 字段。
        markdown:     当前处理的 MarkdownSource，用于填充原文与 source_meta。

    Returns:
        List[KnowledgeBaseRecordData]: 解析得到的知识库记录列表。

    Raises:
        InvalidAgentOutputError: 当根对象缺少 cases 或类型错误时抛出。
        CaseFieldMissingError:   当单个 case 缺少关键字段（如 scene_summary）时抛出。
    """

    if not isinstance(agent_output, dict):
        raise InvalidAgentOutputError(f"Agent 输出根对象类型错误，期望 dict，实际为 {type(agent_output)!r}")

    if "cases" not in agent_output:
        raise InvalidAgentOutputError("Agent 输出中缺少 'cases' 字段")

    cases = agent_output.get("cases")
    if not isinstance(cases, list):
        raise InvalidAgentOutputError(f"'cases' 字段类型错误，期望 list，实际为 {type(cases)!r}")

    records: List[KnowledgeBaseRecordData] = []

    for idx, case in enumerate(cases):
        if not isinstance(case, dict):
            raise InvalidAgentOutputError(
                f"cases[{idx}] 类型错误，期望 dict，实际为 {type(case)!r}"
            )

        scene_summary = _normalize_str(case.get("scene_summary"))
        if not scene_summary:
            raise CaseFieldMissingError(f"cases[{idx}] 缺少必填字段 scene_summary 或内容为空")

        optimization_question = _normalize_optimization_question(case.get("optimization_question"))
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
            raw_material_full_text=markdown.raw_markdown,
            source_meta={"source_file": markdown.source_path},
        )
        records.append(record)

    return records


__all__ = [
    "KnowledgeBaseRecordData",
    "InvalidAgentOutputError",
    "CaseFieldMissingError",
    "parse_cases_from_agent_output",
]

