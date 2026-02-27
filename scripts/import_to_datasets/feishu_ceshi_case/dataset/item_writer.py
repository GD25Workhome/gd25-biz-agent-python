"""
DataSet Item 写入

将解析后的 DataSetItemData 写入 Langfuse DataSet。
"""
import logging
from typing import Any, Dict, Optional

from langfuse import Langfuse

from scripts.import_to_datasets.feishu_ceshi_case.parsers.base import DataSetItemData

logger = logging.getLogger(__name__)


class DatasetItemWriter:
    """DataSet Item 写入器"""

    def __init__(self, langfuse_client: Langfuse) -> None:
        self._client = langfuse_client

    def write_item(
        self,
        dataset_name: str,
        item: DataSetItemData,
        item_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        写入单条 DataSet Item

        Args:
            dataset_name: DataSet 名称
            item: 解析后的 Item 数据
            item_metadata: Item 级 metadata 覆盖/补充
        """
        meta = dict(item.metadata)
        if item_metadata:
            meta.update(item_metadata)

        self._client.create_dataset_item(
            dataset_name=dataset_name,
            input=item.input,
            expected_output=item.expected_output,
            metadata=meta if meta else None,
        )
