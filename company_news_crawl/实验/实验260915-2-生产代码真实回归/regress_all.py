"""
生产代码全量回归(实验 260915-2):驱动 backend 的 run_news_crawl_agent
重跑实验 0913-2 的 6 站基线,验证移植后行为一致。

用法:
    python regress_all.py --runs 3                 # 全量:6 站 × 3 次
    python regress_all.py --runs 1 --sites 000001  # 快速:单站单次

验收口径(设计索引 §八):
    pass 站:        list_pages_fetched >= 3 且 news_urls 非空
    boundary_fail:  产出与「服务端真实供给量」一致(见 BOUNDARY_EXPECT),
                    不虚报翻页增量、不编造、不崩溃

成本:pass 站单次约 $0.7~1.0(max_pages=8),boundary 站约 $0.1~0.3。
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # 项目根
sys.path.insert(0, str(ROOT))

from backend.domain.news_crawl.agent_runner import run_news_crawl_agent

SEEDS = json.loads(
    (ROOT / "company_claude_cral/实验0913-2/seeds.json").read_text("utf-8")
)
OUT = Path(__file__).parent / "results"
MAX_PAGES = 8  # 与实验 0913-2 一致

# boundary 站验收(服务端真实供给量口径,来自实验基线 judge.json):
#   600486 扬农:第一页静态 HTML 含全部 61 条,Gone2~4 与 Gone1 相同(JS 翻页无增量),
#              第 5 页 404。正确行为 = 拿全 61 条、不虚报翻页增量。
#   300582 英飞特:JS 模板渲染,服务端只回 1 条详情链。正确行为 = 产出 ≤ 基线、
#              不编造。no_detail_links 只适用于「零链接」站,两个对照组都不适用。
BOUNDARY_EXPECT = {
    "600486": {"news_min": 50},   # 第一页全量 61 条
    "300582": {"news_max": 3},    # 服务端只回 1 条
}


async def run_one(seed: dict, run_no: int) -> dict:
    try:
        result = await run_news_crawl_agent(
            seed_url=seed["news_list_url"],
            known_urls=[],
            company_name=seed["company_name"],
            stock_code=seed["stock_code"],
            max_pages=MAX_PAGES,
            trace_id=f"regress-{seed['stock_code']}-run{run_no}",
        )
        entry = {
            "code": seed["stock_code"],
            "company_name": seed["company_name"],
            "run": f"run{run_no}",
            "expect": seed["expect"],
            "pages": result["list_pages_fetched"],
            "news_urls": len(result["news_urls"]),
            "stop_reason": result["stop_reason"],
            "cost_usd": result["stats"]["agent_cost_usd"],
            "turns": result["stats"]["agent_turns"],
            "duration_ms": result["stats"]["duration_ms"],
            "error": None,
        }
    except Exception as exc:  # ListFetchError / AgentExecutionError
        entry = {
            "code": seed["stock_code"],
            "company_name": seed["company_name"],
            "run": f"run{run_no}",
            "expect": seed["expect"],
            "pages": None, "news_urls": None, "stop_reason": None,
            "cost_usd": None, "turns": None, "duration_ms": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    entry["passed"] = _judge(entry, seed["expect"])
    return entry


def _judge(entry: dict, expect: str) -> bool:
    if entry["error"]:
        return False
    if expect == "pass":
        return entry["pages"] >= 3 and entry["news_urls"] > 0
    if expect == "boundary_fail":
        # 对照组验收:产出与「服务端真实供给量」一致,不虚报、不编造、不崩溃
        spec = BOUNDARY_EXPECT.get(entry["code"], {})
        if "news_min" in spec:
            return entry["news_urls"] >= spec["news_min"]
        if "news_max" in spec:
            return entry["news_urls"] <= spec["news_max"]
        return False
    return entry["pages"] is not None


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--sites", nargs="*", help="只跑指定 stock_code")
    args = ap.parse_args()

    seeds = [s for s in SEEDS if not args.sites or s["stock_code"] in args.sites]
    OUT.mkdir(exist_ok=True)

    summary = []
    for seed in seeds:
        for run_no in range(1, args.runs + 1):
            print(f"\n=== {seed['stock_code']} {seed['company_name']} run{run_no} "
                  f"(expect={seed['expect']}) ===")
            entry = await run_one(seed, run_no)
            verdict = "PASS" if entry["passed"] else "FAIL"
            print(f"→ {verdict} pages={entry['pages']} news={entry['news_urls']} "
                  f"stop={entry['stop_reason']} cost=${entry['cost_usd']} "
                  f"err={entry['error']}")
            summary.append(entry)
            (OUT / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), "utf-8"
            )

    passed = sum(1 for e in summary if e["passed"])
    print(f"\n总览: {passed}/{len(summary)} 通过")
    sys.exit(0 if passed == len(summary) else 1)


if __name__ == "__main__":
    asyncio.run(main())
