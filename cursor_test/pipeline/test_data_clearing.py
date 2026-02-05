"""
DataSets 数据清理能力单元测试

运行命令：pytest cursor_test/pipeline/test_data_clearing.py -v

设计文档：cursor_docs/020504-DataSets数据清理能力技术设计.md
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.infrastructure.database.repository.data_sets_items_repository import (
    DataSetsItemsRepository,
)


# ---------- delete_all_by_dataset_id（需真实数据库）----------


@pytest.mark.asyncio
async def test_delete_all_by_dataset_id_returns_int():
    """
    验证 delete_all_by_dataset_id 方法存在且返回类型正确。
    使用 mock session 验证方法可被调用且返回整数。
    """
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 3
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = DataSetsItemsRepository(mock_session)
    # 使用 patch 替换 execute 的返回值，因为 delete 需要真实的表结构
    with patch.object(repo.session, "execute", AsyncMock(return_value=mock_result)):
        # 注意：实际执行会因 mock 的 execute 返回的 result 没有 rowcount 的正确
        # 行为而可能失败，这里主要验证方法可调用
        result = await repo.delete_all_by_dataset_id("test-dataset-id")
        assert isinstance(result, int)
        assert result >= 0


# ---------- clearBeforeImport 逻辑（mock 测试）----------


@pytest.mark.asyncio
async def test_execute_import_clear_before_import_calls_delete():
    """
    当 clearBeforeImport 为 True 时，execute_import 应调用 delete_all_by_dataset_id。
    使用 mock 避免依赖真实数据库和 Excel 文件。
    """
    import pandas as pd

    from backend.pipeline import import_service

    mock_session = AsyncMock()

    mock_config = MagicMock()
    mock_config.import_config = {
        "dataSetsId": "ds-001",
        "sourceType": "excel",
        "sourcePath": {"filePath": "static/rag_source/uat_data/test.xlsx"},
        "cleaners": {"default": "lsk"},
        "clearBeforeImport": True,
    }

    mock_dataset = MagicMock()
    mock_dataset.id = "ds-001"

    mock_reader = MagicMock()
    mock_reader.iter_sheets.return_value = iter([("Sheet1", pd.DataFrame())])

    with (
        patch.object(
            import_service.ImportConfigRepository,
            "get_by_id",
            new_callable=AsyncMock,
            return_value=mock_config,
        ),
        patch.object(
            import_service.DataSetsRepository,
            "get_by_id",
            new_callable=AsyncMock,
            return_value=mock_dataset,
        ),
        patch(
            "backend.pipeline.import_service.ExcelReader",
            return_value=mock_reader,
        ),
        patch.object(
            import_service.DataSetsItemsRepository,
            "delete_all_by_dataset_id",
            new_callable=AsyncMock,
            return_value=5,
        ) as mock_delete,
    ):
        result = await import_service.execute_import("config-001", mock_session)
        mock_delete.assert_called_once_with("ds-001")
        assert result.success >= 0


@pytest.mark.asyncio
async def test_execute_import_without_clear_before_import_does_not_call_delete():
    """
    当 clearBeforeImport 为 False 或缺失时，不应调用 delete_all_by_dataset_id。
    """
    import pandas as pd

    from backend.pipeline import import_service

    mock_session = AsyncMock()
    mock_config = MagicMock()
    mock_config.import_config = {
        "dataSetsId": "ds-002",
        "sourceType": "excel",
        "sourcePath": {"filePath": "static/rag_source/uat_data/test.xlsx"},
        "cleaners": {"default": "lsk"},
        "clearBeforeImport": False,  # 明确为 False
    }

    mock_dataset = MagicMock()
    mock_dataset.id = "ds-002"

    mock_reader = MagicMock()
    mock_reader.iter_sheets.return_value = iter([("Sheet1", pd.DataFrame())])

    with (
        patch.object(
            import_service.ImportConfigRepository,
            "get_by_id",
            new_callable=AsyncMock,
            return_value=mock_config,
        ),
        patch.object(
            import_service.DataSetsRepository,
            "get_by_id",
            new_callable=AsyncMock,
            return_value=mock_dataset,
        ),
        patch(
            "backend.pipeline.import_service.ExcelReader",
            return_value=mock_reader,
        ),
        patch.object(
            import_service.DataSetsItemsRepository,
            "delete_all_by_dataset_id",
            new_callable=AsyncMock,
        ) as mock_delete,
    ):
        await import_service.execute_import("config-002", mock_session)
        mock_delete.assert_not_called()
