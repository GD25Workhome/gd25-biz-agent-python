"""
批次任务预创建与执行 DTO。
设计文档：cursor_docs/022701-批次任务创建模版设计方案.md、022803-批次任务执行模版与队列对接技术设计.md
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


@dataclass
class BatchTaskQueueItem:
    """
    批次任务队列元素 / 执行入口统一入参。
    设计文档：cursor_docs/022803-批次任务执行模版与队列对接技术设计.md
    """

    job_type: str
    task_id: str
    task_version: int


@dataclass
class BatchTaskExecutionResult:
    """
    执行结果标准对象，供模版回写到 batch_task。
    必含 execution_return_key；其它字段由业务自定，与 execution_return_key 一起序列化写入 execution_result。
    设计文档：cursor_docs/022803-批次任务执行模版与队列对接技术设计.md
    """

    execution_return_key: str
