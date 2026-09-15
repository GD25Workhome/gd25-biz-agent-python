"""
生产代码首次端到端回归(实验 260915-2)。

直接调用 backend/domain/news_crawl/agent_runner.py 的
run_news_crawl_agent —— 这是 P2 移植代码在 SDK 0.2.152 + CLI 2.1.272
下的第一次真实运行(此前 76 个单测全部 stub 掉 runner)。

验证点:
  1. create_sdk_mcp_server + build_crawl_server 在新 SDK 下工作
  2. 完整 Agent 循环跑通,返回结构正确
  3. 平安银行站(实验基线)回归:max_pages=3 应能翻页并产出 news_urls

成本:约 $0.3~0.5(样板站 max_pages=3)
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.domain.news_crawl.agent_runner import run_news_crawl_agent

SEED = "http://bank.pingan.com/bankPingAnCom/about/news"


async def main() -> None:
    result = await run_news_crawl_agent(
        seed_url=SEED,
        known_urls=[],
        company_name="平安银行",
        stock_code="000001",
        max_pages=3,
        trace_id="regress-260915",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 验收口径(设计索引 §八):list_pages_fetched >= 3 且 news_urls 非空
    ok = result["list_pages_fetched"] >= 3 and bool(result["news_urls"])
    print("\n验收:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
