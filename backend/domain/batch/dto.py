"""
批次任务预创建 DTO
设计文档：cursor_docs/022701-批次任务创建模版设计方案.md
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class TaskPreCreateItem:
    """单条子任务的预创建数据（由子类 query 接口返回）。"""

    source_table_id: Optional[str] = None
    source_table_name: Optional[str] = None
    runtime_params: Optional[Dict[str, Any]] = None
    redundant_key: Optional[str] = None
