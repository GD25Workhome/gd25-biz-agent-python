"""
DataSet 创建与 Schema 设置

负责创建 Langfuse DataSet。通过 create_dataset 的 input_schema、expected_output_schema 参数
设置 Schema 校验，Schema 文件路径由 Config 指定。
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from langfuse import Langfuse

from scripts.import_to_datasets.feishu_ceshi_case.config import Config

logger = logging.getLogger(__name__)

# 分页拉取/删除时的每页数量
_CLEAR_PAGE_SIZE = 100


class DatasetCreator:
    """DataSet 创建器"""

    def __init__(self, langfuse_client: Langfuse) -> None:
        self._client = langfuse_client

    def _load_schema(self, path: Path) -> Dict[str, Any]:
        """加载 JSON Schema 文件"""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def create_or_update_dataset(
        self,
        dataset_name: str,
        excel_name: str,
        sheet_name: str,
        parser_type: str,
    ) -> None:
        """
        创建或更新 DataSet

        Args:
            dataset_name: DataSet 完整名称（含路径）
            excel_name: 来源 Excel 文件名（不含扩展名）
            sheet_name: 来源 Sheet 名称
            parser_type: 使用的解析策略类型
        """
        metadata: Dict[str, Any] = {
            "excel_name": excel_name,
            "sheet_name": sheet_name,
            "parser_type": parser_type,
            "script_name": Config.script_name,
            "import_version": Config.import_version,
            "import_time": datetime.now().isoformat(),
        }

        # 加载 Schema 并传入 create_dataset
        try:
            input_schema = self._load_schema(Config.input_schema_path)
            output_schema = self._load_schema(Config.output_schema_path)
            metadata["input_schema_ref"] = input_schema.get("$id", "DataSet-input-schema")
            metadata["output_schema_ref"] = output_schema.get("$id", "DataSet-output-schema")
        except Exception as e:
            logger.warning("加载 Schema 文件失败，metadata 中不包含 schema 引用: %s", e)

        self._client.create_dataset(
            name=dataset_name,
            description=f"从 {excel_name}/{sheet_name} 导入的评估数据",
            metadata=metadata,
            input_schema=input_schema,
            expected_output_schema=output_schema,
        )
        logger.info("已创建/更新 DataSet: %s", dataset_name)

    def clear_dataset_items(self, dataset_name: str) -> int:
        """
        清空 DataSet 中所有 Items（用于重复导入时覆盖而非追加）

        采用「拉取到空页为止」策略，不依赖 total_pages，避免因 API 分页元数据不准确
        导致提前退出、未清空干净的问题。

        Args:
            dataset_name: DataSet 完整名称

        Returns:
            int: 删除的 Item 数量
        """
        api = self._client.api
        deleted = 0
        page = 1
        while True:
            try:
                resp = api.dataset_items.list(
                    dataset_name=dataset_name,
                    page=page,
                    limit=_CLEAR_PAGE_SIZE,
                )
            except Exception as e:
                # DataSet 可能不存在，或 API 报错
                logger.debug("获取 DataSet Items 失败（可能 DataSet 不存在）: %s", e)
                break
            items = getattr(resp, "data", []) or []
            if not items:
                # 没有更多项，清空完成
                break
            for item in items:
                try:
                    item_id = item.id if hasattr(item, "id") else (item.get("id") if isinstance(item, dict) else None)
                    if item_id:
                        api.dataset_items.delete(id=item_id)
                        deleted += 1
                except Exception as e:
                    logger.warning("删除 Item 失败: %s", e)
            # 删除后下一批成为新的第一页，继续请求 page=1，不递增
        if deleted > 0:
            logger.info("已清空 DataSet '%s' 中 %d 条 Item", dataset_name, deleted)
        return deleted
