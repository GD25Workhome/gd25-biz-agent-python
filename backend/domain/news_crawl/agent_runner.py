"""
新闻 URL 抓取 Agent 运行时。

移植自 company_claude_cral/实验0913-2/agent_crawl.py，生产化改造见
华院Agent设计/260914-整体重构/02-gd25侧详细设计.md §4.1。

核心差异：
  1. 纯内存返回，不落盘
  2. 凭证从 settings 组装，不直读 os.environ
  3. 新增 known_urls（提示词命中 + 返回前过滤）
  4. 新增 stop_reason（区分通道问题）
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from typing import Any, Optional

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage
from claude_agent_sdk.types import AssistantMessage, TextBlock, ToolUseBlock

from backend.app.config import settings
from backend.domain.news_crawl.crawl_tools import (
    CrawlStore,
    build_crawl_server,
)
from backend.domain.news_crawl.exceptions import (
    AgentExecutionError,
    ListFetchError,
)
from backend.domain.news_crawl.prompts import SYSTEM_PROMPT, build_user_prompt
from backend.domain.news_crawl.url_norm import normalize_many

logger = logging.getLogger(__name__)

# 传给 CLI 子进程的环境变量白名单
_SDK_ENV_KEYS = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
)


def _sdk_env() -> dict[str, str]:
    """
    组装传给 CLI 子进程的 Anthropic 凭证。

    优先取 settings（项目约定配置过 settings），回退到 os.environ
    以兼容本地开发时直接用 shell 变量的场景。
    """
    env: dict[str, str] = {}
    for key in _SDK_ENV_KEYS:
        value = getattr(settings, key, None) or os.getenv(key)
        if value:
            env[key] = str(value)
    return env


async def check_cli_available() -> bool:
    """
    自检 claude CLI 是否可用。

    SDK 是 CLI 子进程模型，CLI 缺失时只会在运行时才报错，
    因此启动时做一次轻量探测。
    """
    claude_path = shutil.which("claude")
    if not claude_path:
        logger.error("未找到 claude CLI，新闻 URL 抓取不可用")
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            claude_path, "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        version = (stdout or b"").decode("utf-8", errors="replace").strip()
        logger.info("claude CLI 可用: %s (%s)", claude_path, version)
        return proc.returncode == 0
    except Exception as exc:
        logger.error("claude CLI 自检失败: %s", exc)
        return False


def decide_stop_reason(store: CrawlStore, max_pages: int) -> str:
    """
    判定停止原因。

    ⚠️ 判断顺序是关键：先把 no_detail_links 挑出来，
    否则"抓到页面但零链接"的通道故障会被误报成 no_next
    （看起来像正常到末页）。
    """
    # 抓到过列表页，但一条详情链接都没抽到 → 通道问题（可能需 JS 渲染）
    if not store.news_items and store.list_pages:
        return "no_detail_links"
    # 命中调用方提供的已知 URL → 主动停止。
    # pagination_stopped 是抓页时检测的硬停信号；known_hit_count 是
    # record_news_urls 时的统计，二者任一为真都算命中。
    if store.pagination_stopped or store.known_hit_count > 0:
        return "hit_known"
    # 达到页数上限
    if len(store.list_pages) >= max_pages:
        return "max_pages"
    # 正常翻到末页
    return "no_next"


def _block_summary(block: Any) -> Optional[str]:
    """把消息块转成简短日志文本（仅用于日志，不落盘）。"""
    if isinstance(block, TextBlock):
        text = (block.text or "").strip()
        return text[:200] if text else None
    if isinstance(block, ToolUseBlock):
        return f"[tool] {block.name}"
    return None


async def run_news_crawl_agent(
    *,
    seed_url: str,
    known_urls: list[str],
    company_name: str = "",
    stock_code: str = "",
    max_pages: int = 8,
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    对单个站点发起一次独立 Agent 采集（纯内存，不落盘）。

    Args:
        seed_url: 新闻列表入口页 URL
        known_urls: 调用方已抓取的详情页 URL（用于短路与过滤）
        company_name: 企业名称（辅助消歧）
        stock_code: 证券代码（辅助消歧）
        max_pages: 列表页抓取上限
        trace_id: 链路追踪 ID

    Returns:
        {
          "news_urls": [{"url","title","published_at"}, ...],   # 已减去 known_urls
          "list_pages_fetched": int,
          "list_page_urls": [str, ...],
          "stop_reason": str,
          "stats": {...},
        }

    Raises:
        ListFetchError: 列表页全部抓取失败（通道/网络问题）
        AgentExecutionError: Agent 执行失败（SDK 异常 / is_error）
    """
    started = time.monotonic()
    known_norm = normalize_many(known_urls or [])

    store = CrawlStore(
        company_name=company_name,
        stock_code=stock_code,
        seed_url=seed_url,
        max_pages=max_pages,
        known_norm=known_norm,
    )

    crawl_server = build_crawl_server(
        store, request_interval=settings.NEWS_CRAWL_REQUEST_INTERVAL
    )
    sdk_env = _sdk_env()

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=sdk_env.get("ANTHROPIC_MODEL") or settings.ANTHROPIC_MODEL,
        env=sdk_env,
        mcp_servers={"crawl": crawl_server},
        allowed_tools=[
            "mcp__crawl__fetch_list_page",
            "mcp__crawl__record_news_urls",
            "mcp__crawl__get_state",
            "mcp__crawl__save_results",
        ],
        disallowed_tools=["Bash", "WebFetch", "WebSearch", "Read", "Write", "Edit"],
        permission_mode="bypassPermissions",
        max_turns=settings.NEWS_CRAWL_MAX_TURNS,
        skills=[],
        setting_sources=[],
    )

    user_prompt = build_user_prompt(
        seed_url=seed_url,
        known_urls=known_urls or [],
        company_name=company_name,
        stock_code=stock_code,
        max_pages=max_pages,
    )

    result_meta: dict[str, Any] = {}
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(user_prompt)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        summary = _block_summary(block)
                        if summary and not summary.startswith("[tool]"):
                            logger.debug("[news-crawl] %s | %s", trace_id, summary)
                elif isinstance(msg, ResultMessage):
                    result_meta = {
                        "status": msg.subtype,
                        "turns": msg.num_turns,
                        "cost_usd": msg.total_cost_usd,
                        "is_error": msg.is_error,
                    }
    except Exception as exc:
        raise AgentExecutionError(f"{type(exc).__name__}: {exc}") from exc

    duration_ms = int((time.monotonic() - started) * 1000)

    # 列表页全部失败 → 通道/网络问题
    if not store.list_pages:
        detail = "; ".join(store.errors[:3]) or "未抓取到任何列表页"
        raise ListFetchError(detail)

    if result_meta.get("is_error"):
        raise AgentExecutionError(
            f"Agent 返回错误状态: {result_meta.get('status')}"
        )

    stop_reason = decide_stop_reason(store, max_pages)
    new_items = store.new_items()

    logger.info(
        "[news-crawl] done trace=%s pages=%d candidates=%d new=%d known_hit=%d "
        "stop=%s turns=%s cost=%s duration=%dms",
        trace_id, len(store.list_pages), len(store.news_items), len(new_items),
        store.known_hit_count, stop_reason,
        result_meta.get("turns"), result_meta.get("cost_usd"), duration_ms,
    )

    return {
        "news_urls": [
            {
                "url": i.url,
                "title": i.title,
                "published_at": i.published_at,
            }
            for i in new_items
        ],
        "list_pages_fetched": len(store.list_pages),
        "list_page_urls": [
            p.get("final_url") or p.get("requested_url") for p in store.list_pages
        ],
        "stop_reason": stop_reason,
        "stats": {
            "candidate_count": len(store.news_items),
            "known_hit_count": store.known_hit_count,
            "list_page_urls": [
                p.get("final_url") or p.get("requested_url") for p in store.list_pages
            ],
            "agent_turns": result_meta.get("turns"),
            "agent_cost_usd": result_meta.get("cost_usd"),
            "duration_ms": duration_ms,
        },
    }
