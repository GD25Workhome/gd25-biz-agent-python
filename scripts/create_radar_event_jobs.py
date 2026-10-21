#!/usr/bin/env python
"""批量创建「展厅需求任务」（radar_event_job）——目标集 = 展厅需求事件已评分的公司。

目标集（脚本内置查询，现算不写死）：
    radar_event.deleted = 0 AND total_score IS NOT NULL → distinct company_id
    （按最高分降序；当前库约 331 家）

创建方式：
    调用 Java admin-api `POST /admin-api/radar/event-job/create-batch`
    （≤100 家/次，脚本自动分批；只落 radar_event_job(status=0)，由 Python 调度器认领）。
    走 Java 会经过「同公司仅 1 个 active job」闸，并对未监测企业按需一键入池。

安全默认：
    默认 dry-run（只查目标集 + 打印分批计划，不建任务）。确认后用 `--apply` 真正创建。

用法（仓库根目录）：
    python scripts/create_radar_event_jobs.py                    # dry-run
    python scripts/create_radar_event_jobs.py --limit 5          # dry-run：只取前 5 家
    python scripts/create_radar_event_jobs.py --apply --token <Bearer>
    RADAR_ADMIN_TOKEN=<Bearer> python scripts/create_radar_event_jobs.py --apply

token 取法：
    管理后台登录后的 `oauth2_access_token`（需具备 `radar:event-job:create` 权限）。
    本机可从 Redis（application-local.yaml 的 host + db 5）取现成的 `oauth2_access_token:*`
    直接复用；登录接口对用户名/密码走 SM2，勿用 curl 传明文。

跑前提醒（重跑设计 `01-重跑总体设计.md` §7.1）：
    worker 在跑 + `DEEPSEEK_SEARCH_KEY` 已配；若做对照评测，先完成基线快照（`02-评测详细设计.md` §2）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=False)

from backend.app.config import settings  # noqa: E402

CREATE_BATCH_PATH = "/admin-api/radar/event-job/create-batch"

# 一次 create-batch 的企业数上限（对齐 Java RadarEventJobBatchCreateReqVO @Size(max=100)）
MAX_BATCH_SIZE = 100

_TARGET_SQL = """
SELECT e.company_id AS company_id,
       MAX(e.total_score) AS best_score,
       MAX(c.name) AS name,
       MAX(c.stock_code) AS stock_code
