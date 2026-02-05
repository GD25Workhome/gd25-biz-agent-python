"""
导入入口服务

编排「读取器 → 清洗器 → 入库执行器」三阶段流程。
设计文档：cursor_docs/020402-数据导入流程技术设计.md
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.data_sets_repository import DataSetsRepository
from backend.infrastructure.database.repository.import_config_repository import (
    ImportConfigRepository,
)
from backend.pipeline.cleaners.canonical import canonical_to_dataset_item
from backend.pipeline.cleaners.registry import get_cleaner_by_type
from backend.pipeline.readers.excel_reader import ExcelReader
from backend.pipeline.writers.dataset_item_writer import DatasetItemWriter

logger = logging.getLogger(__name__)


# ---------- 异常定义 ----------


class PipelineImportError(Exception):
    """导入流程基础异常"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ImportConfigNotFoundError(PipelineImportError):
    """导入配置不存在"""

    def __init__(self, config_id: str) -> None:
        super().__init__(f"导入配置不存在: {config_id}")


class DataSetsNotFoundError(PipelineImportError):
    """DataSets 不存在"""

    def __init__(self, dataset_id: str) -> None:
        super().__init__(f"DataSets 不存在: {dataset_id}")


class UnsupportedSourceTypeError(PipelineImportError):
    """不支持的源类型"""

    def __init__(self, source_type: str) -> None:
        super().__init__(f"不支持的源类型: {source_type}")


class CleanerNotConfiguredError(PipelineImportError):
    """清洗器未配置"""

    def __init__(self, sheet_name: str) -> None:
        super().__init__(f"Sheet '{sheet_name}' 未配置清洗器，且 cleaners.default 缺失")


# ---------- 结果模型 ----------


@dataclass
class ImportResult:
    """导入结果"""

    success: int = 0
    fail: int = 0
    skipped: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "fail": self.fail,
            "skipped": self.skipped,
        }


# ---------- 主流程 ----------


async def execute_import(config_id: str, session: AsyncSession) -> ImportResult:
    """
    执行导入流程

    Args:
        config_id: 导入配置 ID
        session: 数据库会话

    Returns:
        ImportResult: 导入统计结果

    Raises:
        ImportConfigNotFoundError: 配置不存在
        DataSetsNotFoundError: DataSets 不存在
        UnsupportedSourceTypeError: 不支持的源类型
        CleanerNotConfiguredError: 清洗器未配置
    """
    # 1. 查询导入配置
    config_repo = ImportConfigRepository(session)
    config = await config_repo.get_by_id(config_id)
    if not config:
        raise ImportConfigNotFoundError(config_id)

    meta: Dict[str, Any] = config.import_config or {}
    if not isinstance(meta, dict):
        meta = {}

    # 2. 校验 dataSetsId
    data_sets_id = meta.get("dataSetsId")
    if not data_sets_id:
        raise PipelineImportError("配置缺少 dataSetsId")

    data_sets_repo = DataSetsRepository(session)
    dataset = await data_sets_repo.get_by_id(data_sets_id)
    if not dataset:
        raise DataSetsNotFoundError(data_sets_id)

    # 3. 根据 sourceType 选择读取器
    source_type = meta.get("sourceType") or "excel"
    if source_type != "excel":
        raise UnsupportedSourceTypeError(source_type)

    # 4. 校验 cleaners 配置
    cleaners_config = meta.get("cleaners") or {}
    if not isinstance(cleaners_config, dict):
        cleaners_config = {}
    if "default" not in cleaners_config:
        raise PipelineImportError("配置 cleaners 必须包含 default 键")

    # 5. 创建读取器与写入器
    reader = ExcelReader(meta) # TODO 这里现在是定制的，后续需要升级
    writer = DatasetItemWriter(session)
    stats = ImportResult()

    source_path = meta.get("sourcePath") or {}
    file_path = source_path.get("filePath") or ""

    # 6. 迭代 sheet → 清洗 → 入库
    for sheet_name, df in reader.iter_sheets():
        cleaner_key = cleaners_config.get(sheet_name) or cleaners_config.get("default")
        if not cleaner_key:
            raise CleanerNotConfiguredError(sheet_name)

        cleaner = get_cleaner_by_type(cleaner_key)
        source_value = f"excel:{file_path}:{sheet_name}" if file_path else f"excel:{sheet_name}"

        for idx, row in df.iterrows():
            if cleaner.is_empty_row(row, df):
                stats.skipped += 1
                continue
            try:
                canonical_items = cleaner.clean(row, df)
                for item in canonical_items:
                    dto = canonical_to_dataset_item(item)
                    await writer.write_item(
                        dataset_id=dataset.id,
                        item=dto,
                        source=source_value,
                        status=1,
                    )
                    stats.success += 1
            except Exception as e:
                stats.fail += 1
                logger.error("Sheet '%s' 第 %d 行处理失败: %s", sheet_name, idx + 2, e)

    return stats
