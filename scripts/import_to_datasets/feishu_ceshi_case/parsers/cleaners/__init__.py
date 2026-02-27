"""Sheet 清洗器：Excel 行 → List[CanonicalItem]"""
from typing import Dict, Type

from scripts.import_to_datasets.feishu_ceshi_case.parsers.canonical import CanonicalItem
from scripts.import_to_datasets.feishu_ceshi_case.parsers.cleaners.base import BaseSheetCleaner
from scripts.import_to_datasets.feishu_ceshi_case.parsers.cleaners.lsk import LskCleaner
from scripts.import_to_datasets.feishu_ceshi_case.parsers.cleaners.sh1128 import Sh1128Cleaner
from scripts.import_to_datasets.feishu_ceshi_case.parsers.cleaners.sh1128_history_qa import Sh1128HistoryQACleaner
from scripts.import_to_datasets.feishu_ceshi_case.parsers.cleaners.sh1128_multi import Sh1128MultiCleaner

_CLEANER_REGISTRY: Dict[str, Type[BaseSheetCleaner]] = {
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
    """
    if cleaner_type not in _CLEANER_REGISTRY:
        raise ValueError(f"未知的清洗器类型: {cleaner_type}，可选: {list(_CLEANER_REGISTRY.keys())}")
    return _CLEANER_REGISTRY[cleaner_type]()


__all__ = [
    "BaseSheetCleaner",
    "CanonicalItem",
    "get_cleaner_by_type",
    "LskCleaner",
    "Sh1128Cleaner",
    "Sh1128MultiCleaner",
    "Sh1128HistoryQACleaner",
]
