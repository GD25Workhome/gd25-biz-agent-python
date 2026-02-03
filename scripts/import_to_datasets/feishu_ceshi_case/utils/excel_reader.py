"""
Excel 读取工具

参考 import_blood_pressure_session_data.py 的读取逻辑，
提供通用的 Excel 读取能力。
"""
import logging
from pathlib import Path
from typing import Iterator, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class ExcelReader:
    """Excel 文件读取器"""

    def __init__(self, excel_path: Path) -> None:
        """
        Args:
            excel_path: Excel 文件路径
        """
        self.excel_path = excel_path
        self._excel_file: pd.ExcelFile | None = None

    @property
    def excel_name(self) -> str:
        """Excel 文件名（不含扩展名）"""
        return self.excel_path.stem

    def get_sheet_names(self) -> list[str]:
        """获取所有 Sheet 名称"""
        if self._excel_file is None:
            self._excel_file = pd.ExcelFile(self.excel_path)
        return self._excel_file.sheet_names

    def iter_sheets(
        self,
    ) -> Iterator[Tuple[str, pd.DataFrame]]:
        """
        迭代所有 Sheet，返回 (sheet_name, dataframe)

        Yields:
            Tuple[str, pd.DataFrame]: Sheet 名称与对应的 DataFrame
        """
        for sheet_name in self.get_sheet_names():
            df = pd.read_excel(self.excel_path, sheet_name=sheet_name)
            yield sheet_name, df

    def read_sheet(self, sheet_name: str) -> pd.DataFrame:
        """读取指定 Sheet"""
        return pd.read_excel(self.excel_path, sheet_name=sheet_name)
