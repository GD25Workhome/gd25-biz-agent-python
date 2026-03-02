"""
基础仓储类
封装通用的数据库操作
设计文档：cursor_docs/022603-数据embedding批次表字段设计.md、022605
"""
from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database.base import Base, generate_ulid

ModelType = TypeVar("ModelType", bound=Base)


def _now() -> datetime:
    """系统当前时间（带时区）。"""
    return datetime.now(timezone.utc)


class BaseRepository(Generic[ModelType]):
    """基础仓储类"""
    
    def __init__(self, session: AsyncSession, model: Type[ModelType]):
        """
        初始化仓储
        
        Args:
            session: 数据库会话
            model: ORM 模型类
        """
        self.session = session
        self.model = model
    
    async def get_by_id(self, id: str) -> Optional[ModelType]:
        """
        根据 ID 查询
        
        Args:
            id: 记录ID
            
        Returns:
            模型实例或None
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[ModelType]:
        """
        查询所有记录
        
        Args:
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            模型实例列表
        """
        result = await self.session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return list(result.scalars().all())
    
    async def create(self, **kwargs) -> ModelType:
        """
        创建记录
        
        Args:
            **kwargs: 模型字段键值对
            
        Returns:
            创建的模型实例
        """
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def create_many(
        self,
        items: List[Dict[str, Any]],
        chunk_size: int = 1000,
    ) -> int:
        """
        批量创建记录：按 chunk_size 分组，每组 add 后执行一次 flush，不 commit。
        设计文档：cursor_docs/030201-Base批量插入与批次任务创建详细技术设计方案.md

        Args:
            items: 每项为可传入 self.model(**kwargs) 的键值对。
            chunk_size: 每多少条为一组执行一次 flush，默认 1000。

        Returns:
            实际插入条数。
        """
        if not items:
            return 0
        total = 0
        for i in range(0, len(items), chunk_size):
            chunk = items[i : i + chunk_size]
            for kwargs in chunk:
                instance = self.model(**kwargs)
                self.session.add(instance)
                total += 1
            await self.session.flush()
        return total

    async def update(self, id: str, **kwargs) -> Optional[ModelType]:
        """
        更新记录
        
        Args:
            id: 记录ID
            **kwargs: 要更新的字段键值对
            
        Returns:
            更新后的模型实例或None
        """
        instance = await self.get_by_id(id)
        if not instance:
            return None
        
        for key, value in kwargs.items():
            if value is not None:  # 只更新非None值
                setattr(instance, key, value)
        
        await self.session.flush()
        return instance
    
    async def delete(self, id: str) -> bool:
        """
        删除记录
        
        Args:
            id: 记录ID
            
        Returns:
            是否删除成功
        """
        instance = await self.get_by_id(id)
        if not instance:
            return False
        
        await self.session.delete(instance)
        await self.session.flush()
        return True


class AuditBaseRepository(BaseRepository[ModelType]):
    """
    带审计字段的仓储基类（路线 B）。
    统一处理 id/version/is_deleted/create_time/update_time；
    仅用于具备上述五列的模型（如 batch_job、batch_task）。
    """

    def _not_deleted_criterion(self):
        """未删除条件，供 get_by_id/get_all 及子类自定义查询复用。"""
        return self.model.is_deleted == False  # noqa: E712

    async def get_by_id(self, id: str) -> Optional[ModelType]:
        """根据 ID 查询（仅未删记录）。"""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.id == id)
            .where(self._not_deleted_criterion())
        )
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[ModelType]:
        """查询所有未删记录。"""
        result = await self.session.execute(
            select(self.model)
            .where(self._not_deleted_criterion())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, **kwargs) -> ModelType:
        """创建记录：未传则补 id、version=0、is_deleted=False、create_time=当前时间。"""
        if "id" not in kwargs:
            kwargs["id"] = generate_ulid()
        if "version" not in kwargs:
            kwargs["version"] = 0
        if "is_deleted" not in kwargs:
            kwargs["is_deleted"] = False
        if "create_time" not in kwargs:
            kwargs["create_time"] = _now()
        return await super().create(**kwargs)

    async def create_many(
        self,
        items: List[Dict[str, Any]],
        chunk_size: int = 1000,
    ) -> int:
        """
        批量创建记录：对每条补全审计字段（id/version/is_deleted/create_time）后按 chunk flush。
        设计文档：cursor_docs/030201-Base批量插入与批次任务创建详细技术设计方案.md
        """
        if not items:
            return 0
        filled: List[Dict[str, Any]] = []
        for raw in items:
            row = dict(raw)
            if "id" not in row:
                row["id"] = generate_ulid()
            if "version" not in row:
                row["version"] = 0
            if "is_deleted" not in row:
                row["is_deleted"] = False
            if "create_time" not in row:
                row["create_time"] = _now()
            filled.append(row)
        return await super().create_many(filled, chunk_size=chunk_size)

    async def update(
        self,
        id: str,
        *,
        extra_where: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Optional[ModelType]:
        """
        更新记录：version+1、update_time=当前时间，再写回。

        当 extra_where 为 None 时：先 get_by_id，再在内存中设置 version+1、update_time 与 kwargs 后 flush（原行为）。
        当 extra_where 非空时：执行单条 UPDATE，WHERE id=? AND extra_where 中各条件，SET version=version+1、update_time、kwargs；
        仅当满足条件的行被更新时返回更新后实例（重新 get_by_id），否则返回 None。用于乐观锁等“仅当满足条件才更新”的场景。
        """
        if extra_where is None:
            instance = await self.get_by_id(id)
            if not instance:
                return None
            kwargs["version"] = getattr(instance, "version", 0) + 1
            kwargs["update_time"] = _now()
            for key, value in kwargs.items():
                if value is not None:
                    setattr(instance, key, value)
            await self.session.flush()
            return instance

        # 条件更新：单条 UPDATE，WHERE id + extra_where，SET version+1、update_time、kwargs
        stmt = (
            update(self.model)
            .where(self.model.id == id)
            .where(self._not_deleted_criterion())
        )
        for key, value in extra_where.items():
            col = getattr(self.model, key, None)
            if col is not None:
                stmt = stmt.where(col == value)
        values = {
            "version": self.model.version + 1,
            "update_time": _now(),
            **kwargs,
        }
        values = {k: v for k, v in values.items() if v is not None}
        stmt = stmt.values(**values)
        result = await self.session.execute(stmt)
        if (result.rowcount or 0) == 0:
            return None
        await self.session.flush()
        return await self.get_by_id(id)

    async def delete(self, id: str) -> bool:
        """软删：将 is_deleted 置为 True。"""
        result = await self.update(id, is_deleted=True)
        return result is not None

