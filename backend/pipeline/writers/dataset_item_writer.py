"""
入库执行器

将清洗后的数据写入 pipeline_data_sets_items 表。
设计文档：cursor_docs/020402-数据导入流程技术设计.md
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.data_sets_items_repository import (
    DataSetsItemsRepository,
)
from backend.pipeline.cleaners.canonical import DatasetItemDto

logger = logging.getLogger(__name__)


class DatasetItemWriter:
    """DataSet Item 入库执行器，写入 pipeline_data_sets_items 表"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DataSetsItemsRepository(session)

    async def write_item(
        self,
        dataset_id: str,
        item: DatasetItemDto,
        source: Optional[str] = None,
        unique_key: Optional[str] = None,
        status: int = 1,
    ) -> None:
        """
        写入单条 DataSet Item

        Args:
            dataset_id: 目标 dataSets.id
            item: 解析后的 Item 数据（input、output、metadata）
            source: 来源，如 excel:path:sheet_name
            unique_key: 业务唯一 key
            status: 1=激活，0=废弃
        """
        await self._repo.create(
            dataset_id=dataset_id,
            input=item.input,
            output=item.output,
            metadata_=item.metadata,
            source=source,
            unique_key=unique_key,
            status=status,
        )
