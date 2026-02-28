"""
批次任务通用创建与运行接口路由。

提供基于 job_type 的通用批次创建入口；提供按 job_id 的运行（入队）入口。
设计文档：cursor_docs/022703、022803-批次任务执行模版与队列对接技术设计.md
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.batch_jobs import (
    BatchJobCreateRequest,
    BatchJobCreateResponse,
    BatchJobRunResponse,
)
from backend.domain.batch.batch_job_service import BatchJobCreateService
from backend.domain.batch.exceptions import InvalidJobParamsError, UnknownJobTypeError
from backend.infrastructure.database.connection import get_async_session
from backend.pipeline.batch_task_queue_service import enqueue_batch_by_job_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch-jobs", tags=["批次任务"])


@router.post("/create", response_model=BatchJobCreateResponse)
async def create_batch_job_endpoint(
    data: BatchJobCreateRequest,
    session: AsyncSession = Depends(get_async_session),
) -> BatchJobCreateResponse:
    """
    通用批次任务创建接口。

    根据 job_type 将请求路由到对应的批次创建 Handler，并返回创建结果。
    """
    try:
        job_type = (data.job_type or "").strip()
        if not job_type:
            raise InvalidJobParamsError("job_type 不能为空")

        if data.query_params is not None and not isinstance(data.query_params, dict):
            raise InvalidJobParamsError("query_params 必须是对象（JSON object）")

        service = BatchJobCreateService(session=session)
        job = await service.create_batch(
            job_type=job_type,
            query_params=data.query_params or {},
        )
        await session.commit()
        return BatchJobCreateResponse(
            success=True,
            message="批次任务创建成功",
            job_type=job.job_type,
            batch_code=job.code,
            total=job.total_count,
        )
    except (InvalidJobParamsError, UnknownJobTypeError) as e:
        await session.rollback()
        logger.warning("批次任务创建参数错误: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        # 已转换为 HTTP 异常的情况直接向上抛出
        raise
    except Exception as e:
        await session.rollback()
        logger.error("批次任务创建失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="批次任务创建失败，请稍后重试")


@router.post("/{job_id}/run", response_model=BatchJobRunResponse)
async def run_batch_job_endpoint(
    job_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> BatchJobRunResponse:
    """
    将指定批次（job_id 为 BatchJobRecord.id）下 pending 的 batch_task 入队。
    设计文档：cursor_docs/022803-批次任务执行模版与队列对接技术设计.md
    """
    job_id = (job_id or "").strip()
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id 不能为空")
    try:
        enqueued = await enqueue_batch_by_job_id(job_id, session)
        await session.commit()
        return BatchJobRunResponse(enqueued=enqueued)
    except Exception as e:
        await session.rollback()
        logger.error("批次任务入队失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="批次任务入队失败，请稍后重试")

