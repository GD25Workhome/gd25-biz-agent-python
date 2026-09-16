"""
单任务处理编排：规则下载 → Agent 兜底一次 → embedding → 写 Milvus → 写 document → 回写 task。

设计文档：exhibition `projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md`
          §3.1（两段式 worker）/ §3.2（写入链）/ §6（端到端流程）

写入顺序（**顺序是设计定死的，不要调换**）
    1. 规则抓取（`content_fetcher`，零 LLM 成本）
    2. 规则失败 → Agent 兜底一次（`agent_fallback`，受日配额/熔断约束）
    3. 拿到正文 → **先落 document 行**（`fetch_status=1`、`embed_status=0`）拿主键
    4. embedding（公司网关，单条）
    5. 写 Milvus（`doc_id` ≡ `document.id`）
    6. 回写 document 的 `embed_status`/`vector_id`
    7. 回写 task（SUCCESS/FAILED + `actual_channel` + `document_id`）

    ⚠️ 第 3 步必须在第 5 步之前：Milvus 主键就是 document.id，
    不先落库拿不到 id。设计文档「先插 Milvus 再写 document」是**逻辑顺序**，
    物理上只能是「插 document（embed_status=0）→ 插 Milvus → 回写 embed_status」。

分步记状态（§3.2，两者互不覆盖）
    下载失败            → task.status=FAILED + `error_message`；document 占位 `fetch_status=2`
    下载成功、向量失败   → task.status=SUCCESS + `embed_status=2`；document `fetch_status=1`、`embed_status=2`
                          （正文已保住，补跑循环只重做向量段）
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from backend.app.config import settings
from backend.domain.news_content import repository as repo
from backend.domain.news_content.agent_fallback import (
    AgentFallbackGuard,
    run_detail_fetch_agent,
)
from backend.domain.news_content.constants import (
    CHANNEL_AGENT,
    CHANNEL_RULE,
    EMBED_STATUS_FAILED,
    EMBED_STATUS_OK,
    EMBED_STATUS_PENDING,
    FETCH_STATUS_OK,
)
from backend.domain.news_content.content_fetcher import fetch_article_by_rule
from backend.domain.news_content.rate_limiter import SiteRateLimiter
from backend.infrastructure.llm.huayuan_embedding_client import HuayuanEmbeddingClient
from backend.infrastructure.milvus.radar_news_doc_store import (
    MilvusUnavailableError,
    RadarNewsDocStore,
)
from backend.domain.news_crawl.url_norm import normalize as normalize_url

logger = logging.getLogger(__name__)


def build_embed_text(
    title: Optional[str],
    content_text: Optional[str],
    max_chars: int,
) -> str:
    """
    组装实际嵌入文本：`title + 正文前 N 字`（V1 不分 chunk，见 §3.2）。

    Args:
        title: 标题
        content_text: 正文
        max_chars: 正文截断长度（默认 2000）

    Returns:
        嵌入文本；标题与正文都为空时返回空串（调用方应判空）
    """
    head = (content_text or "")[: max(0, int(max_chars))]
    title_text = (title or "").strip()
    if title_text and head:
        return f"{title_text}\n{head}"
    return title_text or head


@dataclass
class ProcessOutcome:
    """单任务处理结果（供日志与自检）。"""

    task_id: int
    ok: bool
    channel: Optional[str]
    document_id: Optional[int]
    embed_status: int
    error: Optional[str]
    cost_ms: int


class NewsContentProcessor:
    """
    任务处理器（worker 内单例；内部状态只有限速器与成本闸门）。

    ⚠️ 串行使用：设计是「一条一条处理」（§3.2 worker 内串行），
    本类不做并发控制，由 worker 主循环保证。
    """

    def __init__(
        self,
        *,
        worker_id: str,
        limiter: Optional[SiteRateLimiter] = None,
        guard: Optional[AgentFallbackGuard] = None,
        embedder: Optional[HuayuanEmbeddingClient] = None,
        milvus: Optional[RadarNewsDocStore] = None,
    ) -> None:
        self.worker_id = worker_id
        self.limiter = limiter or SiteRateLimiter(settings.NEWS_CONTENT_SITE_MIN_INTERVAL_SECONDS)
        self.guard = guard or AgentFallbackGuard(
            enabled=settings.NEWS_CONTENT_AGENT_FALLBACK_ENABLED,
            daily_quota=settings.NEWS_CONTENT_AGENT_DAILY_QUOTA,
            max_consecutive_failures=settings.NEWS_CONTENT_AGENT_MAX_CONSECUTIVE_FAILURES,
        )
        self.embedder = embedder or HuayuanEmbeddingClient()
        self.milvus = milvus or RadarNewsDocStore()

    async def aclose(self) -> None:
        """释放外部资源（worker 优雅退出时调用）。"""
        await self.embedder.aclose()
        await self.milvus.close_async()

    # ------------------------------------------------------------ 主流程
    async def process_task(self, task: dict[str, Any]) -> ProcessOutcome:
        """
        处理一条已抢锁的任务（status=RUNNING）。

        ⚠️ 本方法**不抛异常**：任何失败都落成 task 的 FAILED 或 embed_status=2，
        否则任务会一直停在 RUNNING，只能等 30 分钟超时重置。

        Args:
            task: 抢锁返回的 task 行（含 url / source_level / tenant_id 等快照）

        Returns:
            ProcessOutcome
        """
        started = time.monotonic()
        task_id = int(task["id"])
        url = (task.get("url") or "").strip()
        site_key = str(task.get("source_url_id") or "")

        logger.info(
            "[news-content] 开始处理 task_id=%s company_id=%s url=%s source_level=%s",
            task_id, task.get("company_id"), url, task.get("source_level"),
        )

        if not url:
            await self._fail_task(task_id, started, error="任务缺少 url 快照", channel=None)
            return ProcessOutcome(task_id, False, None, None, EMBED_STATUS_PENDING, "任务缺少 url 快照", self._ms(started))

        # ---------- 第 1 段：规则下载 ----------
        channel: Optional[str] = None
        agent_trace_id: Optional[str] = None
        error_message: Optional[str] = None

        rule_result = await fetch_article_by_rule(
            url,
            site_key=site_key,
            limiter=self.limiter,
            min_chars=settings.NEWS_CONTENT_FETCH_MIN_CHARS,
            summary_max_length=settings.NEWS_CONTENT_SUMMARY_MAX_LENGTH,
            timeout=settings.NEWS_CONTENT_HTTP_TIMEOUT_SECONDS,
            max_retries=settings.NEWS_CONTENT_HTTP_MAX_RETRIES,
        )
        article = rule_result.article if rule_result.ok else None
        if article is not None:
            channel = CHANNEL_RULE
            logger.info(
                "[news-content] 规则抓取成功 task_id=%s chars=%d duration=%dms",
                task_id, len(article.content_text or ""), rule_result.duration_ms,
            )
        else:
            error_message = rule_result.error or "规则抓取失败"
            logger.info("[news-content] 规则抓取失败 task_id=%s err=%s", task_id, error_message)

        # ---------- 第 2 段：Agent 兜底（仅规则失败时，每 URL 最多一次） ----------
        if article is None:
            allowed, reason = self.guard.allow()
            if not allowed:
                logger.warning("[news-content] 跳过 Agent 兜底 task_id=%s 原因=%s", task_id, reason)
                error_message = f"{error_message}；Agent 兜底未执行：{reason}"
            else:
                self.guard.mark_used()
                agent_result = await self._run_agent_with_timeout(task, site_key)
                self.guard.mark_result(agent_result.ok)
                agent_trace_id = agent_result.trace_id or None
                if agent_result.ok and agent_result.article is not None:
                    article = agent_result.article
                    channel = CHANNEL_AGENT
                    error_message = None
                    logger.info(
                        "[news-content] Agent 兜底成功 task_id=%s chars=%d cost=%s",
                        task_id, len(article.content_text or ""), agent_result.agent_cost_usd,
                    )
                else:
                    error_message = f"{error_message}；Agent 兜底失败：{agent_result.error}"

        # ---------- 下载彻底失败：task FAILED + document 占位 ----------
        if article is None or not article.content_text:
            return await self._handle_fetch_failure(
                task, started, error_message or "正文抓取失败", channel, agent_trace_id
            )

        # ---------- 第 3 段：正文落库（先拿主键，Milvus 主键 = document.id） ----------
        document_id = await self._write_document(task, article, channel or CHANNEL_RULE)
        if not document_id:
            return await self._handle_fetch_failure(
                task, started, "document 落库失败（未返回主键）", channel, agent_trace_id
            )

        # ---------- 第 4/5/6 段：embedding → Milvus → 回写 document ----------
        embed_status, embed_error = await self._embed_and_store(
            document_id=document_id,
            company_id=int(task.get("company_id") or 0),
            title=article.title,
            content_text=article.content_text,
            url=article.url or url,
        )

        cost_ms = self._ms(started)
        await repo.mark_task_success(
            task_id,
            worker_id=self.worker_id,
            document_id=document_id,
            actual_channel=channel or CHANNEL_RULE,
            title=article.title,
            published_at=article.published_at,
            content_hash=article.content_hash,
            embed_status=embed_status,
            cost_ms=cost_ms,
            agent_trace_id=agent_trace_id,
        )

        logger.info(
            "[news-content] 完成 task_id=%s channel=%s document_id=%s embed_status=%s cost_ms=%d%s",
            task_id, channel, document_id, embed_status, cost_ms,
            f" embed_err={embed_error}" if embed_error else "",
        )
        return ProcessOutcome(task_id, True, channel, document_id, embed_status, embed_error, cost_ms)

    # ------------------------------------------------------------ 分支实现
    async def _run_agent_with_timeout(self, task: dict[str, Any], site_key: str):
        """给 Agent 兜底套墙钟超时（CLI 子进程卡死不能拖垮 worker）。"""
        import asyncio

        from backend.domain.news_content.agent_fallback import AgentFallbackResult

        url = (task.get("url") or "").strip()
        trace_id = f"news-content-{task.get('id')}-{int(time.time())}"
        timeout = float(settings.NEWS_CONTENT_AGENT_TIMEOUT_SECONDS)
        try:
            return await asyncio.wait_for(
                run_detail_fetch_agent(
                    url=url, site_key=site_key, limiter=self.limiter, trace_id=trace_id
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.error("[news-content] Agent 兜底超时 task_id=%s (>%ss)", task.get("id"), timeout)
            return AgentFallbackResult(
                ok=False, article=None, error=f"Agent 兜底超时（>{timeout}s）",
                trace_id=trace_id, duration_ms=int(timeout * 1000),
            )

    async def _write_document(self, task: dict[str, Any], article, channel: str) -> Optional[int]:
        """
        正文落库（`fetch_status=1`、`embed_status=0` 待向量化），返回 document.id。

        `source_level` 取 **task 快照**（不回头读 source_url 表，守住两表边界）。
        """
        doc = {
            "company_id": int(task.get("company_id") or 0),
            "news_url_id": int(task.get("news_url_id") or 0),
            "source_url_id": int(task.get("source_url_id") or 0),
            "title": article.title,
            "url": article.url or task.get("url"),
            "url_norm": normalize_url(article.url or task.get("url") or ""),
            "published_at": article.published_at,
            "content_text": article.content_text,
            "content_summary": article.content_summary,
            "content_hash": article.content_hash,
            "source_type": channel,
            "source_level": (task.get("source_level") or "P0"),
            "fetch_status": FETCH_STATUS_OK,
            "embed_status": EMBED_STATUS_PENDING,
            "extra_json": json.dumps(
                {
                    "title": article.title,
                    "published_at": article.published_at,
                    "agent_trace_id": None,
                },
                ensure_ascii=False,
            ),
            "tenant_id": task.get("tenant_id"),
        }
        try:
            return await repo.upsert_document(doc, self.worker_id)
        except Exception as exc:
            logger.exception("[news-content] document 落库异常 task_id=%s", task.get("id"))
            return None

    async def _embed_and_store(
        self,
        *,
        document_id: int,
        company_id: int,
        title: Optional[str],
        content_text: Optional[str],
        url: str,
    ) -> tuple[int, Optional[str]]:
        """
        向量段：embedding → 写 Milvus → 回写 document。**不抛异常**。

        Returns:
            (embed_status, error_message)；成功为 (1, None)
        """
        embed_text = build_embed_text(
            title, content_text, settings.NEWS_CONTENT_EMBED_TEXT_MAX_CHARS
        )
        if not embed_text.strip():
            await self._mark_embed_failed(document_id, "嵌入文本为空（标题与正文皆空）")
            return EMBED_STATUS_FAILED, "嵌入文本为空"

        try:
            vector = await self.embedder.embed_one(embed_text)
        except Exception as exc:
            message = f"embedding 失败: {type(exc).__name__}: {exc}"
            logger.error("[news-content] %s document_id=%s", message, document_id)
            await self._mark_embed_failed(document_id, message)
            return EMBED_STATUS_FAILED, message

        try:
            # Milvus 主键 = document.id（§4.3 doc_id ≡ radar_company_news_document.id）
            await self.milvus.upsert_document_async(
                doc_id=int(document_id),
                company_id=int(company_id),
                title=title or "",
                summary=build_summary(content_text),
                url=url,
                embed_text=embed_text,
                embedding=vector,
            )
        except MilvusUnavailableError as exc:
            message = f"Milvus 不可用: {exc}"
            logger.error("[news-content] %s document_id=%s", message, document_id)
            await self._mark_embed_failed(document_id, message)
            return EMBED_STATUS_FAILED, message
        except Exception as exc:
            message = f"Milvus 写入失败: {type(exc).__name__}: {exc}"
            logger.exception("[news-content] Milvus 写入异常 document_id=%s", document_id)
            await self._mark_embed_failed(document_id, message)
            return EMBED_STATUS_FAILED, message

        try:
            await repo.mark_document_embed_ok(
                document_id, worker_id=self.worker_id, vector_id=int(document_id)
            )
        except Exception as exc:
            # 向量已进 Milvus，只是状态没回写 —— 补跑会重做一次（upsert 幂等），不致命
            logger.error(
                "[news-content] embed_status 回写失败 document_id=%s: %s", document_id, exc
            )
            return EMBED_STATUS_FAILED, f"状态回写失败: {exc}"
        return EMBED_STATUS_OK, None

    async def _mark_embed_failed(self, document_id: int, message: str) -> None:
        """把向量段失败落到 document（累计尝试次数，供补跑限量）。"""
        try:
            attempts = await repo.mark_document_embed_failed(
                document_id, worker_id=self.worker_id, error_message=message
            )
            logger.warning(
                "[news-content] 向量段失败 document_id=%s attempts=%s msg=%s",
                document_id, attempts, message,
            )
        except Exception:
            logger.exception("[news-content] embed_status=2 回写失败 document_id=%s", document_id)

    async def _handle_fetch_failure(
        self,
        task: dict[str, Any],
        started: float,
        error_message: str,
        channel: Optional[str],
        agent_trace_id: Optional[str],
    ) -> ProcessOutcome:
        """下载彻底失败：写 document 占位（fetch_status=2）+ task FAILED。"""
        task_id = int(task["id"])
        document_id: Optional[int] = None
        try:
            document_id = await repo.mark_document_fetch_failed(
                {
                    "company_id": int(task.get("company_id") or 0),
                    "news_url_id": int(task.get("news_url_id") or 0),
                    "source_url_id": int(task.get("source_url_id") or 0),
                    "url": task.get("url"),
                    "url_norm": normalize_url(task.get("url") or ""),
                    "source_type": channel or CHANNEL_RULE,
                    "source_level": task.get("source_level") or "P0",
                    "extra_json": json.dumps(
                        {"fetch_error": (error_message or "")[:500]}, ensure_ascii=False
                    ),
                    "tenant_id": task.get("tenant_id"),
                },
                self.worker_id,
            )
        except Exception:
            logger.exception("[news-content] fetch 失败占位写入异常 task_id=%s", task_id)

        cost_ms = self._ms(started)
        await repo.mark_task_failed(
            task_id,
            worker_id=self.worker_id,
            error_message=error_message,
            actual_channel=channel,
            cost_ms=cost_ms,
            agent_trace_id=agent_trace_id,
        )
        # task 的 document_id 回填（便于运维台从 task 跳到占位行）
        if document_id:
            try:
                await repo.update_task_document_id(task_id, document_id, self.worker_id)
            except Exception:
                logger.debug("回填 task.document_id 失败 task_id=%s", task_id, exc_info=True)

        logger.warning(
            "[news-content] 任务失败 task_id=%s err=%s cost_ms=%d",
            task_id, error_message, cost_ms,
        )
        return ProcessOutcome(
            task_id, False, channel, document_id, EMBED_STATUS_PENDING, error_message, cost_ms
        )

    async def _fail_task(
        self, task_id: int, started: float, *, error: str, channel: Optional[str]
    ) -> None:
        """直接判失败（前置校验不通过时用）。"""
        await repo.mark_task_failed(
            task_id, worker_id=self.worker_id, error_message=error,
            actual_channel=channel, cost_ms=self._ms(started),
        )

    @staticmethod
    def _ms(started: float) -> int:
        """耗时毫秒。"""
        return int((time.monotonic() - started) * 1000)

    # ------------------------------------------------------------ 补跑循环
    async def backfill_embeddings(self, limit: Optional[int] = None) -> tuple[int, int, int]:
        """
        补跑循环：扫 `embed_status IN (0,2)` 的 document 重做向量段（**不重新下载**）。

        设计文档 §3.2「幂等补跑并入 worker 循环」。
        超过 `NEWS_CONTENT_EMBED_MAX_ATTEMPTS` 次的文档保持 `embed_status=2`（终态，
        不再重试），避免永久失败的文档无限消耗网关配额。

        Args:
            limit: 本轮扫描条数（默认取配置）

        Returns:
            (成功数, 失败数, 跳过数)
        """
        batch = int(limit or settings.NEWS_CONTENT_EMBED_BACKFILL_BATCH_SIZE)
        try:
            rows = await repo.list_documents_for_embed_backfill(
                batch, max_attempts=settings.NEWS_CONTENT_EMBED_MAX_ATTEMPTS
            )
        except Exception:
            logger.exception("[news-content] 补跑扫描失败")
            return 0, 0, 0

        ok = failed = skipped = 0
        for row in rows:
            doc_id = int(row["id"])
            attempts = repo.parse_embed_attempts(row.get("extra_json"))
            if row.get("embed_status") == EMBED_STATUS_FAILED and attempts >= settings.NEWS_CONTENT_EMBED_MAX_ATTEMPTS:
                skipped += 1
                continue

            embed_status, error = await self._embed_and_store(
                document_id=doc_id,
                company_id=int(row.get("company_id") or 0),
                title=row.get("title"),
                content_text=row.get("content_text"),
                url=row.get("url") or "",
            )
            if embed_status == EMBED_STATUS_OK:
                ok += 1
            else:
                failed += 1
                logger.warning("[news-content] 补跑失败 document_id=%s err=%s", doc_id, error)

            # task 表的冗余 embed_status 同步（权威值仍在 document 表）
            try:
                task = await repo.find_task_by_document_id(doc_id)
                if task:
                    await repo.update_task_embed_status(int(task["id"]), embed_status, self.worker_id)
            except Exception:
                logger.debug("同步 task.embed_status 失败 document_id=%s", doc_id, exc_info=True)

        if rows:
            logger.info(
                "[news-content] 补跑完成 scan=%d ok=%d failed=%d skipped=%d",
                len(rows), ok, failed, skipped,
            )
        return ok, failed, skipped


def build_summary(content_text: Optional[str]) -> str:
    """
    document 表用的 200 字摘要（复用 company_news_crawl 的同一份实现）。

    ⚠️ 补跑场景只从库里读正文、没有现成摘要，因此在此现算，
    保证 Milvus 的 `summary` 字段与 document 表口径一致。
    """
    from company_news_crawl.adapters.content_extractor import ContentExtractor

    return ContentExtractor.generate_summary(
        content_text or "", max_length=settings.NEWS_CONTENT_SUMMARY_MAX_LENGTH
    )


__all__ = ["NewsContentProcessor", "ProcessOutcome", "build_embed_text", "build_summary"]
