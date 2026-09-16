"""
Agent 兜底：规则版抓不到正文时，让 Agent 抓详情页 + 抽取正文（每 URL 最多一次）。

设计文档：exhibition `projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md`
          §3.1-2（Agent 兜底，仅规则失败时，每 URL 最多一次）
          §8-5（成本风险：按 URL 计费，单篇约 $0.2~0.5，需日配额 + 熔断）

复用关系
    - SDK 运行时 / MCP 工具工厂：`claude_agent_sdk`（与 `news_crawl` 同源）
    - 凭证组装：`news_crawl.agent_runner.build_sdk_env()`
    - HTTP 头 / URL 规整 / 日期规整：`news_crawl.crawl_tools` 的公开函数与常量
    - 正文抽取：`company_news_crawl` 的 `ContentExtractor`（与规则版同一份实现）

与 news_crawl 的差别（**不要照搬列表页那套工具**）
    news_crawl 的工具是「列表页发现入口 URL」，明令禁止打开详情页；
    本模块的工具反过来：只服务**一个已知详情页 URL**，目标是把正文抠出来。

三道成本闸门（硬约束，见 `ai_docs/26091605-Agent兜底闸门改造设计.md`）
    1. 开关：`NEWS_CONTENT_AGENT_FALLBACK_ENABLED`
    2. 日配额：`NEWS_CONTENT_AGENT_DAILY_QUOTA`（表 `radar_news_agent_guard` 原子扣减，多实例共享）
    3. 熔断：仅 **system** 连续失败达阈 → 当日全局闭闸；
       内容失败按 `source_url_id` 跳过（不打穿其它信息源）
    另有墙钟超时 `NEWS_CONTENT_AGENT_TIMEOUT_SECONDS` 兜底（CLI 子进程卡死不拖垮 worker）。

⚠️ 闸门状态落库；多实例共享同一配额与熔断位。DDL 见 `scripts/sql/18_radar_news_agent_guard.sql`。
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional
from urllib.parse import urljoin

import httpx
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, create_sdk_mcp_server, tool
from claude_agent_sdk.types import ResultMessage

from backend.app.config import settings
from backend.domain.news_crawl.agent_runner import build_sdk_env
from backend.domain.news_crawl.crawl_tools import USER_AGENT, normalize_date, normalize_url
from backend.domain.news_content.agent_guard_store import (
    AgentGuardStore,
    MysqlAgentGuardStore,
    today_stat_date,
)
from backend.domain.news_content.rate_limiter import SiteRateLimiter
from company_news_crawl.adapters.content_extractor import ContentExtractor, ExtractedArticle

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 25.0
# 单次工具返回给模型阅读的正文上限（防止超长页面把上下文打爆）
_TOOL_TEXT_MAX_CHARS = 8000
# 反幻觉校验时用于比对的正文前缀长度
_VERIFY_PREFIX_CHARS = 120

FailureKind = Literal["content", "system"]

SYSTEM_PROMPT = """
你是企业官网新闻详情页的正文抽取助手。只做一件事：把给定详情页 URL 的新闻正文抠出来。

硬性约束：
1. 只能用 mcp__detail__* 工具。禁止 Bash / WebFetch / WebSearch / Read / Write / Edit。
2. 只能抓取调用方给出的那个 URL（以及从该页面里发现的**同一篇文章**的分页/打印版链接）。
   禁止扩展到列表页、栏目页、其它文章。
3. 提交的正文必须是【真的从抓到的页面上读到的】，禁止改写、翻译、扩写、编造。
   工具会把它和抓到的页面原文逐字比对，对不上会被拒绝。
4. 正文要完整：去掉导航、页脚、"上一篇/下一篇"、版权声明等非正文内容，
   但不要删掉正文段落本身。不要做摘要。

