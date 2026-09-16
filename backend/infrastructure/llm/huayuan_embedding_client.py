"""
公司统一 LLM 网关 embedding 客户端（OpenAI 兼容 `/embeddings`）。

设计文档：exhibition `projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md` §3.2
调用样例参照：`scripts/probe_company_embedding.py`（同一端点、同一鉴权头）

⚠️ 与 `backend/infrastructure/llm/embedding_client.py` 的区别
    那个是**豆包 Ark SDK** 的 `doubao-embedding-vision`（医疗线 RAG 在用），
    本模块走的是**公司网关的 OpenAI 兼容端点**（`unidt/embedding-bge-m3`，1024 维）。
    两者 SDK / 端点 / 维度都不同，互不影响，不要合并。

⚠️ 密钥只从 `settings.HUAYUAN_API_KEY` 读，禁止出现在日志/异常文案里。
"""
from __future__ import annotations

import logging
from typing import Optional, Sequence

import httpx

from backend.app.config import settings

logger = logging.getLogger(__name__)

# 两候选模型实测均为 1024 维（01 文档 §3.2），建 collection 前必须一致
DEFAULT_DIM = 1024


class HuayuanEmbeddingError(RuntimeError):
    """公司网关 embedding 调用失败（网络/鉴权/响应结构异常）。"""


class HuayuanEmbeddingClient:
    """
    公司网关 embedding 客户端（异步）。

    生命周期：worker 启动时创建一份、退出时 `aclose()`；
    内部持有 `httpx.AsyncClient`，连接复用。
    """

    def __init__(
        self,
        *,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        dim: Optional[int] = None,
    ) -> None:
        self.endpoint = (endpoint or settings.HUAYUAN_API_URL_embeddings or "").rstrip("/")
        self._api_key = api_key or settings.HUAYUAN_API_KEY or ""
        self.model = model or settings.EMBEDDING_MODEL
        self.timeout = float(timeout or settings.EMBEDDING_TIMEOUT_SECONDS)
        # 观测到的维度；与 Milvus collection 的 dim 必须一致
        self.dim = int(dim or settings.EMBEDDING_DIM or DEFAULT_DIM)
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------ 生命周期
    @property
    def is_available(self) -> bool:
        """端点 + 鉴权 key 齐备才可用。"""
        return bool(self.endpoint and self._api_key)

    def _get_client(self) -> httpx.AsyncClient:
        if not self.is_available:
            raise HuayuanEmbeddingError(
                "公司网关 embedding 未配置：请在 .env 设置 "
                "HUAYUAN_API_URL_embeddings 与 HUAYUAN_API_KEY"
            )
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def aclose(self) -> None:
        """关闭底层 HTTP 客户端（worker 优雅退出时调用）。"""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    # ------------------------------------------------------------ 调用
    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """
        批量嵌入。

        Args:
            texts: 文本列表（空列表直接返回 []，不发请求）

        Returns:
            与入参等长、顺序一致的向量列表

        Raises:
            HuayuanEmbeddingError: 未配置 / HTTP 非 200 / 响应缺字段 / 条数不匹配
        """
        items = [str(t or "") for t in texts]
        if not items:
            return []

        client = self._get_client()
        try:
            response = await client.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.model, "input": items},
            )
        except httpx.TimeoutException as exc:
            raise HuayuanEmbeddingError(
                f"embedding 请求超时（>{self.timeout}s，model={self.model}）"
            ) from exc
        except Exception as exc:
            raise HuayuanEmbeddingError(
                f"embedding 请求异常: {type(exc).__name__}: {exc}"
            ) from exc

        if response.status_code != 200:
            # ⚠️ 只截断响应体，不回显请求头（含 key）
            raise HuayuanEmbeddingError(
                f"embedding HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            payload = response.json()
        except Exception as exc:
            raise HuayuanEmbeddingError(f"embedding 响应非 JSON: {exc}") from exc

        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise HuayuanEmbeddingError("embedding 响应缺少 data 数组")

        first = data[0]
        if isinstance(first, dict) and isinstance(first.get("embedding"), (int, float)):
            # 结构 B（网关新配置，2026-09-15 探测实测）：向量每个分量拆成独立 dict
            #   data = [{"object": "embedding", "embedding": <float>, "index": i}, ...] 共 dim 个
            # 仅支持单条输入（worker 写链路按篇调用），按 index 排序拼回向量
            if len(items) != 1:
                raise HuayuanEmbeddingError(
                    f"embedding 返回分量拆分结构，不支持批量 {len(items)} 条输入"
                )
            rows = sorted(data, key=lambda r: int(r.get("index", 0)))
            vectors: list[list[float]] = [[float(r["embedding"]) for r in rows]]
        elif all(isinstance(x, (int, float)) for x in data[:3]):
            # 结构 C（防御性兼容）：data 直接是向量 float 数组
            if len(items) != 1:
                raise HuayuanEmbeddingError(
                    f"embedding 返回裸向量结构，不支持批量 {len(items)} 条输入"
                )
            vectors = [[float(x) for x in data]]
        else:
            # 结构 A（OpenAI 兼容标准）：data = [{"embedding": [...], "index": i}, ...]
            rows = data
            if len(rows) != len(items):
                raise HuayuanEmbeddingError(
                    f"embedding 返回条数不匹配（期望 {len(items)}，实际 {len(rows)}）"
                )
            # 按 index 排序，确保与入参顺序一致（OpenAI 兼容协议不保证返回顺序）
            try:
                rows = sorted(rows, key=lambda r: int(r.get("index", 0)))
            except Exception:
                pass
            vectors = []
            for row in rows:
                vector = row.get("embedding") if isinstance(row, dict) else None
                if not vector:
                    raise HuayuanEmbeddingError("embedding 返回项缺少 embedding 字段")
                vectors.append([float(x) for x in vector])

        observed = len(vectors[0])
        if observed != self.dim:
            # 只告警不抛错：模型可切换（bge-m3 / qwen3 同为 1024），
            # 真的不一致时写 Milvus 会失败，日志里要能一眼看出原因
            logger.warning(
                "embedding 维度与期望不一致：期望 %d 实际 %d（model=%s）",
                self.dim, observed, self.model,
            )
            self.dim = observed
        return vectors

    async def embed_one(self, text: str) -> list[float]:
        """
        单条嵌入（worker 写链路按篇处理，单条调用即可）。

        Raises:
            HuayuanEmbeddingError: 调用失败或返回空
        """
        vectors = await self.embed_texts([text])
        if not vectors:
            raise HuayuanEmbeddingError("embedding 返回空结果")
        return vectors[0]


__all__ = ["HuayuanEmbeddingClient", "HuayuanEmbeddingError", "DEFAULT_DIM"]
