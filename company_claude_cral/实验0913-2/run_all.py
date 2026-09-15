"""
实验0913-2 驱动脚本：每个站 × 每个 run 起一个【独立子进程】。

严格按 我的思路.md："每个网站一次独立的Agent发起"。
本站实现得更严格：连 run 之间也是独立进程 + 独立内存库。

用法：
    python run_all.py                 # 全部 6 站 × 3 次
    python run_all.py --runs 1        # 只跑 1 次（快速验证）
    python run_all.py --sites 000001  # 只跑某站
    python run_all.py --judge-only    # 只对已有结果重新判分
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RESULTS = BASE_DIR / "results"
RUNS_DEFAULT = 3


def load_seeds() -> list[dict]:
    """读取种子。"""
    return json.loads((BASE_DIR / "seeds.json").read_text(encoding="utf-8"))


def run_one(seed: dict, run_idx: int) -> dict:
    """在独立子进程中跑一次 Agent 采集。"""
    code = seed["stock_code"]
    out_dir = RESULTS / code / f"run{run_idx}"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, str(BASE_DIR / "agent_crawl.py"),
           "--code", code,
           "--name", seed["company_name"],
           "--url", seed["news_list_url"],
           "--out", str(out_dir)]
    print(f"\n{'='*70}\n[run] {code} {seed['company_name']} run{run_idx}\n{'='*70}")
    proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)
    log = out_dir / "stdout.log"
    log.write_text((proc.stdout or "") + "\n--- STDERR ---\n" + (proc.stderr or ""),
                   encoding="utf-8")
    print(f"[run] exit={proc.returncode} log={log}")
    if proc.returncode != 0:
        print((proc.stderr or "")[-1500:])
    return {"code": code, "run": run_idx, "exit": proc.returncode}


def judge_one(seed: dict, run_idx: int) -> dict:
    """对一次 run 判分。"""
    import judge as J
    return J.judge_run(seed["stock_code"], RESULTS / seed["stock_code"] / f"run{run_idx}")


def main() -> int:
    """CLI 入口。"""
    ap = argparse.ArgumentParser(description="实验0913-2 驱动")
    ap.add_argument("--runs", type=int, default=RUNS_DEFAULT, help="每站跑几次（默认3）")
    ap.add_argument("--sites", nargs="*", help="只跑指定股票代码")
    ap.add_argument("--judge-only", action="store_true", help="只判分，不跑 Agent")
    args = ap.parse_args()

    seeds = load_seeds()
    if args.sites:
        seeds = [s for s in seeds if s["stock_code"] in args.sites]

    summary: list[dict] = []
    for seed in seeds:
        code = seed["stock_code"]
        for i in range(1, args.runs + 1):
            if not args.judge_only:
                run_one(seed, i)
            verdict = judge_one(seed, i)
            verdict["expect"] = seed.get("expect", "pass")
            verdict["note"] = seed.get("note", "")
            summary.append(verdict)

            flag = "PASS" if verdict["passed"] else "FAIL"
            print(f"[judge] {code} run{i}: {flag}  pages={verdict.get('list_pages_fetched')} "
                  f"later_new={verdict.get('later_page_unique_urls')} "
                  f"({verdict.get('reason')})")
            verdict_path = RESULTS / code / f"run{i}" / "judge.json"
            verdict_path.parent.mkdir(parents=True, exist_ok=True)
            verdict_path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2),
                                    encoding="utf-8")

    # ---------------- 汇总 ----------------
    print(f"\n{'='*70}\n汇总\n{'='*70}")
    by_site: dict[str, list[dict]] = {}
    for v in summary:
        by_site.setdefault(v["code"], []).append(v)

    print(f"{'代码':<8}{'公司':<10}{'通过/次数':<10}{'页数':<16}{'后续新URL':<12}{'预期':<14}判定")
    for code, vs in by_site.items():
        ok = sum(1 for v in vs if v["passed"])
        pages = "/".join(str(v.get("list_pages_fetched")) for v in vs)
        later = "/".join(str(v.get("later_page_unique_urls")) for v in vs)
        exp = vs[0].get("expect", "")
        if exp == "boundary_fail":
            verdict = "符合预期(通道问题)" if ok == 0 else "**超出预期**"
        else:
            verdict = "稳定" if ok == len(vs) else ("部分" if ok else "失败")
        print(f"{code:<8}{vs[0].get('company_name',''):<10}{f'{ok}/{len(vs)}':<10}"
              f"{pages:<16}{later:<12}{exp:<14}{verdict}")

    total_ok = sum(1 for v in summary if v["passed"])
    print(f"\n总通过 run 数: {total_ok}/{len(summary)}")
    costs = [v["cost_usd"] for v in summary if v.get("cost_usd")]
    if costs:
        print(f"成本: 合计 ${sum(costs):.2f}, 均 ${sum(costs)/len(costs):.4f}, "
              f"单次 ${min(costs):.3f}~${max(costs):.3f}")

    (RESULTS / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"详细结果: {RESULTS / 'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
