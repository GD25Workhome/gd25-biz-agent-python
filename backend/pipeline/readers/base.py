"""
读取器基类

定义原始数据读取器的抽象接口。
设计文档：cursor_docs/020402-数据导入流程技术设计.md
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, Tuple

import pandas as pd


class BaseReader(ABC):
    """原始数据读取器基类"""

    @abstractmethod
    def iter_sheets(self) -> Iterator[Tuple[str, pd.DataFrame]]:
        """
        迭代读取数据，返回 (sheet_name, DataFrame)。

        Yields:
            Tuple[str, pd.DataFrame]: Sheet 名称与对应的 DataFrame
        """
        pass
