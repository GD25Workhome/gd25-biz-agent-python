"""
数据导入流程单元测试

运行命令：pytest cursor_test/pipeline/test_pipeline_import.py -v

设计文档：cursor_docs/020402-数据导入流程技术设计.md
"""
import pytest
import pandas as pd

from backend.pipeline.cleaners.canonical import (
    CanonicalItem,
    DatasetItemDto,
    canonical_to_dataset_item,
)
from backend.pipeline.cleaners.registry import get_cleaner_by_type
from backend.pipeline.cleaners.impl.lsk import LskCleaner


# ---------- canonical_to_dataset_item ----------


def test_canonical_to_dataset_item_minimal():
    """最小化 CanonicalItem 转换"""
    item = CanonicalItem()
    dto = canonical_to_dataset_item(item)
    assert isinstance(dto, DatasetItemDto)
    assert dto.input == {"current_msg": "", "history_messages": []}
    assert dto.output == {"response_message": "", "flow_msgs": []}
    assert dto.metadata == {}


def test_canonical_to_dataset_item_full():
    """完整 CanonicalItem 转换"""
    item = CanonicalItem(
        current_msg="用户提问",
        history_messages=[{"type": "human", "content": "历史"}],
        response_message="回复内容",
        message_id="msg-001",
        patient_id="p-001",
        doctor_id="d-001",
        context={"age": 30, "disease": "高血压"},
        ext="扩展",
    )
    dto = canonical_to_dataset_item(item)
    assert dto.input["current_msg"] == "用户提问"
    assert len(dto.input["history_messages"]) == 1
    assert dto.output["response_message"] == "回复内容"
    assert dto.metadata["query_message_id"] == "msg-001"
    assert "content_info" in dto.metadata
    assert dto.metadata["content_info"]["user_info"] == {"age": 30, "disease": "高血压"}
    assert dto.metadata["content_info"]["patient_info"] == {"patient_id": "p-001"}
    assert dto.metadata["content_info"]["doctor_info"] == {"doctor_id": "d-001"}
    assert dto.metadata["content_info"]["ext"] == "扩展"


# ---------- get_cleaner_by_type ----------


def test_get_cleaner_by_type_lsk():
    """获取 LSK 清洗器"""
    cleaner = get_cleaner_by_type("lsk")
    assert isinstance(cleaner, LskCleaner)


def test_get_cleaner_by_type_unknown():
    """未知清洗器类型应抛出 ValueError"""
    with pytest.raises(ValueError, match="未知的清洗器类型"):
        get_cleaner_by_type("unknown_type")


# ---------- LskCleaner ----------


def test_lsk_cleaner_is_empty_row_missing_columns():
    """缺少必填列时为空行"""
    cleaner = LskCleaner()
    df = pd.DataFrame(columns=["其他列"])
    row = pd.Series({"其他列": "值"})
    assert cleaner.is_empty_row(row, df) is True


def test_lsk_cleaner_is_empty_row_empty_current():
    """新会话为空时为空行"""
    cleaner = LskCleaner()
    df = pd.DataFrame(columns=["新会话", "新会话响应"])
    row = pd.Series({"新会话": "", "新会话响应": "有回复"})
    assert cleaner.is_empty_row(row, df) is True


def test_lsk_cleaner_is_empty_row_valid():
    """新会话和新会话响应都有值时非空行"""
    cleaner = LskCleaner()
    df = pd.DataFrame(columns=["新会话", "新会话响应"])
    row = pd.Series({"新会话": "用户提问", "新会话响应": "回复"})
    assert cleaner.is_empty_row(row, df) is False


def test_lsk_cleaner_clean_simple():
    """LSK 清洗器简单行清洗"""
    cleaner = LskCleaner()
    df = pd.DataFrame(
        columns=["新会话", "新会话响应", "ids", "历史会话", "历史会话响应", "年龄"]
    )
    row = pd.Series(
        {
            "新会话": "血压多少？",
            "新会话响应": "content=您的血压正常",
            "ids": "messageId: msg-001",
            "历史会话": "",
            "历史会话响应": "",
            "年龄": 35,
        }
    )
    items = cleaner.clean(row, df)
    assert len(items) == 1
    item = items[0]
    assert item.current_msg == "血压多少？"
    assert item.response_message == "您的血压正常"
    assert item.message_id == "msg-001"
    assert item.context.get("age") == 35


def test_lsk_cleaner_clean_strip_content_prefix():
    """LSK 清洗器应去掉 content= 前缀"""
    cleaner = LskCleaner()
    df = pd.DataFrame(columns=["新会话", "新会话响应"])
    row = pd.Series(
        {
            "新会话": "问",
            "新会话响应": "content=实际回复内容",
        }
    )
    items = cleaner.clean(row, df)
    assert len(items) == 1
    assert items[0].response_message == "实际回复内容"
