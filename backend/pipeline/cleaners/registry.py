"""
清洗器注册与获取

根据 cleaner_key 返回对应清洗器实例。
设计文档：cursor_docs/020402-数据导入流程技术设计.md
"""
from typing import Dict, Type

from backend.pipeline.cleaners.base import BaseSheetCleaner
from backend.pipeline.cleaners.impl.lsk import LskCleaner

_CLEANER_REGISTRY: Dict[str, Type[BaseSheetCleaner]] = {
    "lsk": LskCleaner,
}


def get_cleaner_by_type(cleaner_type: str) -> BaseSheetCleaner:
    """
    根据类型获取清洗器实例

    Args:
        cleaner_type: 清洗器类型，如 "lsk"

    Returns:
        BaseSheetCleaner 实例

    Raises:
        ValueError: 未知的清洗器类型
    """
    if cleaner_type not in _CLEANER_REGISTRY:
        raise ValueError(f"未知的清洗器类型: {cleaner_type}，可选: {list(_CLEANER_REGISTRY.keys())}")
    return _CLEANER_REGISTRY[cleaner_type]()
