"""
批次任务领域层
设计文档：cursor_docs/022701、022803-批次任务执行模版与队列对接技术设计.md
"""
from backend.domain.batch.batch_template import CreateTemplate, ExecuteTemplate
from backend.domain.batch.dto import (
    BatchTaskExecutionResult,
    BatchTaskQueueItem,
    TaskPreCreateItem,
)

__all__ = [
    "TaskPreCreateItem",
    "BatchTaskQueueItem",
    "BatchTaskExecutionResult",
    "CreateTemplate",
    "ExecuteTemplate",
]
