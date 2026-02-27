"""
PG 数据库读取器

根据配置从 PostgreSQL 表读取数据，输出为 (logical_name, DataFrame) 的迭代。
设计文档：cursor_docs/020507-gd2502_knowledge_base导入流程技术设计.md
"""
import logging
from typing import Any, Dict, Iterator, Tuple

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.models.knowledge_base import KnowledgeBaseRecord
from backend.pipeline.readers.base import BaseReader

logger = logging.getLogger(__name__)

# 表名到 ORM 模型的映射，用于配置驱动的数据读取
_TABLE_MODEL_MAP = {
    KnowledgeBaseRecord.__tablename__: KnowledgeBaseRecord,
}


def _orm_to_dict(record: Any) -> Dict[str, Any]:
    """将 ORM 记录转为字典，便于构建 DataFrame"""
    row_dict: Dict[str, Any] = {}
    for c in record.__table__.columns:
        val = getattr(record, c.name)
        if hasattr(val, "isoformat") and callable(getattr(val, "isoformat")):
            val = val.isoformat() if val is not None else None
        row_dict[c.name] = val
    return row_dict


class PgReader(BaseReader):
    """
    PG 数据库表读取器。

    需先调用 fetch(session) 异步拉取数据，再通过 iter_sheets() 迭代。
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Args:
            config: 导入配置，需包含 sourcePath.tableName
        """
        self._config = config or {}
        source_path = self._config.get("sourcePath") or {}
        table_name = source_path.get("tableName") or ""
        if not table_name:
            raise ValueError("配置缺少 sourcePath.tableName")

        self._table_name = table_name.strip()
        self._model = _TABLE_MODEL_MAP.get(self._table_name)
        if not self._model:
            raise ValueError(
                f"不支持的表名: {self._table_name}，"
                f"当前支持: {list(_TABLE_MODEL_MAP.keys())}"
            )
        self._df: pd.DataFrame | None = None

    async def fetch(self, session: AsyncSession) -> None:
        """
        异步拉取表数据至内存。

        必须在 iter_sheets() 之前调用。

        Args:
            session: 数据库异步会话
        """
        query = select(self._model)
        result = await session.execute(query)
        rows = result.scalars().all()
        data = [_orm_to_dict(r) for r in rows]
        self._df = pd.DataFrame(data) if data else pd.DataFrame()
        logger.info("PgReader 拉取表 %s 共 %d 行", self._table_name, len(self._df))

    def iter_sheets(self) -> Iterator[Tuple[str, pd.DataFrame]]:
        """
        迭代读取数据，返回 (logical_name, DataFrame)。

        需先调用 fetch(session)，否则抛出 RuntimeError。

        Yields:
            Tuple[str, pd.DataFrame]: 逻辑分区名（"default"）与对应的 DataFrame
        """
        if self._df is None:
            raise RuntimeError("请先调用 fetch(session) 拉取数据")
        yield "default", self._df
