"""
清洗器基类：Excel 行 → List[CanonicalItem]

各 Sheet 清洗器实现 clean()、is_empty_row()，输出规范格式。
"""
from abc import ABC, abstractmethod
from typing import List

import pandas as pd

from scripts.import_to_datasets.feishu_ceshi_case.parsers.canonical import CanonicalItem


class BaseSheetCleaner(ABC):
    """Sheet 清洗器基类：Excel 行 → List[CanonicalItem]"""

    @abstractmethod
    def clean(self, row: pd.Series, df: pd.DataFrame) -> List[CanonicalItem]:
        """清洗单行，返回 0 个或多个 CanonicalItem"""
        pass

    @abstractmethod
    def is_empty_row(self, row: pd.Series, df: pd.DataFrame) -> bool:
        """是否为空行（跳过）"""
        pass
