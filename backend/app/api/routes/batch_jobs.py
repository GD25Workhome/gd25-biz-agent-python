"""
批次任务通用创建与运行接口路由。

提供基于 job_type 的通用批次创建入口；提供按 job_id 的运行（入队）入口；
提供批次列表（含统计）、队列统计、清空队列、按 job 移除队列。
设计文档：cursor_docs/022703、022803、030202-批次任务batch_jobs与Step02清洗批次管理功能对比与缺口分析.md
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.batch_jobs import (
    BatchJobClearQueueResponse,
    BatchJobCreateRequest,
    BatchJobCreateResponse,
    BatchJobListResponse,
    BatchJobRemoveBatchRequest,
    BatchJobRemoveBatchResponse,
    BatchJobRunResponse,
    BatchJobStatsResponse,
    BatchTaskExecuteRequest,
    BatchTaskExecuteResponse,
    BatchTaskItemResponse,
    BatchTaskListResponse,
    QueueStatsResponse,
)
from backend.domain.batch.batch_job_service import BatchJobCreateService
from backend.domain.batch.exceptions import InvalidJobParamsError, UnknownJobTypeError
from backend.infrastructure.database.connection import get_async_session
from backend.infrastructure.database.repository.batch.batch_job_repository import (
    BatchJobRepository,
)
from backend.infrastructure.database.repository.batch.batch_task_repository import (
    BatchTaskRepository,
)
from backend.pipeline.batch_task_queue_service import (
    clear_all_queue,
    enqueue_batch_by_job_id,
    enqueue_task_by_id,
    get_queue_stats,
    remove_batch_by_job_id,
    rerun_batch_by_job_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch-jobs", tags=["批次任务"])


@router.get("", response_model=BatchJobListResponse)
async def list_batch_jobs(
    code: Optional[str] = Query(None, description="批次编码（包含）"),
    job_type: Optional[str] = Query(None, description="批次任务类型（精确）"),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_session),
) -> BatchJobListResponse:
    """
    批次列表（含子任务统计）。设计文档：030202。
    """
    try:
        repo = BatchJobRepository(session)
        rows, total = await repo.get_jobs_with_stats(
            code=code,
            job_type=job_type,
            limit=limit,
            offset=offset,
        )
        items = [
            BatchJobStatsResponse(
                id=row.record.id,
                job_type=row.record.job_type or "",
                code=row.record.code or "",
                total_count=row.record.total_count or 0,
                query_params=row.record.query_params,
                create_time=getattr(row.record, "create_time", None),
                update_time=getattr(row.record, "update_time", None),
                tasks_total=row.tasks_total,
                status_pending_count=row.status_pending_count,
                status_running_count=row.status_running_count,
                status_success_count=row.status_success_count,
                status_failed_count=row.status_failed_count,
            )
            for row in rows
        ]
        return BatchJobListResponse(total=total, items=items)
    except Exception as e:
        await session.rollback()
        logger.error("查询批次列表失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="查询批次列表失败")


@router.get("/queue-stats", response_model=QueueStatsResponse)
async def get_batch_jobs_queue_stats() -> QueueStatsResponse:
    """
    队列统计：排队数、执行中+排队总数。设计文档：030202。
    """
    stats = get_queue_stats()
    return QueueStatsResponse(**stats)


@router.post("/clear-queue", response_model=BatchJobClearQueueResponse)
async def clear_batch_jobs_queue() -> BatchJobClearQueueResponse:
    """
    清空全部队列（仅排队中的任务，正在执行的不中断）。设计文档：030202。
    """
    removed = clear_all_queue()
    return BatchJobClearQueueResponse(removed=removed)


@router.post("/remove-batch", response_model=BatchJobRemoveBatchResponse)
async def remove_batch_from_queue_endpoint(
    data: BatchJobRemoveBatchRequest,
    session: AsyncSession = Depends(get_async_session),
) -> BatchJobRemoveBatchResponse:
    """
    从队列中移除指定 job 下的任务（仅尚未被消费的）。设计文档：030202。
    """
    job_id = (data.job_id or "").strip()
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id 不能为空")
    try:
        removed = await remove_batch_by_job_id(job_id, session)
        return BatchJobRemoveBatchResponse(removed=removed)
    except Exception as e:
        await session.rollback()
        logger.error("移除批次队列失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="移除批次队列失败")


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


@router.post("/tasks/execute", response_model=BatchTaskExecuteResponse)
async def execute_batch_task_endpoint(
    data: BatchTaskExecuteRequest,
    session: AsyncSession = Depends(get_async_session),
) -> BatchTaskExecuteResponse:
    """
    单行任务执行：将指定 task 置为 pending 并入队，入参仅 task_id。
    设计文档：cursor_docs/030204-Step03-1任务子界面类数据清洗能力技术设计.md
    """
    task_id = (data.task_id or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id 不能为空")
    try:
        task_repo = BatchTaskRepository(session)
        task = await task_repo.get_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        await task_repo.update_status_to_pending(task_id)
        await session.commit()
        enqueued = await enqueue_task_by_id(task_id, session)
        return BatchTaskExecuteResponse(
            success=True,
            message="已入队执行",
            enqueued=enqueued,
        )
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("单行任务执行失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="单行任务执行失败，请稍后重试")


@router.get("/{job_id}/tasks", response_model=BatchTaskListResponse)
async def list_batch_tasks(
    job_id: str,
    id: Optional[str] = Query(None, description="任务 id（精确匹配）"),
    status: Optional[str] = Query(None, description="状态筛选：pending/running/success/failed"),
    source_table_id: Optional[str] = Query(None, description="来源表 ID（包含）"),
    source_table_name: Optional[str] = Query(None, description="来源表名（包含）"),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_session),
) -> BatchTaskListResponse:
    """
    按 job 分页查询子任务列表，支持 id、status、source_table_id、source_table_name 筛选。
    """
    job_id = (job_id or "").strip()
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id 不能为空")
    try:
        task_repo = BatchTaskRepository(session)
        total = await task_repo.count_by_job(
            job_id=job_id,
            status=status,
            task_id=id,
            source_table_id=source_table_id,
            source_table_name=source_table_name,
        )
        tasks = await task_repo.get_list(
            job_id=job_id,
            status=status,
            task_id=id,
            source_table_id=source_table_id,
            source_table_name=source_table_name,
            limit=limit,
            offset=offset,
        )
        items = [
            BatchTaskItemResponse(
                id=t.id,
                job_id=t.job_id or "",
                source_table_id=t.source_table_id,
                source_table_name=t.source_table_name,
                status=t.status,
                runtime_params=t.runtime_params,
                redundant_key=t.redundant_key,
                execution_result=t.execution_result,
                execution_error_message=t.execution_error_message,
                execution_return_key=t.execution_return_key,
                create_time=getattr(t, "create_time", None),
                update_time=getattr(t, "update_time", None),
            )
            for t in tasks
        ]
        return BatchTaskListResponse(total=total, items=items)
    except Exception as e:
        await session.rollback()
        logger.error("查询批次子任务列表失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="查询批次子任务列表失败")


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


@router.post("/{job_id}/rerun", response_model=BatchJobRunResponse)
async def rerun_batch_job_endpoint(
    job_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> BatchJobRunResponse:
    """
    重跑指定批次：先将该 job 下所有子任务状态改为 pending，再全部入队执行。
    与 run 的区别是：run 仅入队当前已是 pending 的任务；rerun 会重置所有任务为 pending 后再入队。
    设计文档：Step03-1 重跑功能。
    """
    job_id = (job_id or "").strip()
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id 不能为空")
    try:
        enqueued = await rerun_batch_by_job_id(job_id, session)
        await session.commit()
        return BatchJobRunResponse(enqueued=enqueued)
    except Exception as e:
        await session.rollback()
        logger.error("批次任务重跑失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="批次任务重跑失败，请稍后重试")