FROM radar_event e
LEFT JOIN radar_company c ON c.id = e.company_id AND c.deleted = b'0'
WHERE e.deleted = b'0' AND e.total_score IS NOT NULL
GROUP BY e.company_id
ORDER BY best_score DESC, e.company_id ASC
"""


def connect() -> pymysql.connections.Connection:
    """
        按 settings 连 exhibition MySQL。

        Returns:
            关闭自动提交的连接（DictCursor）
    """
    cfg = settings.require_exhibition_mysql()
    return pymysql.connect(
        host=cfg["host"], port=int(cfg["port"]), user=cfg["user"],
        password=cfg["password"], database=cfg["database"],
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def fetch_targets(conn: pymysql.connections.Connection, limit: int = 0) -> List[Dict[str, Any]]:
    """
        取「展厅需求事件已评分」的企业清单（按最高分降序）。

        Args:
            conn: 数据库连接
            limit: >0 时只取前 N 家（冒烟测试用）

        Returns:
            每行含 company_id / best_score / name / stock_code
    """
    sql = _TARGET_SQL
    params: List[Any] = []
    if int(limit) > 0:
        sql += " LIMIT %s"
        params.append(int(limit))
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall() or [])


def chunked(seq: Sequence[Any], size: int) -> List[List[Any]]:
    """
        把序列按 size 切块。

        Args:
            seq: 待切分的序列
            size: 每块最大长度（至少 1）

        Returns:
            切好的块列表
    """
    size = max(1, int(size))
    return [list(seq[i:i + size]) for i in range(0, len(seq), size)]


def build_body(company_ids: Sequence[int], args: argparse.Namespace) -> Dict[str, Any]:
    """
        组装 create-batch 请求体（对齐 RadarEventJobBatchCreateReqVO）。

        Args:
            company_ids: 本批企业编号
            args: 命令行参数

        Returns:
            请求体 dict
    """
    # 1. 企业编号（必填）
    body: Dict[str, Any] = {"companyIds": [int(x) for x in company_ids]}
    # 2. 未监测是否一键入池（默认 true，与 Java 默认一致）
    body["applyMonitorIfNeeded"] = not args.no_monitor
    # 3. 一键入池是否 force（非 CORE/KEY 也可入）
    if args.force_monitor:
        body["forceMonitor"] = True
    # 4. 可选提示时间窗（缺省不传 = NULL，时效口径见 D9 滚动窗口）
    if args.time_from:
        body["timeFrom"] = args.time_from
    if args.time_to:
        body["timeTo"] = args.time_to
    return body


def post_batch(base_url: str, token: str, body: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    """
        调用 Java create-batch，返回解包后的 data。

        Args:
            base_url: Java 服务根地址
            token: Bearer token
            body: 请求体
            timeout: 超时秒数

        Returns:
            RadarBatchJobResultRespVO 形状的 dict

        Raises:
            RuntimeError: 网络错误、HTTP 非 2xx、或 CommonResult code 非成功
    """
    url = base_url.rstrip("/") + CREATE_BATCH_PATH
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=raw, method="POST")
    request.add_header("Content-Type", "application/json; charset=utf-8")
    request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as ex:
        detail = ex.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {ex.code} {url} {detail}") from ex
    except (urllib.error.URLError, TimeoutError, OSError) as ex:
        raise RuntimeError(f"请求失败 {url} {ex}") from ex

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as ex:
        raise RuntimeError(f"响应不是 JSON {url}: {text[:200]}") from ex
    if not isinstance(payload, dict):
        raise RuntimeError(f"响应不是对象 {url}: {text[:200]}")
    code = payload.get("code")
    if code not in (0, 200, "0", "200"):
        raise RuntimeError(f"Java 业务错误 code={code} msg={payload.get('msg')}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"Java data 非对象 {url}: {text[:200]}")
    return data


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    ap = argparse.ArgumentParser(
        description="为「展厅需求事件已评分」的企业批量创建 radar_event_job（走 Java create-batch）"
    )
    ap.add_argument("--apply", action="store_true",
                    help="真正调用 Java 创建任务（默认只 dry-run，不建任务）")
    ap.add_argument("--base-url", default=os.getenv("RADAR_SCORE_JAVA_BASE_URL", "").strip(),
                    help="Java 服务根地址（默认取 RADAR_SCORE_JAVA_BASE_URL）")
    ap.add_argument("--token", default=os.getenv("RADAR_ADMIN_TOKEN", "").strip(),
                    help="管理后台 Bearer token（默认取 RADAR_ADMIN_TOKEN）")
    ap.add_argument("--chunk-size", type=int, default=MAX_BATCH_SIZE,
                    help=f"每批企业数，上限 {MAX_BATCH_SIZE}（默认 {MAX_BATCH_SIZE}）")
    ap.add_argument("--limit", type=int, default=0,
                    help="只取前 N 家企业（0=全部；用于冒烟测试）")
    ap.add_argument("--time-from", default=None, help="提示时间窗起 YYYY-MM-DD（缺省不传）")
    ap.add_argument("--time-to", default=None, help="提示时间窗止 YYYY-MM-DD（缺省不传）")
    ap.add_argument("--no-monitor", action="store_true",
                    help="applyMonitorIfNeeded=false：未监测企业不自动一键入池")
    ap.add_argument("--force-monitor", action="store_true",
                    help="一键入池 force=true：非 CORE/KEY 也可入池")
    ap.add_argument("--timeout", type=float, default=60.0, help="单次请求超时秒数（默认 60）")
    return ap.parse_args()


def main() -> int:
    """入口。"""
    args = parse_args()

    # 1. 取目标集（展厅需求事件已评分的企业）
    conn = connect()
    try:
        targets = fetch_targets(conn, args.limit)
    finally:
        conn.close()

    if not targets:
        print("目标集为空：没有「展厅需求事件已评分」的企业")
        return 0

    ids = [int(t["company_id"]) for t in targets]
    batch_size = max(1, min(MAX_BATCH_SIZE, args.chunk_size))
    chunks = chunked(ids, batch_size)
    print(f"目标企业：{len(ids)} 家（按最高分降序）")
    print("前 10 家：" + ", ".join(
        f"{t['name']}({t['company_id']}:{t['best_score']})" for t in targets[:10]))
    print(f"分批：{len(chunks)} 批 × ≤{batch_size} 家")

    # 2. dry-run 到此为止
    if not args.apply:
        print("dry-run：未调用 Java、未建任务。确认后加 --apply。")
        return 0

    # 3. 前置校验
    if not args.base_url:
        print("[error] 缺少 --base-url（或环境变量 RADAR_SCORE_JAVA_BASE_URL）")
        return 2
    if not args.token:
        print("[error] 缺少 --token（或环境变量 RADAR_ADMIN_TOKEN）")
        print("        取法：管理后台登录后的 oauth2_access_token（需 radar:event-job:create 权限）")
        return 2
    print("提示：确认 worker 在跑且 DEEPSEEK_SEARCH_KEY 已配；如需对照评测请先做基线快照。")

    # 4. 逐批创建，汇总结果
    created_ids: List[int] = []
    skip_reasons: Dict[str, int] = {}
    try:
        for idx, batch in enumerate(chunks, 1):
            data = post_batch(args.base_url, args.token, build_body(batch, args), args.timeout)
            items = data.get("items") or []
            for item in items:
                if item.get("success") and item.get("jobId") is not None:
                    created_ids.append(int(item["jobId"]))
                elif item.get("skipReason"):
                    reason = str(item["skipReason"])
                    skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            print(f"  第 {idx}/{len(chunks)} 批：成功 {data.get('successCount')}，"
                  f"跳过 {data.get('skipCount')}")
    except RuntimeError as ex:
        print(f"[error] {ex}")
        if created_ids:
            print(f"（出错前已创建 {len(created_ids)} 个任务，job id "
                  f"{min(created_ids)} ~ {max(created_ids)}）")
        return 1

    # 5. 收尾汇总
    print(f"\n完成：创建 {len(created_ids)} 个任务，跳过 {sum(skip_reasons.values())} 家")
    if created_ids:
        print(f"本批 job id 区间：{min(created_ids)} ~ {max(created_ids)}（共 {len(created_ids)} 个）")
    for reason, count in sorted(skip_reasons.items(), key=lambda kv: -kv[1]):
        print(f"  跳过原因 x{count}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())