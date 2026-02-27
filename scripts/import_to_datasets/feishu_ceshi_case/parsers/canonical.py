"""
规范格式 CanonicalItem 与统一转换器

CanonicalItem：清洗后的统一中间格式，所有 Sheet 清洗器输出此结构。
canonical_to_dataset_item：将 CanonicalItem 转为 DataSetItemData，供 Langfuse 写入。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from scripts.import_to_datasets.feishu_ceshi_case.parsers.base import DataSetItemData


@dataclass
class CanonicalItem:
    """
    清洗后的规范格式，所有 Sheet 清洗器统一输出。

    与 Input/Output Schema 一一对应，转换层无需再解析。
    """

    current_msg: str = ""
    history_messages: List[Dict[str, str]] = field(default_factory=list)
    response_message: str = ""
    message_id: Optional[str] = None
    patient_id: Optional[str] = None
    doctor_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    ext: Optional[str] = None


def canonical_to_dataset_item(item: CanonicalItem) -> DataSetItemData:
    """
    将 CanonicalItem 转为 DataSetItemData，供 Langfuse create_dataset_item 使用。

    按方案 A（完全层级化）：context、ext 迁入 metadata，input/output 瘦身。

    Args:
        item: 清洗后的规范格式

    Returns:
        DataSetItemData：包含 input、expected_output、metadata
    """
    # Input：仅 current_msg、history_messages，context 迁入 metadata
    input_data: Dict[str, Any] = {
        "current_msg": item.current_msg or "",
        "history_messages": item.history_messages or [],
    }

    # Output：仅 response_message、flow_msgs，other_meta_data 迁入 metadata
    expected_output: Dict[str, Any] = {
        "response_message": item.response_message or "",
        "flow_msgs": [],
    }

    # Metadata：query_ 前缀扁平 key + content_info 层级（020308 二次改造）
    item_metadata: Dict[str, Any] = {}

    if item.message_id:
        item_metadata["query_message_id"] = item.message_id

    content_info: Dict[str, Any] = {}
    if item.context:
        content_info["user_info"] = item.context
    if item.patient_id:
        content_info["patient_info"] = {"patient_id": item.patient_id}
    if item.doctor_id:
        content_info["doctor_info"] = {"doctor_id": item.doctor_id}
    if item.ext:
        content_info["ext"] = item.ext
    if content_info:
        item_metadata["content_info"] = content_info

    return DataSetItemData(
        input=input_data,
        expected_output=expected_output,
        metadata=item_metadata,
    )
