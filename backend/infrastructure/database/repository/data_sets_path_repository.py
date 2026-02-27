"""
数据集合文件夹仓储实现
支持按 id_path 查询子节点、获取树形结构。
设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
"""
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.data_sets_path import DataSetsPathRecord


class DataSetsPathRepository(BaseRepository[DataSetsPathRecord]):
    """数据集合文件夹仓储类"""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DataSetsPathRecord)

    async def get_children_by_path(self, id_path: Optional[str]) -> List[DataSetsPathRecord]:
        """
        按上级路径查询子节点。
        根节点：id_path 为 None 或空字符串。
        """
        if id_path is None or (isinstance(id_path, str) and id_path.strip() == ""):
            stmt = select(DataSetsPathRecord).where(
                (DataSetsPathRecord.id_path.is_(None)) | (DataSetsPathRecord.id_path == "")
            )
        else:
            stmt = select(DataSetsPathRecord).where(DataSetsPathRecord.id_path == id_path)
        stmt = stmt.order_by(DataSetsPathRecord.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_tree(self) -> List[dict]:
        """
        获取完整树形结构（递归构建）。
        返回格式：[{"id", "id_path", "name", "description", "metadata_", "children": [...]}]
        """
        async def build_node(id_path: Optional[str]) -> List[dict]:
            children = await self.get_children_by_path(id_path)
            nodes = []
            for c in children:
                node = {
                    "id": c.id,
                    "id_path": c.id_path,
                    "name": c.name,
                    "description": c.description,
                    "metadata": c.metadata_,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                    "children": await build_node(c.id),
                }
                nodes.append(node)
            return nodes

        return await build_node(None)
