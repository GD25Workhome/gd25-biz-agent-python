"""
Excel 读取器

根据配置读取 Excel 文件，支持 sheetNames 过滤（null/单字符串/数组）。
设计文档：cursor_docs/020402-数据导入流程技术设计.md
"""
import logging
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple, Union

import pandas as pd

from backend.app.config import find_project_root
from backend.pipeline.readers.base import BaseReader

logger = logging.getLogger(__name__)


class ExcelReader(BaseReader):
    """Excel 文件读取器，根据配置解析 filePath 和 sheetNames"""
    # TODO 这里的数据读取是针对单个文件的，如果后续有需要读取多个文件，需要进行升级

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Args:
            config: 导入配置，需包含 sourcePath.filePath、可选 sheetNames
        """
        self._config = config or {}
        source_path = self._config.get("sourcePath") or {}
        file_path = source_path.get("filePath") or ""
        if not file_path:
            raise ValueError("配置缺少 sourcePath.filePath")

        project_root = find_project_root()
        self._excel_path = (project_root / file_path.strip()).resolve()
        if not self._excel_path.exists():
            raise FileNotFoundError(f"Excel 文件不存在: {self._excel_path}")

        self._sheet_names: Union[None, str, List[str]] = self._config.get("sheetNames")
        self._excel_file: pd.ExcelFile | None = None

    def _get_sheets_to_read(self) -> List[str]:
        """根据 sheetNames 配置确定要读取的 sheet 列表"""
        if self._excel_file is None:
            self._excel_file = pd.ExcelFile(self._excel_path)
        all_sheets = self._excel_file.sheet_names

        if self._sheet_names is None:
            return all_sheets
        if isinstance(self._sheet_names, str):
            if self._sheet_names.strip() in all_sheets:
                return [self._sheet_names.strip()]
            raise ValueError(f"Sheet 不存在: {self._sheet_names}")
        if isinstance(self._sheet_names, list):
            result = []
            for name in self._sheet_names:
                s = (name.strip() if isinstance(name, str) else str(name)).strip()
                if s and s in all_sheets:
                    result.append(s)
                elif s:
                    logger.warning("Sheet 不存在，跳过: %s", s)
            return result
        return all_sheets

    def iter_sheets(self) -> Iterator[Tuple[str, pd.DataFrame]]:
        """
        迭代要读取的 Sheet，返回 (sheet_name, DataFrame)。

        Yields:
            Tuple[str, pd.DataFrame]: Sheet 名称与对应的 DataFrame
        """
        sheets = self._get_sheets_to_read()
        for sheet_name in sheets:
            df = pd.read_excel(self._excel_path, sheet_name=sheet_name)
            yield sheet_name, df
