"""
清洗器注册与获取

根据 cleaner_key 返回对应清洗器实例。
设计文档：cursor_docs/020402-数据导入流程技术设计.md
"""
from typing import Dict, Type

from backend.pipeline.cleaners.base import BaseSheetCleaner
from backend.pipeline.cleaners.impl.knowledge_base import KnowledgeBaseCleaner
from backend.pipeline.cleaners.impl.lsk import LskCleaner
from backend.pipeline.cleaners.impl.sh1128 import Sh1128Cleaner
from backend.pipeline.cleaners.impl.sh1128_history_qa import Sh1128HistoryQACleaner
from backend.pipeline.cleaners.impl.sh1128_multi import Sh1128MultiCleaner

_CLEANER_REGISTRY: Dict[str, Type[BaseSheetCleaner]] = {
    "knowledge_base": KnowledgeBaseCleaner,
    "lsk": LskCleaner,
    "sh1128": Sh1128Cleaner,
    "sh1128_multi": Sh1128MultiCleaner,
    "sh1128_history_qa": Sh1128HistoryQACleaner,
}


def get_cleaner_by_type(cleaner_type: str) -> BaseSheetCleaner:
    """
    根据类型获取清洗器实例

    Args:
        cleaner_type: 清洗器类型，如 "lsk", "sh1128", "sh1128_multi", "sh1128_history_qa"

    Returns:
        BaseSheetCleaner 实例

    Raises:
        ValueError: 未知的清洗器类型
    """
    if cleaner_type not in _CLEANER_REGISTRY:
        raise ValueError(f"未知的清洗器类型: {cleaner_type}，可选: {list(_CLEANER_REGISTRY.keys())}")
    return _CLEANER_REGISTRY[cleaner_type]()
