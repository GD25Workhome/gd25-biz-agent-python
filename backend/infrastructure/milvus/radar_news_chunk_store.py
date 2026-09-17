"""
雷达新闻知识库 Milvus collection 客户端（V2：一行一 chunk）。

    collection: `radar_company_news_chunk`（默认，见 settings.MILVUS_COLLECTION）
    schema:     chunk_id(varchar, PK) / doc_id / company_id(partition key)
                chunk_index / chunk_count / char_start / char_end
                title / summary / url / embed_text / embedding(dim=1024)
    index:      HNSW + COSINE；doc_id 标量索引（delete-by-doc）

设计文档：ai_docs/26091607-新闻知识库全文切分与召回策略C设计.md §3 / §4.2

⚠️ 若配置仍指向 V1 collection（PK=doc_id、无 chunk_id），ensure/search
   会抛 SchemaMismatchError，避免静默读写错误结构。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, Sequence

from pymilvus import DataType, MilvusClient
from pymilvus.milvus_client import IndexParams

from backend.app.config import settings
from backend.infrastructure.llm.huayuan_embedding_client import DEFAULT_DIM
from backend.infrastructure.milvus.radar_news_doc_store import (
    FIELD_COMPANY_ID,
    FIELD_DOC_ID,
    FIELD_EMBED_TEXT,
    FIELD_EMBEDDING,
    FIELD_SUMMARY,
    FIELD_TITLE,
    FIELD_URL,
    HNSW_EF_CONSTRUCTION,
    HNSW_M,
    MAX_LEN_EMBED_TEXT,
    MAX_LEN_SUMMARY,
    MAX_LEN_TITLE,
    MAX_LEN_URL,
    SEARCH_EF,
    MilvusUnavailableError,
    _truncate,
)

logger = logging.getLogger(__name__)

FIELD_CHUNK_ID = "chunk_id"
FIELD_CHUNK_INDEX = "chunk_index"
FIELD_CHUNK_COUNT = "chunk_count"
FIELD_CHAR_START = "char_start"
FIELD_CHAR_END = "char_end"
FIELD_CONTENT_GRADE = "content_grade"
FIELD_SOURCE_KIND = "source_kind"

MAX_LEN_CHUNK_ID = 64
MAX_LEN_CONTENT_GRADE = 16
MAX_LEN_SOURCE_KIND = 32
DEFAULT_CONTENT_GRADE = "full"
DEFAULT_SOURCE_KIND = "news_html"


class SchemaMismatchError(RuntimeError):
    """Collection 存在但不是 V2 chunk schema（常见原因：仍指向旧 V1 名）。"""


class RadarNewsChunkStore:
    """
        新闻知识库 chunk collection 的读写封装（同步 + 异步门面）。

        主键 = `chunk_id` = `{doc_id}_{chunk_index}`；按文档删除用 `doc_id` 过滤。
    """

    def __init__(
        self,
        *,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[str] = None,
        db_name: Optional[str] = None,
        collection: Optional[str] = None,
        dim: Optional[int] = None,
    ) -> None:
        self.uri = uri or settings.MILVUS_URI or ""
        self.user = user if user is not None else (settings.MILVUS_USER or "")
        self.password = password if password is not None else (settings.MILVUS_PASSWORD or "")
        self.token = token if token is not None else (settings.MILVUS_TOKEN or "")
        self.db_name = db_name or settings.MILVUS_DB_NAME
        self.collection = collection or settings.MILVUS_COLLECTION
        self.dim = int(dim or settings.EMBEDDING_DIM or DEFAULT_DIM)
        self._client: Optional[MilvusClient] = None
        self._ensured = False

    @property
    def is_configured(self) -> bool:
        """配置齐备才尝试连接。"""
        return bool(self.uri and (self.token or (self.user and self.password)))

    def _get_client(self) -> MilvusClient:
        if not self.is_configured:
            raise MilvusUnavailableError(
                "Milvus 未配置：请在 .env 设置 MILVUS_URI 与 MILVUS_USER/MILVUS_PASSWORD"
            )
        if self._client is None:
            kwargs: dict[str, Any] = {"uri": self.uri}
            if self.token:
                kwargs["token"] = self.token
            else:
                kwargs["user"] = self.user
                kwargs["password"] = self.password
            if self.db_name:
                kwargs["db_name"] = self.db_name
            self._client = MilvusClient(**kwargs)
            logger.info(
                "Milvus Chunk 客户端就绪 uri=%s db=%s collection=%s dim=%d",
                self.uri,
                self.db_name,
                self.collection,
                self.dim,
            )
        return self._client

    def close(self) -> None:
        """关闭客户端连接。"""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        self._ensured = False

    def has_collection(self) -> bool:
        """collection 是否已存在。"""
        return bool(self._get_client().has_collection(self.collection))

    def _field_names(self) -> set[str]:
        """读取已有 collection 的字段名集合。"""
        desc = self._get_client().describe_collection(self.collection)
        return {str(f.get("name")) for f in (desc.get("fields") or []) if f.get("name")}

    def _assert_v2_schema(self) -> None:
        """已存在的 collection 必须含 V2 必需字段，否则拒绝继续。"""
        names = self._field_names()
        required = {
            FIELD_CHUNK_ID,
            FIELD_CONTENT_GRADE,
            FIELD_SOURCE_KIND,
        }
        missing = required - names
        if missing:
            raise SchemaMismatchError(
                f"collection={self.collection} 不是 V2 chunk schema（缺少字段 {sorted(missing)}）。"
                f"请运行 scripts/rebuild_radar_milvus_collection.py 重建 collection。"
            )

    def ensure_collection(self) -> bool:
        """
            幂等初始化 V2 collection：不存在才建；已存在则校验 schema 并 load。

            Returns:
                True 表示本次新建；False 表示已存在

            Raises:
                SchemaMismatchError: 已存在但非 V2 schema
        """
        client = self._get_client()
        if client.has_collection(self.collection):
            self._assert_v2_schema()
            self._load()
            self._ensured = True
            logger.info("chunk collection 已存在 collection=%s", self.collection)
            return False

        # 1. 建 schema
        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(
            FIELD_CHUNK_ID, DataType.VARCHAR, max_length=MAX_LEN_CHUNK_ID, is_primary=True
        )
        schema.add_field(FIELD_DOC_ID, DataType.INT64)
        schema.add_field(FIELD_COMPANY_ID, DataType.INT64, is_partition_key=True)
        schema.add_field(FIELD_CHUNK_INDEX, DataType.INT64)
        schema.add_field(FIELD_CHUNK_COUNT, DataType.INT64)
        schema.add_field(FIELD_CHAR_START, DataType.INT64)
        schema.add_field(FIELD_CHAR_END, DataType.INT64)
        schema.add_field(FIELD_TITLE, DataType.VARCHAR, max_length=MAX_LEN_TITLE)
        schema.add_field(FIELD_SUMMARY, DataType.VARCHAR, max_length=MAX_LEN_SUMMARY)
        schema.add_field(FIELD_URL, DataType.VARCHAR, max_length=MAX_LEN_URL)
        schema.add_field(FIELD_EMBED_TEXT, DataType.VARCHAR, max_length=MAX_LEN_EMBED_TEXT)
        schema.add_field(
            FIELD_CONTENT_GRADE, DataType.VARCHAR, max_length=MAX_LEN_CONTENT_GRADE
        )
        schema.add_field(FIELD_SOURCE_KIND, DataType.VARCHAR, max_length=MAX_LEN_SOURCE_KIND)
        schema.add_field(FIELD_EMBEDDING, DataType.FLOAT_VECTOR, dim=self.dim)

        client.create_collection(collection_name=self.collection, schema=schema)

        # 2. 向量索引 + doc_id 标量索引
        index_params = IndexParams()
        index_params.add_index(
            field_name=FIELD_EMBEDDING,
            index_type="HNSW",
            index_name="hnsw_embedding",
            metric_type="COSINE",
            M=HNSW_M,
            efConstruction=HNSW_EF_CONSTRUCTION,
        )
        try:
            index_params.add_index(
                field_name=FIELD_DOC_ID,
                index_type="INVERTED",
                index_name="idx_doc_id",
            )
        except Exception as exc:
            logger.warning("为 doc_id 添加标量索引参数失败（仍可按 filter 删除）: %s", exc)

        client.create_index(collection_name=self.collection, index_params=index_params)
        self._load()
        self._ensured = True
        logger.info(
            "chunk collection 新建完成 collection=%s db=%s dim=%d",
            self.collection,
            self.db_name,
            self.dim,
        )
        return True

    def _load(self) -> None:
        """load collection。"""
        try:
            self._get_client().load_collection(self.collection)
        except Exception as exc:
            logger.warning(
                "load_collection 告警 collection=%s: %s", self.collection, exc
            )

    @staticmethod
    def make_chunk_id(doc_id: int, chunk_index: int) -> str:
        """生成主键 `{doc_id}_{chunk_index}`。"""
        return f"{int(doc_id)}_{int(chunk_index)}"

    def upsert_chunks(self, rows: Sequence[dict[str, Any]]) -> int:
        """
            批量 upsert chunk 行。

            Args:
                rows: 每项含 doc_id / company_id / chunk_index / chunk_count /
                      char_start / char_end / title / summary / url /
                      embed_text / embedding；可选 chunk_id

            Returns:
                写入条数
        """
        if not rows:
            return 0
        self.ensure_collection()

        payload: list[dict[str, Any]] = []
        for row in rows:
            vector = row.get("embedding") or []
            if len(vector) != self.dim:
                raise ValueError(
                    f"embedding 维度不符：doc_id={row.get('doc_id')} "
                    f"chunk_index={row.get('chunk_index')} "
                    f"期望 {self.dim} 实际 {len(vector)}"
                )
            doc_id = int(row["doc_id"])
            chunk_index = int(row["chunk_index"])
            chunk_id = str(row.get("chunk_id") or self.make_chunk_id(doc_id, chunk_index))
            content_grade = str(
                row.get("content_grade") or DEFAULT_CONTENT_GRADE
            ).strip() or DEFAULT_CONTENT_GRADE
            source_kind = str(row.get("source_kind") or DEFAULT_SOURCE_KIND).strip() or (
                DEFAULT_SOURCE_KIND
            )
            payload.append(
                {
                    FIELD_CHUNK_ID: _truncate(chunk_id, MAX_LEN_CHUNK_ID),
                    FIELD_DOC_ID: doc_id,
                    FIELD_COMPANY_ID: int(row["company_id"]),
                    FIELD_CHUNK_INDEX: chunk_index,
                    FIELD_CHUNK_COUNT: int(row.get("chunk_count") or 0),
                    FIELD_CHAR_START: int(row.get("char_start") or 0),
                    FIELD_CHAR_END: int(row.get("char_end") or 0),
                    FIELD_TITLE: _truncate(row.get("title"), MAX_LEN_TITLE),
                    FIELD_SUMMARY: _truncate(row.get("summary"), MAX_LEN_SUMMARY),
                    FIELD_URL: _truncate(row.get("url"), MAX_LEN_URL),
                    FIELD_EMBED_TEXT: _truncate(row.get("embed_text"), MAX_LEN_EMBED_TEXT),
                    FIELD_CONTENT_GRADE: _truncate(content_grade, MAX_LEN_CONTENT_GRADE),
                    FIELD_SOURCE_KIND: _truncate(source_kind, MAX_LEN_SOURCE_KIND),
                    FIELD_EMBEDDING: [float(x) for x in vector],
                }
            )

        self._get_client().upsert(collection_name=self.collection, data=payload)
        return len(payload)

    def delete_by_doc_id(self, doc_id: int) -> None:
        """按 doc_id 过滤删除该文档全部 chunk（正文变短/重嵌前调用）。"""
        self.ensure_collection()
        expr = f"{FIELD_DOC_ID} == {int(doc_id)}"
        self._get_client().delete(collection_name=self.collection, filter=expr)

    def search(
        self,
        query_vector: Sequence[float],
        *,
        company_id: Optional[int] = None,
        content_grade: Optional[str] = None,
        source_kind: Optional[str] = None,
        top_k: int = 10,
        ef: int = SEARCH_EF,
    ) -> list[dict[str, Any]]:
        """
            向量检索（COSINE），返回 chunk 级命中。

            Returns:
                含 chunk_id/doc_id/chunk_index/embed_text/score 等字段的列表
        """
        self.ensure_collection()
        filter_parts: list[str] = []
        if company_id is not None:
            filter_parts.append(f"{FIELD_COMPANY_ID} == {int(company_id)}")
        if content_grade:
            filter_parts.append(
                f'{FIELD_CONTENT_GRADE} == "{str(content_grade).replace(chr(34), "")}"'
            )
        if source_kind:
            filter_parts.append(
                f'{FIELD_SOURCE_KIND} == "{str(source_kind).replace(chr(34), "")}"'
            )
        filter_expr = " and ".join(filter_parts)
        output_fields = [
            FIELD_CHUNK_ID,
            FIELD_DOC_ID,
            FIELD_COMPANY_ID,
            FIELD_CHUNK_INDEX,
            FIELD_CHUNK_COUNT,
            FIELD_CHAR_START,
            FIELD_CHAR_END,
            FIELD_TITLE,
            FIELD_SUMMARY,
            FIELD_URL,
            FIELD_EMBED_TEXT,
            FIELD_CONTENT_GRADE,
            FIELD_SOURCE_KIND,
        ]
        results = self._get_client().search(
            collection_name=self.collection,
            data=[[float(x) for x in query_vector]],
            filter=filter_expr,
            limit=int(top_k),
            output_fields=output_fields,
            search_params={"metric_type": "COSINE", "params": {"ef": int(ef)}},
        )
        hits: list[dict[str, Any]] = []
        for hit in results[0] if results else []:
            entity = hit.get("entity") or {}
            hits.append(
                {
                    "chunk_id": entity.get(FIELD_CHUNK_ID),
                    "doc_id": entity.get(FIELD_DOC_ID),
                    "company_id": entity.get(FIELD_COMPANY_ID),
                    "chunk_index": entity.get(FIELD_CHUNK_INDEX),
                    "chunk_count": entity.get(FIELD_CHUNK_COUNT),
                    "char_start": entity.get(FIELD_CHAR_START),
                    "char_end": entity.get(FIELD_CHAR_END),
                    "title": entity.get(FIELD_TITLE),
                    "summary": entity.get(FIELD_SUMMARY),
                    "url": entity.get(FIELD_URL),
                    "embed_text": entity.get(FIELD_EMBED_TEXT),
                    "content_grade": entity.get(FIELD_CONTENT_GRADE),
                    "source_kind": entity.get(FIELD_SOURCE_KIND),
                    "score": hit.get("distance"),
                }
            )
        return hits

    def rebuild_collection(self, *, drop: bool = True) -> bool:
        """
        删除并重建 V2 chunk collection（联调/ schema 升级用）。

        Args:
            drop: True 时先 drop 再 create；False 时仅 ensure（不删数据）

        Returns:
            True 表示本次新建；False 表示已存在且未 drop
        """
        client = self._get_client()
        if drop and client.has_collection(self.collection):
            client.drop_collection(self.collection)
            self._ensured = False
            logger.warning("已 drop chunk collection=%s，准备重建", self.collection)
        return self.ensure_collection()

    def _count_raw(self) -> int:
        """统计实体数（不带 limit）。"""
        rows = self._get_client().query(
            collection_name=self.collection,
            filter="",
            output_fields=["count(*)"],
        )
        if not rows:
            return 0
        return int(list(rows[0].values())[0])

    def count(self) -> int:
        """collection 内实体数。"""
        self.ensure_collection()
        return self._count_raw()

    def describe(self) -> dict[str, Any]:
        """
            collection 概况（dry-run 只读；不 ensure 创建）。
        """
        client = self._get_client()
        info: dict[str, Any] = {
            "uri": self.uri,
            "db_name": self.db_name,
            "collection": self.collection,
            "dim": self.dim,
            "schema_version": "v2_chunk",
            "exists": bool(client.has_collection(self.collection)),
        }
        if not info["exists"]:
            return info
        try:
            self._assert_v2_schema()
            info["schema_ok"] = True
        except SchemaMismatchError as exc:
            info["schema_ok"] = False
            info["schema_error"] = str(exc)
        desc = client.describe_collection(self.collection)
        info["fields"] = [
            {
                "name": f.get("name"),
                "type": str(f.get("type")),
                "is_primary": f.get("is_primary", False),
                "is_partition_key": f.get("is_partition_key", False),
            }
            for f in (desc.get("fields") or [])
        ]
        try:
            info["row_count"] = self._count_raw()
        except Exception as exc:
            info["row_count_error"] = f"{type(exc).__name__}: {exc}"
        return info

    def drop(self) -> None:
        """⚠️ 危险：删除整个 collection，仅联调用。"""
        self._get_client().drop_collection(self.collection)
        self._ensured = False
        logger.warning("已删除 chunk collection=%s", self.collection)

    async def ensure_collection_async(self) -> bool:
        """ensure_collection 异步版。"""
        return await asyncio.to_thread(self.ensure_collection)

    async def upsert_chunks_async(self, rows: Sequence[dict[str, Any]]) -> int:
        """upsert_chunks 异步版。"""
        return await asyncio.to_thread(self.upsert_chunks, rows)

    async def delete_by_doc_id_async(self, doc_id: int) -> None:
        """delete_by_doc_id 异步版。"""
        await asyncio.to_thread(self.delete_by_doc_id, doc_id)

    async def search_async(
        self, query_vector: Sequence[float], **kwargs: Any
    ) -> list[dict[str, Any]]:
        """search 异步版。"""
        return await asyncio.to_thread(self.search, query_vector, **kwargs)

    async def describe_async(self) -> dict[str, Any]:
        """describe 异步版。"""
        return await asyncio.to_thread(self.describe)

    async def close_async(self) -> None:
        """close 异步版。"""
        await asyncio.to_thread(self.close)


_chunk_store: Optional[RadarNewsChunkStore] = None


def get_milvus_chunk_store() -> RadarNewsChunkStore:
    """获取 V2 Chunk Store 单例（写入与召回共用）。"""
    global _chunk_store
    if _chunk_store is None:
        _chunk_store = RadarNewsChunkStore()
    return _chunk_store


def reset_milvus_chunk_store() -> None:
    """重置单例（测试/改配置后）。"""
    global _chunk_store
    if _chunk_store is not None:
        _chunk_store.close()
    _chunk_store = None


__all__ = [
    "RadarNewsChunkStore",
    "SchemaMismatchError",
    "get_milvus_chunk_store",
    "reset_milvus_chunk_store",
    "FIELD_CHUNK_ID",
    "FIELD_CHUNK_INDEX",
    "FIELD_CHUNK_COUNT",
    "FIELD_CHAR_START",
    "FIELD_CHAR_END",
    "FIELD_CONTENT_GRADE",
    "FIELD_SOURCE_KIND",
]
