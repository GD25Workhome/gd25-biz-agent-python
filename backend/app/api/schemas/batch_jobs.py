"""
批次任务创建与批次管理接口相关 Schema。

设计文档：cursor_docs/022703-批次任务通用创建接口技术设计.md、030202-批次任务batch_jobs与Step02清洗批次管理功能对比与缺口分析.md
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BatchJobStatsResponse(BaseModel):
    """批次列表单项（含子任务统计）。设计文档：030202。"""

    id: str = Field(..., description="批次 job id（batch_job.id）")
    job_type: str = Field(..., description="批次任务类型")
    code: str = Field(..., description="批次编码（batch_job.code）")
    total_count: int = Field(..., description="创建时预期子任务总数")
    query_params: Optional[Dict[str, Any]] = Field(None, description="创建时的查询参数")
    create_time: Optional[datetime] = Field(None, description="创建时间")
    update_time: Optional[datetime] = Field(None, description="更新时间")
    tasks_total: int = Field(0, description="实际子任务数量")
    status_pending_count: int = Field(0, description="待处理数量")
    status_running_count: int = Field(0, description="执行中数量")
    status_success_count: int = Field(0, description="成功数量")
    status_failed_count: int = Field(0, description="失败数量")


class BatchJobListResponse(BaseModel):
    """批次列表（含统计）响应。设计文档：030202。"""

    total: int = Field(..., description="满足条件的批次数")
    items: List[BatchJobStatsResponse] = Field(default_factory=list, description="批次列表")


class QueueStatsResponse(BaseModel):
    """队列统计响应。设计文档：030202。"""

    queue_size: int = Field(..., description="排队中任务数")
    in_flight_count: int = Field(..., description="队列中+执行中的任务 id 总数")


class BatchJobClearQueueResponse(BaseModel):
    """清空队列响应。设计文档：030202。"""

    removed: int = Field(..., description="从队列中移除的任务数")


class BatchJobRemoveBatchRequest(BaseModel):
    """按 job 移除队列请求。设计文档：030202。"""

    job_id: str = Field(..., description="批次 job id（batch_job.id）")


class BatchJobRemoveBatchResponse(BaseModel):
    """按 job 移除队列响应。设计文档：030202。"""

    removed: int = Field(..., description="从队列中移除的该批次任务数")


class BatchJobCreateRequest(BaseModel):
    """批次任务创建请求模型。"""

    job_type: str = Field(
        ...,
        description="批次任务类型，用于从注册表中查找具体 Handler，例如 pipeline_embedding",
    )
    query_params: Optional[Dict[str, Any]] = Field(
        None,
        description="与 job_type 对应的筛选 / 创建参数对象，由各 job_type 自行约定结构",
    )


class BatchJobCreateResponse(BaseModel):
    """批次任务创建响应模型。"""

    success: bool = Field(..., description="是否成功创建批次任务")
    message: str = Field(..., description="提示信息")
    job_type: str = Field(..., description="本批次任务类型")
    batch_code: str = Field(..., description="批次编码（batch_job.code）")
    total: int = Field(..., description="本批次创建的子任务总数（batch_job.total_count）")


class BatchJobRunResponse(BaseModel):
    """批次任务运行（入队）响应模型。设计文档：022803。"""

    enqueued: int = Field(..., description="本次入队的子任务数量")


class BatchTaskItemResponse(BaseModel):
    """单个 batch_task 列表项（供 job 下任务列表接口返回），含表内全部业务字段。"""

    id: str = Field(..., description="任务 id")
    job_id: str = Field(..., description="所属批次 job id")
    source_table_id: Optional[str] = Field(None, description="来源表 ID")
    source_table_name: Optional[str] = Field(None, description="来源表名")
    status: Optional[str] = Field(None, description="状态 pending/running/success/failed")
    runtime_params: Optional[Dict[str, Any]] = Field(None, description="运行时参数")
    redundant_key: Optional[str] = Field(None, description="冗余 key（去重/幂等用）")
    execution_result: Optional[str] = Field(None, description="执行返回结果")
    execution_error_message: Optional[str] = Field(None, description="执行失败信息")
    execution_return_key: Optional[str] = Field(None, description="执行返回 key")
    create_time: Optional[datetime] = Field(None, description="创建时间")
    update_time: Optional[datetime] = Field(None, description="更新时间")


class BatchTaskListResponse(BaseModel):
    """按 job 分页查询子任务列表响应。"""

    total: int = Field(..., description="该 job 下满足条件的任务总数")
    items: List[BatchTaskItemResponse] = Field(default_factory=list, description="任务列表")


class BatchTaskExecuteRequest(BaseModel):
    """单行任务执行请求。设计文档：030204。"""

    task_id: str = Field(..., description="要执行的任务 id")


class BatchTaskExecuteResponse(BaseModel):
    """单行任务执行响应。设计文档：030204。"""

    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="提示信息")
    enqueued: int = Field(..., description="本次入队数量（1 表示成功入队）")

