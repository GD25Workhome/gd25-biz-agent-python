"""
数据清洗相关路由
设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
"""
import logging
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.data_cleaning import (
    DataSetsPathCreate,
    DataSetsPathUpdate,
    DataSetsPathResponse,
    DataSetsPathTreeNode,
    DataSetsCreate,
    DataSetsUpdate,
    DataSetsResponse,
    DataSetsListResponse,
    DataSetsItemsCreate,
    DataSetsItemsUpdate,
    DataSetsItemsResponse,
    DataSetsItemsListResponse,
    ImportConfigCreate,
    ImportConfigUpdate,
    ImportConfigResponse,
    ImportConfigListResponse,
)
from backend.infrastructure.database.connection import get_async_session
from backend.infrastructure.database.repository.data_sets_path_repository import (
    DataSetsPathRepository,
)
from backend.infrastructure.database.repository.data_sets_repository import (
    DataSetsRepository,
)
from backend.infrastructure.database.repository.data_sets_items_repository import (
    DataSetsItemsRepository,
)
from backend.infrastructure.database.repository.import_config_repository import (
    ImportConfigRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data-cleaning", tags=["数据清洗"])


def _to_create_kwargs(data: Any, exclude: Optional[List[str]] = None) -> dict:
    """将 Create/Update schema 转为 model create/update 的 kwargs，处理 metadata -> metadata_"""
    exclude = exclude or []
    d = data.model_dump(exclude_unset=True, exclude=exclude)
    if "metadata" in d:
        d["metadata_"] = d.pop("metadata")
    return d


# ---------- DataSetsPath ----------
@router.get("/paths/tree", response_model=List[DataSetsPathTreeNode])
async def get_paths_tree(session: AsyncSession = Depends(get_async_session)):
    """获取路径树形结构"""
    try:
        repo = DataSetsPathRepository(session)
        tree = await repo.get_tree()
        await session.commit()
        return tree
    except Exception as e:
        await session.rollback()
        logger.error("获取路径树失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/paths/{path_id}", response_model=DataSetsPathResponse)
async def get_path(path_id: str, session: AsyncSession = Depends(get_async_session)):
    """获取单条路径"""
    try:
        repo = DataSetsPathRepository(session)
        record = await repo.get_by_id(path_id)
        await session.commit()
        if not record:
            raise HTTPException(status_code=404, detail="路径不存在")
        return DataSetsPathResponse.model_validate(record)
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("获取路径失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/paths", response_model=DataSetsPathResponse)
async def create_path(data: DataSetsPathCreate, session: AsyncSession = Depends(get_async_session)):
    """创建路径"""
    try:
        repo = DataSetsPathRepository(session)
        record = await repo.create(
            id=data.id,
            id_path=data.id_path,
            name=data.name,
            description=data.description,
            metadata_=data.metadata,
        )
        await session.commit()
        return DataSetsPathResponse.model_validate(record)
    except Exception as e:
        await session.rollback()
        logger.error("创建路径失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/paths/{path_id}", response_model=DataSetsPathResponse)
async def update_path(
    path_id: str,
    data: DataSetsPathUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    """更新路径"""
    try:
        repo = DataSetsPathRepository(session)
        record = await repo.update(path_id, **_to_create_kwargs(data))
        await session.commit()
        if not record:
            raise HTTPException(status_code=404, detail="路径不存在")
        await session.refresh(record)  # 在异步上下文中刷新，确保 updated_at 等属性已加载
        return DataSetsPathResponse.model_validate(record)
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("更新路径失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/paths/{path_id}")
async def delete_path(path_id: str, session: AsyncSession = Depends(get_async_session)):
    """删除路径"""
    try:
        repo = DataSetsPathRepository(session)
        ok = await repo.delete(path_id)
        await session.commit()
        if not ok:
            raise HTTPException(status_code=404, detail="路径不存在")
        return {"message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("删除路径失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------- DataSets ----------
@router.get("/datasets", response_model=DataSetsListResponse)
async def list_datasets(
    path_id: Optional[str] = Query(None, description="按 path_id 筛选"),
    name: Optional[str] = Query(None, description="名称（包含）"),
    keyword: Optional[str] = Query(None, description="关键词（在 input_schema/output_schema/metadata 中搜索）"),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_session),
):
    """数据集合列表"""
    try:
        repo = DataSetsRepository(session)
        items, total = await repo.get_list_with_total(
            path_id=path_id, name=name, keyword=keyword, limit=limit, offset=offset
        )
        await session.commit()
        return DataSetsListResponse(
            total=total,
            items=[DataSetsResponse.model_validate(r) for r in items],
        )
    except Exception as e:
        await session.rollback()
        logger.error("查询数据集合列表失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets/{dataset_id}", response_model=DataSetsResponse)
async def get_dataset(dataset_id: str, session: AsyncSession = Depends(get_async_session)):
    """获取单条数据集合"""
    try:
        repo = DataSetsRepository(session)
        record = await repo.get_by_id(dataset_id)
        await session.commit()
        if not record:
            raise HTTPException(status_code=404, detail="数据集合不存在")
        return DataSetsResponse.model_validate(record)
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("获取数据集合失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/datasets", response_model=DataSetsResponse)
async def create_dataset(data: DataSetsCreate, session: AsyncSession = Depends(get_async_session)):
    """创建数据集合"""
    try:
        repo = DataSetsRepository(session)
        record = await repo.create(
            name=data.name,
            path_id=data.path_id,
            input_schema=data.input_schema,
            output_schema=data.output_schema,
            metadata_=data.metadata,
        )
        await session.commit()
        return DataSetsResponse.model_validate(record)
    except Exception as e:
        await session.rollback()
        logger.error("创建数据集合失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/datasets/{dataset_id}", response_model=DataSetsResponse)
async def update_dataset(
    dataset_id: str,
    data: DataSetsUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    """更新数据集合"""
    try:
        repo = DataSetsRepository(session)
        record = await repo.update(dataset_id, **_to_create_kwargs(data))
        await session.commit()
        if not record:
            raise HTTPException(status_code=404, detail="数据集合不存在")
        await session.refresh(record)  # 在异步上下文中刷新，确保 updated_at 等属性已加载
        return DataSetsResponse.model_validate(record)
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("更新数据集合失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str, session: AsyncSession = Depends(get_async_session)):
    """删除数据集合"""
    try:
        repo = DataSetsRepository(session)
        ok = await repo.delete(dataset_id)
        await session.commit()
        if not ok:
            raise HTTPException(status_code=404, detail="数据集合不存在")
        return {"message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("删除数据集合失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------- DataSetsItems ----------
@router.get(
    "/datasets/{dataset_id}/items",
    response_model=DataSetsItemsListResponse,
)
async def list_dataset_items(
    dataset_id: str,
    status: Optional[int] = Query(None, description="1=激活，0=废弃"),
    unique_key: Optional[str] = Query(None, description="unique_key（包含）"),
    source: Optional[str] = Query(None, description="source（包含）"),
    keyword: Optional[str] = Query(None, description="关键词（在 input/output/metadata 中搜索）"),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_session),
):
    """数据项列表"""
    try:
        repo = DataSetsItemsRepository(session)
        items, total = await repo.get_list_with_total(
            dataset_id=dataset_id,
            status=status,
            unique_key=unique_key,
            source=source,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
        await session.commit()
        return DataSetsItemsListResponse(
            total=total,
            items=[DataSetsItemsResponse.model_validate(r) for r in items],
        )
    except Exception as e:
        await session.rollback()
        logger.error("查询数据项列表失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/datasets/{dataset_id}/items/{item_id}",
    response_model=DataSetsItemsResponse,
)
async def get_dataset_item(
    dataset_id: str,
    item_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    """获取单条数据项"""
    try:
        repo = DataSetsItemsRepository(session)
        record = await repo.get_by_id(item_id)
        await session.commit()
        if not record or record.dataset_id != dataset_id:
            raise HTTPException(status_code=404, detail="数据项不存在")
        return DataSetsItemsResponse.model_validate(record)
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("获取数据项失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/datasets/{dataset_id}/items",
    response_model=DataSetsItemsResponse,
)
async def create_dataset_item(
    dataset_id: str,
    data: DataSetsItemsCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """创建数据项"""
    try:
        repo = DataSetsItemsRepository(session)
        record = await repo.create(
            dataset_id=dataset_id,
            unique_key=data.unique_key,
            input=data.input,
            output=data.output,
            metadata_=data.metadata,
            status=data.status,
            source=data.source,
        )
        await session.commit()
        return DataSetsItemsResponse.model_validate(record)
    except Exception as e:
        await session.rollback()
        logger.error("创建数据项失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/datasets/{dataset_id}/items/{item_id}",
    response_model=DataSetsItemsResponse,
)
async def update_dataset_item(
    dataset_id: str,
    item_id: str,
    data: DataSetsItemsUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    """更新数据项"""
    try:
        repo = DataSetsItemsRepository(session)
        record = await repo.get_by_id(item_id)
        if not record or record.dataset_id != dataset_id:
            raise HTTPException(status_code=404, detail="数据项不存在")
        record = await repo.update(item_id, **_to_create_kwargs(data))
        await session.commit()
        await session.refresh(record)  # 在异步上下文中刷新，确保 updated_at 等属性已加载
        return DataSetsItemsResponse.model_validate(record)
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("更新数据项失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/datasets/{dataset_id}/items/{item_id}")
async def delete_dataset_item(
    dataset_id: str,
    item_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    """删除数据项"""
    try:
        repo = DataSetsItemsRepository(session)
        record = await repo.get_by_id(item_id)
        if not record or record.dataset_id != dataset_id:
            raise HTTPException(status_code=404, detail="数据项不存在")
        await repo.delete(item_id)
        await session.commit()
        return {"message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("删除数据项失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/datasets/{dataset_id}/items")
async def clear_all_dataset_items(
    dataset_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    """
    清空指定 DataSet 下所有数据项。
    设计文档：cursor_docs/020504-DataSets数据清理能力技术设计.md
    """
    try:
        ds_repo = DataSetsRepository(session)
        dataset = await ds_repo.get_by_id(dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="数据集合不存在")
        items_repo = DataSetsItemsRepository(session)
        deleted_count = await items_repo.delete_all_by_dataset_id(dataset_id)
        await session.commit()
        return {"message": "清空成功", "deleted_count": deleted_count}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("清空数据项失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------- ImportConfig ----------
@router.get("/import-configs", response_model=ImportConfigListResponse)
async def list_import_configs(
    name: Optional[str] = Query(None, description="名称（包含）"),
    keyword: Optional[str] = Query(None, description="关键词（在 name/description/import_config 中搜索）"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_session),
):
    """导入配置列表"""
    try:
        repo = ImportConfigRepository(session)
        items, total = await repo.get_list_with_total(
            name=name, keyword=keyword, limit=limit, offset=offset
        )
        await session.commit()
        return ImportConfigListResponse(
            total=total,
            items=[ImportConfigResponse.model_validate(r) for r in items],
        )
    except Exception as e:
        await session.rollback()
        logger.error("查询导入配置列表失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/import-configs/{config_id}", response_model=ImportConfigResponse)
async def get_import_config(
    config_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    """获取单条导入配置"""
    try:
        repo = ImportConfigRepository(session)
        record = await repo.get_by_id(config_id)
        await session.commit()
        if not record:
            raise HTTPException(status_code=404, detail="导入配置不存在")
        return ImportConfigResponse.model_validate(record)
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("获取导入配置失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-configs", response_model=ImportConfigResponse)
async def create_import_config(
    data: ImportConfigCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """创建导入配置"""
    try:
        repo = ImportConfigRepository(session)
        record = await repo.create(
            name=data.name,
            description=data.description,
            import_config=data.import_config,
        )
        await session.commit()
        return ImportConfigResponse.model_validate(record)
    except Exception as e:
        await session.rollback()
        logger.error("创建导入配置失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/import-configs/{config_id}", response_model=ImportConfigResponse)
async def update_import_config(
    config_id: str,
    data: ImportConfigUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    """更新导入配置"""
    try:
        repo = ImportConfigRepository(session)
        record = await repo.update(config_id, **_to_create_kwargs(data))
        await session.commit()
        if not record:
            raise HTTPException(status_code=404, detail="导入配置不存在")
        await session.refresh(record)  # 在异步上下文中刷新，确保 updated_at 等属性已加载
        return ImportConfigResponse.model_validate(record)
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("更新导入配置失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/import-configs/{config_id}")
async def delete_import_config(
    config_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    """删除导入配置"""
    try:
        repo = ImportConfigRepository(session)
        ok = await repo.delete(config_id)
        await session.commit()
        if not ok:
            raise HTTPException(status_code=404, detail="导入配置不存在")
        return {"message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("删除导入配置失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------- 执行导入 ----------
@router.post("/import-configs/{config_id}/execute")
async def execute_import_endpoint(
    config_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    """
    执行导入：根据配置 ID 查询配置并执行导入流程。
    设计文档：cursor_docs/020402-数据导入流程技术设计.md
    """
    from backend.pipeline.import_service import (
        CleanerNotConfiguredError,
        DataSetsNotFoundError,
        ImportConfigNotFoundError,
        PipelineImportError,
        UnsupportedSourceTypeError,
        execute_import,
    )

    try:
        result = await execute_import(config_id, session)
        await session.commit()
        return {
            "success": True,
            "stats": result.to_dict(),
            "message": "导入完成",
        }
    except (
        ImportConfigNotFoundError,
        DataSetsNotFoundError,
        UnsupportedSourceTypeError,
        CleanerNotConfiguredError,
        PipelineImportError,
    ) as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=e.message)
    except (FileNotFoundError, ValueError) as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error("执行导入失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
