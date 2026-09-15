"""
known_urls 短路验证(实验 260915-2):验证 L1/L2 两层机制与省钱效果。

流程:
  1. 全量跑一次平安银行(max_pages=8,known_urls=[]),拿真实 URL 列表
  2. 取前 50 条作为 known_urls 再跑一次,预期:
     - stop_reason == hit_known(短路生效)
     - 成本显著低于全量(设计目标 ≈$0.20,全量 ≈$0.73+)
     - 返回值干净:news_urls 与 known_urls 无交集(L2 过滤)

设计文档:02-gd25侧详细设计.md §4.3 / 设计索引 §四.1
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.domain.news_crawl.agent_runner import run_news_crawl_agent
from backend.domain.news_crawl.url_norm import normalize

SEED = "http://bank.pingan.com/bankPingAnCom/about/news"
KNOWN_N = 50


async def main() -> None:
    print("=== 第一步:全量跑(known_urls=[],max_pages=8) ===")
    full = await run_news_crawl_agent(
        seed_url=SEED, known_urls=[], company_name="平安银行",
        stock_code="000001", max_pages=8, trace_id="known-test-full",
    )
    print(f"全量: pages={full['list_pages_fetched']} news={len(full['news_urls'])} "
          f"stop={full['stop_reason']} cost=${full['stats']['agent_cost_usd']:.4f}")

    known = [i["url"] for i in full["news_urls"][:KNOWN_N]]
    print(f"\n=== 第二步:短路跑(known_urls={len(known)} 条) ===")
    short = await run_news_crawl_agent(
        seed_url=SEED, known_urls=known, company_name="平安银行",
        stock_code="000001", max_pages=8, trace_id="known-test-short",
    )
    print(f"短路: pages={short['list_pages_fetched']} news={len(short['news_urls'])} "
          f"stop={short['stop_reason']} cost=${short['stats']['agent_cost_usd']:.4f}")

    # 验收
    known_norm = {normalize(u) for u in known}
    new_norm = {normalize(i["url"]) for i in short["news_urls"]}
    overlap = known_norm & new_norm
    full_cost = full["stats"]["agent_cost_usd"] or 0
    short_cost = short["stats"]["agent_cost_usd"] or 0
    save = (full_cost - short_cost) / full_cost if full_cost else 0

    checks = {
        "stop_reason == hit_known": short["stop_reason"] == "hit_known",
        "返回值与 known_urls 无交集(L2)": not overlap,
        f"成本下降 ≥30%({save:.0%})": save >= 0.30,
    }
    print("\n验收:")
    ok = True
    for name, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
        ok = ok and passed
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