工作流：
A. fetch_detail_page(url=给定URL)
B. 阅读返回内容：
   - 若已给出可用的 title/published_at/content_text，直接采用（可做最小清理）；
   - 若正文明显缺失（只有标题、或只有一小段），查看返回的"页面可读文本"自行判断
     正文起止，或尝试分页/打印版链接后重新抽取。
C. save_article(article_json=...) 提交最终结果：
   {"url": "...", "title": "...", "published_at": "YYYY-MM-DD 或原文",
    "content_text": "正文全文"}
   没有找到的字段传空字符串。
D. 页面确实打不开或正文确实不存在时，调用 give_up(reason="...") 结束。

判断要点：
- 企业新闻正文一般包含时间、正文段落；"关于我们""组织架构""联系方式"这类不是新闻正文。
- published_at 尽量归一为 YYYY-MM-DD；只有模糊日期（如"近日"）时保留原文。
""".strip()


def _text_result(payload: Any) -> dict[str, Any]:
    """把任意对象包装成 MCP 工具返回（与 news_crawl 同形状）。"""
    text = payload if isinstance(payload, str) else json.dumps(
        payload, ensure_ascii=False, indent=2
    )
    return {"content": [{"type": "text", "text": text}]}


def _normalize_for_verify(text: str) -> str:
    """反幻觉比对用的归一：压掉所有空白。"""
    return re.sub(r"\s+", "", text or "")


def _simplify_html_text(html: str, max_chars: int) -> str:
    """
    把 HTML 压成可读纯文本（供模型自行找正文边界）。

    与列表页的 `simplify_list_html` 不同：这里不做链接清单，只给正文候选文本。
    """
    try:
        from selectolax.parser import HTMLParser

        parser = HTMLParser(html)
        for tag in ("script", "style", "noscript", "nav", "header", "footer", "aside"):
            for node in parser.css(tag):
                node.decompose()
        body = parser.css_first("body") or parser.root
        text = body.text(separator="\n", strip=True) if body is not None else ""
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html or "")
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
    text = text.strip()
    return text[:max_chars]


@dataclass
class FetchedPage:
    """一次工具抓取的页面记录（反幻觉校验的证据）。"""

    requested_url: str
    final_url: str
    http_status: int
    text: str
    article: Optional[ExtractedArticle] = None


@dataclass
class DetailAgentStore:
    """单次兜底请求的内存库（请求间零共享）。"""

    target_url: str
    site_key: str = ""
    pages: list[FetchedPage] = field(default_factory=list)
    submitted: Optional[dict[str, Any]] = None
    give_up_reason: Optional[str] = None
    errors: list[str] = field(default_factory=list)

    def find_page(self, url: str) -> Optional[FetchedPage]:
        """按归一化 URL 找已抓页面。"""
        key = normalize_url(url)
        for page in self.pages:
            if normalize_url(page.final_url) == key or normalize_url(page.requested_url) == key:
                return page
        return None

    def verify_content(self, content_text: str) -> Optional[str]:
        """
        反幻觉校验：提交的正文必须能在某个已抓页面里逐字找到。

        Returns:
            校验通过返回 None；否则返回拒绝原因
        """
        probe = _normalize_for_verify(content_text)
        if not probe:
            return "正文为空"
        head = probe[:_VERIFY_PREFIX_CHARS]
        for page in self.pages:
            page_text = _normalize_for_verify(page.text)
            if not page_text:
                continue
            # 工具已抽取过正文的页面，把抽取结果也算进可比对范围
            if page.article and page.article.content_text:
                page_text += _normalize_for_verify(page.article.content_text)
            if head in page_text:
                return None
        return (
            "提交的正文无法在已抓取页面的原文中找到（疑似改写/编造）。"
            "请只提交原文中真实存在的正文。"
        )


# ---------------------------------------------------------------- 成本闸门

class AgentFallbackGuard:
    """
        Agent 兜底三道闸门：开关 / 日配额（原子） / 系统熔断 + 按源内容跳过。

        权威状态在 `AgentGuardStore`（默认 MySQL）；调用序必须为：
        allow → try_consume_quota → Agent → mark_result。
    """

    def __init__(
        self,
        *,
        enabled: bool,
        daily_quota: int,
        max_consecutive_failures: int,
        max_content_failures_per_site: int = 1,
        store: Optional[AgentGuardStore] = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.daily_quota = max(0, int(daily_quota))
        self.max_consecutive_failures = max(1, int(max_consecutive_failures))
        self.max_content_failures_per_site = max(1, int(max_content_failures_per_site))
        self._store: AgentGuardStore = store or MysqlAgentGuardStore()

    async def allow(self, source_url_id: int) -> tuple[bool, str]:
        """
            只读闸门：开关 / 系统熔断 / 该源内容跳过。不扣配额。

            Args:
                source_url_id: 任务信息源 id；≤0 时跳过按源检查

            Returns:
                (是否允许继续尝试扣配额, 不允许时的原因)
        """
        if not self.enabled:
            return False, "Agent 兜底已关闭（NEWS_CONTENT_AGENT_FALLBACK_ENABLED=false）"

        # 1. 全局系统熔断
        stat = today_stat_date()
        if await self._store.is_system_tripped(stat):
            return False, "Agent 兜底已熔断（连续系统失败），当日不再兜底"

        # 2. 按信息源内容跳过
        sid = int(source_url_id or 0)
        if sid > 0 and await self._store.is_source_skipped(sid, stat):
            return (
                False,
                f"Agent 兜底已跳过该信息源（source_url_id={sid} 内容失败达阈），当日不再兜底",
            )
        return True, ""

    async def try_consume_quota(self) -> tuple[bool, str]:
        """
            原子扣减日配额（唯一扣配额入口）。

            Returns:
                (是否扣成功, 失败原因)；失败时调用方不得再跑 Agent
        """
        ok, used, reason = await self._store.try_consume_quota(
            today_stat_date(), self.daily_quota
        )
        if ok:
            logger.info(
                "Agent 兜底扣配额成功 used=%s/%s", used, self.daily_quota
            )
        return ok, reason

    async def mark_result(
        self,
        *,
        success: bool,
        source_url_id: int,
        failure_kind: Optional[FailureKind] = None,
        content_streak_eligible: bool = False,
    ) -> None:
        """
            根据兜底结果更新系统熔断与按源跳过计数。

            Args:
                success: 是否抽到合格正文
                source_url_id: 信息源 id
                failure_kind: 失败类别；ok=False 且缺失时按 system
                content_streak_eligible: 是否计入按源 content streak（HTTP 200 空正文等）
        """
        stat = today_stat_date()
        sid = int(source_url_id or 0)

        if success:
            # 成功：清零系统 streak，并清零该源 content 计数
            await self._store.mark_system_result(
                stat, success=True, max_streak=self.max_consecutive_failures
            )
            if sid > 0:
                await self._store.mark_content_result(
                    sid,
                    stat,
                    success=True,
                    increment_streak=False,
                    max_streak=self.max_content_failures_per_site,
                )
            return

        kind: FailureKind = failure_kind if failure_kind in ("content", "system") else "system"
        if kind == "system":
            await self._store.mark_system_result(
                stat, success=False, max_streak=self.max_consecutive_failures
            )
            return

        # content：不推系统熔断；按 eligible 决定是否推源跳过
        if sid > 0:
            await self._store.mark_content_result(
                sid,
                stat,
                success=False,
                increment_streak=bool(content_streak_eligible),
                max_streak=self.max_content_failures_per_site,
            )


def _content_streak_eligible_from_store(store: DetailAgentStore, min_chars: int) -> bool:
    """
        是否满足「HTTP 200 + 无可抽正文」——可计入按源 content streak。

        临时 5xx / 连接失败等页面不计入，避免误跳过好源。
    """
    threshold = max(1, int(min_chars))
    for page in store.pages:
        if int(page.http_status or 0) != 200:
            continue
        content_len = len((page.article.content_text if page.article else None) or "")
        readable_len = len((page.text or "").strip())
        if content_len < threshold and readable_len < threshold:
            return True
    return False


# ---------------------------------------------------------------- 工具工厂

def build_detail_server(store: DetailAgentStore, limiter: SiteRateLimiter):
    """
    为一次兜底请求创建 MCP Server（store 由闭包绑定，请求间零共享）。

    工具：
      - fetch_detail_page(url)  抓页面 + 规则抽取，返回可读文本供模型判断
      - save_article(...)       提交最终正文（反幻觉校验后接受）
      - give_up(reason)         明确放弃
    """
    http_timeout = float(getattr(settings, "NEWS_CONTENT_HTTP_TIMEOUT_SECONDS", HTTP_TIMEOUT))

    async def _fetch_html(url: str) -> tuple[Optional[str], str, int, Optional[str]]:
        """GET 页面，跟随重定向，遵守同站最小间隔。"""
        await limiter.acquire(store.site_key or None)
        try:
            async with httpx.AsyncClient(
                timeout=http_timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            ) as client:
                response = await client.get(url)
                final_url = str(response.url)
                if response.status_code != 200:
                    return None, final_url, response.status_code, f"HTTP {response.status_code}"
                return response.text, final_url, response.status_code, None
        except httpx.TimeoutException:
            return None, url, 0, "Timeout"
        except httpx.ConnectError as exc:
            return None, url, 0, f"Connection error: {type(exc).__name__}"
        except Exception as exc:
            return None, url, 0, f"Error: {type(exc).__name__}: {exc}"

    def _same_site(url: str) -> bool:
        """只允许抓同站（防 Agent 顺着外链跑偏，也防跑出成本）。"""
        from urllib.parse import urlparse

        target_host = urlparse(store.target_url).netloc.lower()
        return urlparse(url).netloc.lower() == target_host

    @tool(
        "fetch_detail_page",
        "抓取一个新闻详情页并返回可读内容（含规则抽取结果）。"
        "只允许抓同站链接；不要用它翻列表页或抓别的文章。",
        {"url": str},
    )
    async def fetch_detail_page(args: dict[str, Any]) -> dict[str, Any]:
        """抓取详情页并返回可读文本。"""
        raw_url = str(args.get("url") or "").strip()
        if not raw_url:
            return _text_result({"ok": False, "error": "url 不能为空"})
        url = normalize_url(urljoin(store.target_url, raw_url))
        if not _same_site(url):
            return _text_result({
                "ok": False,
                "error": "只允许抓取与目标详情页同站的链接",
                "target": store.target_url,
            })
        if len(store.pages) >= 4:
            return _text_result({
                "ok": False,
                "error": "抓取页面数已达上限（4），请立即 save_article 或 give_up",
            })

        html, final_url, status, error = await _fetch_html(url)
        if error or not html:
            store.errors.append(f"详情页失败 {url}: {error}")
            return _text_result({"ok": False, "url": url, "final_url": final_url, "error": error})

        readable = _simplify_html_text(html, _TOOL_TEXT_MAX_CHARS)
        article = ContentExtractor.extract_article(
            html, final_url or url,
            summary_max_length=int(settings.NEWS_CONTENT_SUMMARY_MAX_LENGTH),
        )
        store.pages.append(
            FetchedPage(
                requested_url=url, final_url=final_url, http_status=status,
                text=readable, article=article,
            )
        )

        header = (
            f"ok=true\nrequested_url={url}\nfinal_url={final_url}\nhttp_status={status}\n"
            f"pages_fetched={len(store.pages)}\n\n"
        )
        rule_block = (
            "## 规则抽取结果（供参考，可用可不用）\n"
            f"title={article.title or '(未抽到)'}\n"
            f"published_at={article.published_at or '(未抽到)'}\n"
            f"content_len={len(article.content_text or '')}\n"
            f"content_preview={(article.content_text or '')[:600]}\n\n"
        )
        return _text_result(header + rule_block + "## 页面可读文本\n" + readable)

    @tool(
        "save_article",
        "提交最终抽取结果。article_json 为 JSON 字符串，字段："
        "url / title / published_at / content_text。正文必须是页面上真实存在的原文，"
        "工具会与已抓页面逐字比对，实改写或编造会被拒绝。",
        {"article_json": str},
    )
    async def save_article(args: dict[str, Any]) -> dict[str, Any]:
        """接收并校验最终正文。"""
        raw = str(args.get("article_json") or "")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return _text_result({
                "ok": False,
                "error": f"article_json 不是合法 JSON: {exc}",
                "expected": '{"url":"...","title":"...","published_at":"...","content_text":"..."}',
            })
        if not isinstance(parsed, dict):
            return _text_result({"ok": False, "error": "article_json 必须是 JSON 对象"})

        content_text = str(parsed.get("content_text") or "").strip()
        reason = store.verify_content(content_text)
        if reason:
            return _text_result({"ok": False, "error": reason, "content_len": len(content_text)})

        store.submitted = {
            "url": str(parsed.get("url") or store.target_url).strip() or store.target_url,
            "title": str(parsed.get("title") or "").strip(),
            "published_at": normalize_date(str(parsed.get("published_at") or ""))
            or str(parsed.get("published_at") or "").strip(),
            "content_text": content_text,
        }
        return _text_result({
            "ok": True,
            "submitted": True,
            "content_len": len(content_text),
            "note": "结果已提交，可以结束。",
        })

    @tool("give_up", "明确放弃：页面打不开或正文确实不存在。", {"reason": str})
    async def give_up(args: dict[str, Any]) -> dict[str, Any]:
        """记录放弃原因。"""
        store.give_up_reason = str(args.get("reason") or "").strip() or "未说明原因"
        return _text_result({"ok": True, "note": "已记录放弃，可以结束。"})

    return create_sdk_mcp_server(
        name="detail",
        version="1.0.0",
        tools=[fetch_detail_page, save_article, give_up],
    )


# ---------------------------------------------------------------- 入口

@dataclass
class AgentFallbackResult:
    """一次 Agent 兜底的结果。"""

    ok: bool
    article: Optional[ExtractedArticle]
    error: Optional[str]
    trace_id: str
    duration_ms: int
    agent_turns: Optional[int] = None
    agent_cost_usd: Optional[float] = None
    failure_kind: Optional[FailureKind] = None
    content_streak_eligible: bool = False


async def run_detail_fetch_agent(
    *,
    url: str,
    site_key: str = "",
    limiter: SiteRateLimiter,
    trace_id: Optional[str] = None,
) -> AgentFallbackResult:
    """
        对单个详情页跑一次 Agent 兜底抽取（每 URL 只应调用一次）。

        ⚠️ 本函数**不含配额判断** —— 调用方必须先 `allow` + `try_consume_quota`，
        结束后 `mark_result(...)`。

        Args:
            url: 详情页 URL
            site_key: 站点标识（同站限速，通常为 source_url_id 字符串）
            limiter: 进程内共享限速器
            trace_id: 链路追踪 ID（回写 `agent_trace_id`）

        Returns:
            AgentFallbackResult —— 失败时 `error` / `failure_kind` 有值，绝不抛异常给主循环
    """
    started = time.monotonic()
    trace = trace_id or ""
    store = DetailAgentStore(target_url=url, site_key=str(site_key or ""))
    detail_server = build_detail_server(store, limiter)
    sdk_env = build_sdk_env()
    min_chars = int(settings.NEWS_CONTENT_FETCH_MIN_CHARS)

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=sdk_env.get("ANTHROPIC_MODEL") or settings.ANTHROPIC_MODEL,
        env=sdk_env,
        mcp_servers={"detail": detail_server},
        allowed_tools=[
            "mcp__detail__fetch_detail_page",
            "mcp__detail__save_article",
            "mcp__detail__give_up",
        ],
        disallowed_tools=["Bash", "WebFetch", "WebSearch", "Read", "Write", "Edit"],
        permission_mode="bypassPermissions",
        max_turns=min(int(settings.NEWS_CRAWL_MAX_TURNS), 20),
        skills=[],
        setting_sources=[],
    )

    user_prompt = (
        f"请抽取下面这个新闻详情页的正文。\n\n"
        f"详情页 URL：{url}\n"
        f"（只处理这一篇文章；抓取失败或页面没有正文时调用 give_up）"
    )

    result_meta: dict[str, Any] = {}
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(user_prompt)
            async for msg in client.receive_response():
                if isinstance(msg, ResultMessage):
                    result_meta = {
                        "status": msg.subtype,
                        "turns": msg.num_turns,
                        "cost_usd": msg.total_cost_usd,
                        "is_error": msg.is_error,
                    }
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.error("[news-content] 兜底 Agent 执行失败 trace=%s: %s", trace, exc)
        return AgentFallbackResult(
            ok=False,
            article=None,
            error=f"{type(exc).__name__}: {exc}",
            trace_id=trace,
            duration_ms=duration_ms,
            failure_kind="system",
            content_streak_eligible=False,
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    turns = result_meta.get("turns")
    cost = result_meta.get("cost_usd")
    streak_eligible = _content_streak_eligible_from_store(store, min_chars)

    if result_meta.get("is_error"):
        return AgentFallbackResult(
            ok=False, article=None,
            error=f"Agent 返回错误状态: {result_meta.get('status')}",
            trace_id=trace, duration_ms=duration_ms,
            agent_turns=turns, agent_cost_usd=cost,
            failure_kind="system",
            content_streak_eligible=False,
        )

    if not store.submitted:
        detail = store.give_up_reason or (store.errors[-1] if store.errors else "Agent 未提交正文")
        return AgentFallbackResult(
            ok=False, article=None, error=detail,
            trace_id=trace, duration_ms=duration_ms,
            agent_turns=turns, agent_cost_usd=cost,
            failure_kind="content",
            content_streak_eligible=streak_eligible,
        )

    submitted = store.submitted
    content_text = submitted["content_text"]
    if len(content_text.strip()) < min_chars:
        return AgentFallbackResult(
            ok=False, article=None,
            error=f"Agent 提交的正文过短（{len(content_text.strip())} < {min_chars}）",
            trace_id=trace, duration_ms=duration_ms,
            agent_turns=turns, agent_cost_usd=cost,
            failure_kind="content",
            content_streak_eligible=streak_eligible,
        )

    article = ExtractedArticle(
        url=submitted["url"] or url,
        title=submitted["title"] or None,
        published_at=submitted["published_at"] or None,
        content_text=content_text,
        content_summary=ContentExtractor.generate_summary(
            content_text, max_length=int(settings.NEWS_CONTENT_SUMMARY_MAX_LENGTH)
        ),
        content_hash=ContentExtractor.compute_content_hash(content_text),
    )

    logger.info(
        "[news-content] 兜底成功 trace=%s url=%s chars=%d turns=%s cost=%s duration=%dms",
        trace, url, len(content_text), turns, cost, duration_ms,
    )
    return AgentFallbackResult(
        ok=True, article=article, error=None, trace_id=trace,
        duration_ms=duration_ms, agent_turns=turns, agent_cost_usd=cost,
        failure_kind=None,
        content_streak_eligible=False,
    )


__all__ = [
    "AgentFallbackGuard",
    "AgentFallbackResult",
    "DetailAgentStore",
    "FailureKind",
    "build_detail_server",
    "run_detail_fetch_agent",
]
