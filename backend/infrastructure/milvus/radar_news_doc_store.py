"""
雷达新闻知识库 Milvus collection 客户端。

    db:         `exhibition_test`（**是库名**，不是 collection 名）
    collection: `radar_company_news_doc`
    schema:     doc_id(int64, PK) / company_id(int64, partition key)
                title / summary / url / embed_text(varchar) / embedding(float vector, dim=1024)
    index:      HNSW + COSINE（M=16，efConstruction=200；检索 ef=64）

设计文档：exhibition `projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md` §3.2 / §4.3

⚠️ pymilvus 3.x 与 2.4 的三条 API 差异（01 文档 §4.3，实现时踩过，勿按 2.4 写）
    1. **schema 路径的 `create_collection` 不会自动建索引** —— 必须显式
       `create_index` + `load_collection`；`IndexParams` 要从
       `pymilvus.milvus_client` 导入（顶层 `pymilvus` 不导出）；
       `list_indexes` 返回索引名列表而非 dict
    2. `query(count(*))` **不能带 limit**
    3. `drop_collection` 是**异步**的，同名立即重建会导致 load 状态错乱 ——
       生产初始化必须幂等：先 `has_collection` 判断，已存在就**不重建**

⚠️ 生产数据安全：本模块的 `drop()` 只在联调/重建时用，正常链路绝不调用。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, Sequence

from pymilvus import DataType, MilvusClient
from pymilvus.milvus_client import IndexParams

from backend.app.config import settings
from backend.infrastructure.llm.huayuan_embedding_client import DEFAULT_DIM

logger = logging.getLogger(__name__)

# 字段名（与 01 文档 §4.3 表格逐字一致，改动需同步检索侧）
FIELD_DOC_ID = "doc_id"
FIELD_COMPANY_ID = "company_id"
FIELD_TITLE = "title"
FIELD_SUMMARY = "summary"
FIELD_URL = "url"
FIELD_EMBED_TEXT = "embed_text"
FIELD_EMBEDDING = "embedding"

# VARCHAR 长度上限（Milvus 必填）。embed_text = title + 正文前 2000 字，
# 取 8192 留足余量（中文字符按 UTF-8 多字节计算也不会溢出）。
MAX_LEN_TITLE = 512
MAX_LEN_SUMMARY = 1024
MAX_LEN_URL = 1024
MAX_LEN_EMBED_TEXT = 8192

# HNSW 参数：文档量级小，不用 AUTOINDEX，显式控制
HNSW_M = 16
HNSW_EF_CONSTRUCTION = 200
SEARCH_EF = 64


class MilvusUnavailableError(RuntimeError):
    """Milvus 未配置或不可用（写链路应据此把 embed_status 置 2）。"""


def _truncate(value: Optional[str], limit: int) -> str:
    """按 VARCHAR 上限截断（Milvus 超长会直接报错）。"""
    if value is None:
        return ""
    text = str(value)
    return text if len(text) <= limit else text[:limit]


class RadarNewsDocStore:
    """
    新闻知识库 collection 的读写封装（同步实现）。

    ⚠️ pymilvus `MilvusClient` 是同步的。worker 是 asyncio 进程，
    因此本类另提供 `*_async` 包装（`asyncio.to_thread`），worker 只调异步版。
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

    # ------------------------------------------------------------ 连接
    @property
    def is_configured(self) -> bool:
        """配置齐备才尝试连接（uri + user/password 或 token）。"""
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
                "Milvus 客户端就绪 uri=%s db=%s collection=%s dim=%d",
                self.uri, self.db_name, self.collection, self.dim,
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

    # ------------------------------------------------------------ 初始化（幂等）
    def has_collection(self) -> bool:
        """collection 是否已存在（只读探测）。"""
        return bool(self._get_client().has_collection(self.collection))

    def ensure_collection(self) -> bool:
        """
        幂等初始化 collection：不存在才建，已存在**绝不重建**。

        ⚠️ 差异点 3：`drop_collection` 异步，同名立刻重建会让 load 状态错乱，
        所以生产初始化只能靠 `has_collection` 判断，不要用「先 drop 再 create」。

        建 schema 路径必须**显式** `create_index` + `load_collection`（差异点 1）。

        Returns:
            True 表示本次新建了 collection；False 表示已存在（复用了现有）
        """
        client = self._get_client()
        if client.has_collection(self.collection):
            self._load()
            self._ensured = True
            logger.info("collection 已存在，跳过创建 collection=%s", self.collection)
            return False

        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(FIELD_DOC_ID, DataType.INT64, is_primary=True)
        schema.add_field(FIELD_COMPANY_ID, DataType.INT64, is_partition_key=True)
        schema.add_field(FIELD_TITLE, DataType.VARCHAR, max_length=MAX_LEN_TITLE)
        schema.add_field(FIELD_SUMMARY, DataType.VARCHAR, max_length=MAX_LEN_SUMMARY)
        schema.add_field(FIELD_URL, DataType.VARCHAR, max_length=MAX_LEN_URL)
        schema.add_field(FIELD_EMBED_TEXT, DataType.VARCHAR, max_length=MAX_LEN_EMBED_TEXT)
        schema.add_field(FIELD_EMBEDDING, DataType.FLOAT_VECTOR, dim=self.dim)

        # schema 路径：create_collection 不建索引，index_params 传了也不生效
        client.create_collection(collection_name=self.collection, schema=schema)

        index_params = IndexParams()
        index_params.add_index(
            field_name=FIELD_EMBEDDING,
            index_type="HNSW",
            index_name="hnsw_embedding",
            metric_type="COSINE",
            M=HNSW_M,
            efConstruction=HNSW_EF_CONSTRUCTION,
        )
        client.create_index(collection_name=self.collection, index_params=index_params)
        self._load()
        self._ensured = True
        logger.info(
            "collection 新建完成 collection=%s db=%s dim=%d index=HNSW/COSINE(M=%d,efC=%d)",
            self.collection, self.db_name, self.dim, HNSW_M, HNSW_EF_CONSTRUCTION,
        )
        return True

    def _load(self) -> None:
        """load collection（检索/写入前需要）。"""
        try:
            self._get_client().load_collection(self.collection)
        except Exception as exc:
            # 已 load 时部分版本会抛异常，降级为告警
            logger.warning("load_collection 告警（可能已加载）collection=%s: %s", self.collection, exc)

    # ------------------------------------------------------------ 写入
    def upsert_documents(self, rows: Sequence[dict[str, Any]]) -> int:
        """
        写入/覆盖若干篇文档（主键 = `doc_id` ≡ `radar_company_news_document.id`）。

        用 `upsert` 而非 `insert`：补跑重嵌/正文更新时同一 doc_id 会重复写，
        upsert 保证幂等（与 document 表的 `uk(news_url_id, deleted)` 语义对齐）。

        Args:
            rows: 每项含 doc_id / company_id / title / summary / url / embed_text / embedding

        Returns:
            实际提交条数

        Raises:
            MilvusUnavailableError: 未配置
            ValueError: embedding 维度与 collection 不一致（写进去会被拒）
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
                    f"期望 {self.dim} 实际 {len(vector)}"
                )
            payload.append({
                FIELD_DOC_ID: int(row["doc_id"]),
                FIELD_COMPANY_ID: int(row["company_id"]),
                FIELD_TITLE: _truncate(row.get("title"), MAX_LEN_TITLE),
                FIELD_SUMMARY: _truncate(row.get("summary"), MAX_LEN_SUMMARY),
                FIELD_URL: _truncate(row.get("url"), MAX_LEN_URL),
                FIELD_EMBED_TEXT: _truncate(row.get("embed_text"), MAX_LEN_EMBED_TEXT),
                FIELD_EMBEDDING: [float(x) for x in vector],
            })

        client = self._get_client()
        client.upsert(collection_name=self.collection, data=payload)
        return len(payload)

    def upsert_document(self, **row: Any) -> int:
        """单篇写入（参数同 `upsert_documents` 的单项）。"""
        return self.upsert_documents([row])

    # ------------------------------------------------------------ 检索（使用侧 P3 / 人工验证）
    def search(
        self,
        query_vector: Sequence[float],
        *,
        company_id: Optional[int] = None,
        top_k: int = 10,
        ef: int = SEARCH_EF,
    ) -> list[dict[str, Any]]:
        """
        向量检索（COSINE）。

        Args:
            query_vector: 查询向量（dim 必须与 collection 一致）
            company_id: 公司过滤（partition key，性能关键路径）；None 表示不过滤
            top_k: 返回条数
            ef: HNSW 检索参数（默认 64）

        Returns:
            [{"doc_id","company_id","title","summary","url","score"}, ...]
        """
        self.ensure_collection()
        filter_expr = f"{FIELD_COMPANY_ID} == {int(company_id)}" if company_id is not None else ""
        results = self._get_client().search(
            collection_name=self.collection,
            data=[[float(x) for x in query_vector]],
            filter=filter_expr,
            limit=int(top_k),
            output_fields=[FIELD_DOC_ID, FIELD_COMPANY_ID, FIELD_TITLE, FIELD_SUMMARY, FIELD_URL],
            search_params={"metric_type": "COSINE", "params": {"ef": int(ef)}},
        )
        hits: list[dict[str, Any]] = []
        for hit in (results[0] if results else []):
            entity = hit.get("entity") or {}
            hits.append({
                "doc_id": entity.get(FIELD_DOC_ID),
                "company_id": entity.get(FIELD_COMPANY_ID),
                "title": entity.get(FIELD_TITLE),
                "summary": entity.get(FIELD_SUMMARY),
                "url": entity.get(FIELD_URL),
                "score": hit.get("distance"),
            })
        return hits

    # ------------------------------------------------------------ 维护
    def _count_raw(self) -> int:
        """
        统计实体数（**不触发** ensure/load 等状态变更）。

        ⚠️ 差异点 2：`query(count(*))` **不能带 limit**（带 limit 会报错）。
        """
        rows = self._get_client().query(
            collection_name=self.collection,
            filter="",
            output_fields=["count(*)"],
        )
        if not rows:
            return 0
        return int(list(rows[0].values())[0])

    def count(self) -> int:
        """collection 内实体数（会确保 collection 就绪）。"""
        self.ensure_collection()
        return self._count_raw()

    def delete_by_doc_ids(self, doc_ids: Sequence[int]) -> int:
        """
        按主键删除向量（document 删除时同步删向量）。

        V1 说明：document 软删场景暂不联动（设计文档 §4.3 已标注），
        本方法留给后续硬删/重建使用。
        """
        ids = [int(x) for x in doc_ids]
        if not ids:
            return 0
        self.ensure_collection()
        self._get_client().delete(collection_name=self.collection, ids=ids)
        return len(ids)

    def describe(self) -> dict[str, Any]:
        """
        collection 概况（`--dry-run` 只读自检用）。

        ⚠️ 严格只读：**不调用** `ensure_collection()` —— 那会在 collection 缺失时把它建出来，
        违背 `--dry-run`「只读验证、不写数据」的约束。
        """
        client = self._get_client()
        info: dict[str, Any] = {
            "uri": self.uri,
            "db_name": self.db_name,
            "collection": self.collection,
            "dim": self.dim,
            "exists": bool(client.has_collection(self.collection)),
        }
        if not info["exists"]:
            return info
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
        """
        ⚠️ 危险操作：删除整个 collection。仅联调/重建时手动调用。

        正常链路（`ensure_collection`）**永不**调用本方法 —— 见差异点 3。
        """
        self._get_client().drop_collection(self.collection)
        self._ensured = False
        logger.warning("已删除 collection=%s（危险操作）", self.collection)

    # ------------------------------------------------------------ 异步门面
    # worker 是 asyncio 进程，pymilvus 是同步的 —— 统一丢线程池，别卡事件循环。

    async def ensure_collection_async(self) -> bool:
        """`ensure_collection` 的异步版。"""
        return await asyncio.to_thread(self.ensure_collection)

    async def upsert_document_async(self, **row: Any) -> int:
        """`upsert_document` 的异步版。"""
        return await asyncio.to_thread(self.upsert_document, **row)

    async def search_async(self, query_vector: Sequence[float], **kwargs: Any) -> list[dict[str, Any]]:
        """`search` 的异步版。"""
        return await asyncio.to_thread(self.search, query_vector, **kwargs)

    async def describe_async(self) -> dict[str, Any]:
        """`describe` 的异步版。"""
        return await asyncio.to_thread(self.describe)

    async def close_async(self) -> None:
        """`close` 的异步版。"""
        await asyncio.to_thread(self.close)


_store: Optional[RadarNewsDocStore] = None


def get_milvus_store() -> RadarNewsDocStore:
    """获取 Milvus 客户端单例（进程内共享）。"""
    global _store
    if _store is None:
        _store = RadarNewsDocStore()
    return _store


def reset_milvus_store() -> None:
    """重置单例（测试/重连用）。"""
    global _store
    if _store is not None:
        _store.close()
    _store = None


__all__ = [
    "RadarNewsDocStore",
    "MilvusUnavailableError",
    "get_milvus_store",
    "reset_milvus_store",
    "FIELD_DOC_ID",
    "FIELD_COMPANY_ID",
    "FIELD_TITLE",
    "FIELD_SUMMARY",
    "FIELD_URL",
    "FIELD_EMBED_TEXT",
    "FIELD_EMBEDDING",
]
