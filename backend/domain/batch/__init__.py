"""
批次任务领域层
设计文档：cursor_docs/022701-批次任务创建模版设计方案.md
"""
from backend.domain.batch.dto import TaskPreCreateItem
from backend.domain.batch.create_template import BatchCreateTemplate

__all__ = [
    "TaskPreCreateItem",
    "BatchCreateTemplate",
]
