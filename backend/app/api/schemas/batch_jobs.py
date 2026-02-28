"""
批次任务创建接口相关 Schema。

设计文档：cursor_docs/022703-批次任务通用创建接口技术设计.md
"""
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


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

