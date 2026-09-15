"""
实验0913-2 主程序：对【单个站】发起一次独立的 Agent 采集。

用法：
    python agent_crawl.py --code 000001 --name 平安银行 \
        --url "http://bank.pingan.com/bankPingAnCom/about/news" \
        --out results/000001/run1

设计约束（见 实验设计.md §4）：
  - 每个进程只处理一个站、一个 run —— 站间/run 间完全隔离
  - 提示词【不给】任何翻页规律、不给详情页路径特征、不给规则版结果
  - 只用 mcp__crawl__* 工具；禁止 Bash/WebFetch/Read/Write/Edit
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage
from claude_agent_sdk.types import AssistantMessage, TextBlock, ToolUseBlock

from crawl_runtime import (
    BASE_DIR,
    MAX_PAGES,
    build_crawl_server,
    new_store,
)

SYSTEM_PROMPT = """
你是上市公司官网新闻列表采集 Agent。只做一件事：从列表页里找出新闻详情入口 URL。

硬性约束：
1. 只能用 mcp__crawl__* 工具。禁止 Bash / WebFetch / WebSearch / Read / Write / Edit。
2. 禁止打开新闻详情页，禁止抽取正文。列表页上的标题/日期可以记下，仅供核对。
3. 不要把导航、栏目、公告栏、许可证公示、分页控件本身当成新闻入口。
4. 禁止依赖事先给定的翻页 URL、文件名或锚文本模式；后续列表页只能从当前页内容里发现。
5. 必须持续找后续列表页，直到没有后续或达到 max_pages 上限。不要只停在入口页。

工作流：
A. fetch_list_page(当前列表 URL)
B. 阅读链接清单，自行挑选新闻详情入口 {url, title, published_at}
C. record_news_urls(page_url, items_json, next_page_url)；没有后续列表页则 next_page_url 传空字符串
D. 若 pages_remaining > 0 且你找到了后续列表页：对其重复 A-C
E. save_results()

判断要点：
- 新闻详情入口通常是"一条具体的新闻"，有标题（和可能的日期）。
- 列表页/分页控件本身不是新闻入口。
- 同一站点里，列表页 URL 与详情页 URL 可能长得很像，要靠页面上呈现的内容来判断，不要只看路径。
""".strip()

USER_PROMPT_TEMPLATE = """
请采集 {company_name}（{stock_code}）官网新闻中心的新闻详情入口 URL。

入口页：{seed_url}
最多列表页：{max_pages}

要求：
1. 请只根据 fetch_list_page 返回的页面内容，自己找出新闻详情入口 URL，以及是否还有后续列表页。
2. 不要猜测固定路径。
3. 必须尝试翻页：至少抓到 3 个列表页（除非站点确实没有后续页）。
4. 采完后必须 save_results。

最终回复用简短文字说明：入口页是哪个、实际翻了几页、每页各有多少条新闻 URL、后续页是怎么找到的。
详细清单以工具写出的 Markdown 为准。
""".strip()


def _sdk_env() -> dict[str, str]:
    """把当前可用的 Anthropic 兼容凭证传给 CLI 子进程。"""
    env: dict[str, str] = {}
    for key in (
        "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
    ):
        value = os.getenv(key)
        if value:
            env[key] = value
    return env


def _block_text(block: Any) -> str:
    """把 SDK 消息块转成可打印文本。"""
    if isinstance(block, TextBlock):
        return block.text
    if isinstance(block, ToolUseBlock):
        return f"[tool_use] {block.name} {json.dumps(block.input, ensure_ascii=False)[:400]}"
    return str(block)


async def run_agent(code: str, name: str, seed_url: str, out_dir: Path) -> dict[str, Any]:
    """对单个站发起一次独立 Agent 采集。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = out_dir / "snapshots"

    # 本次 run 独立的内存库与 MCP server（站间/run 间零共享）
    store = new_store(code, name, seed_url)
    crawl_server = build_crawl_server(store, snapshot_dir)
    sdk_env = _sdk_env()

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=sdk_env.get("ANTHROPIC_MODEL") or os.getenv("ANTHROPIC_MODEL"),
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
        cwd=str(BASE_DIR),
        max_turns=50,
        skills=[],
        setting_sources=[],
    )

    user_prompt = USER_PROMPT_TEMPLATE.format(
        company_name=name, stock_code=code, seed_url=seed_url, max_pages=MAX_PAGES,
    )

    traces: list[str] = []
    result_meta: dict[str, Any] = {}
    async with ClaudeSDKClient(options=options) as client:
        await client.query(user_prompt)
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    line = _block_text(block)
                    print(line)
                    traces.append(line)
            elif isinstance(msg, ResultMessage):
                summary = (f"[result] status={msg.subtype} turns={msg.num_turns} "
                           f"cost={msg.total_cost_usd} is_error={msg.is_error}")
                print(summary)
                traces.append(summary)
                result_meta = {
                    "status": msg.subtype,
                    "turns": msg.num_turns,
                    "cost_usd": msg.total_cost_usd,
                    "is_error": msg.is_error,
                }
                if msg.result:
                    traces.append(str(msg.result))
            else:
                print(msg)
                traces.append(str(msg))

    (out_dir / "agent_trace.txt").write_text("\n".join(traces), encoding="utf-8")

    run_meta = {
        "stock_code": code,
        "company_name": name,
        "seed_url": seed_url,
        "list_pages_fetched": len(store.list_pages),
        "news_url_count": len(store.news_urls()),
        "errors": store.errors,
        "agent": result_meta,
    }
    (out_dir / "run_meta.json").write_text(
        json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_meta


def main() -> int:
    """命令行入口。"""
    p = argparse.ArgumentParser(description="实验0913-2：单站单次 Agent 采集")
    p.add_argument("--code", required=True, help="股票代码")
    p.add_argument("--name", required=True, help="公司名称")
    p.add_argument("--url", required=True, help="新闻列表入口页")
    p.add_argument("--out", required=True, help="输出目录")
    args = p.parse_args()

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = BASE_DIR / out_dir

    print(f"=== 实验0913-2 单站采集 ===")
    print(f"company={args.name} {args.code}")
    print(f"seed_url={args.url}")
    print(f"out_dir={out_dir}")
    print(f"ANTHROPIC_BASE_URL={os.environ.get('ANTHROPIC_BASE_URL')}")
    print(f"ANTHROPIC_MODEL={os.environ.get('ANTHROPIC_MODEL')}")
    print()

    meta = asyncio.run(run_agent(args.code, args.name, args.url, out_dir))
    print("\n=== run_meta ===")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0 if not meta.get("agent", {}).get("is_error") else 1


if __name__ == "__main__":
    sys.exit(main())
