#!/usr/bin/env python
"""
雷达新闻知识库写入链路：gd25 常驻 worker CLI。

    Java quartz 只建 `radar_news_content_task`（PENDING），
    本进程直连 exhibition MySQL 扫表抢锁，内部串行完成：
        规则下载正文 → 失败则 Agent 兜底一次 → embedding（公司网关）
        → 写 Milvus → 写 `radar_company_news_document` → 回写 task 状态
    另有周期补跑：扫 `embed_status IN (0,2)` 的 document 重做向量段（不重新下载）。

主循环实现：`backend/domain/news_content/worker_loop.py`（与 FastAPI lifespan 方案 A′ 共用）。
亦可设 `NEWS_CONTENT_WORKER_IN_APP=true` 由 `backend/main.py` 拉起，无需本脚本。

设计文档：exhibition `projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md` §3.1 / §3.2 / §6
         ai_docs/26091604-新闻知识库Worker技术说明.md

用法（仓库根目录）：
    python scripts/news_content_worker.py --dry-run
    python scripts/news_content_worker.py --once
    python scripts/news_content_worker.py

⚠️ 多实例并发安全：抢锁靠 MySQL 行锁（`FOR UPDATE SKIP LOCKED` + 条件 UPDATE），
    进程挂死后 RUNNING 任务由超时重置自动回收（默认 30 分钟）。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Optional

# 允许直接 `python scripts/news_content_worker.py` 运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.config import settings  # noqa: E402
from backend.domain.news_content import repository as repo  # noqa: E402
from backend.domain.news_content.constants import TASK_STATUS_TEXT  # noqa: E402
from backend.domain.news_content.worker_loop import (  # noqa: E402
    NewsContentWorkerOptions,
    run_news_content_loop,
)
from backend.infrastructure.database.mysql_connection import (  # noqa: E402
    close_pool,
    ping as mysql_ping,
)

log = logging.getLogger("news-content-worker")


def _setup_logging(verbose: bool) -> None:
    """统一日志格式（与 radar_crawl 一致）。"""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    for noisy in ("httpx", "httpcore", "pymilvus", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="雷达新闻知识库写入 worker（gd25 常驻进程）"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只读自检：检查配置/MySQL/Milvus/待处理任务，不写任何数据后退出",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="只处理一轮（或 --max-tasks 条）后退出；联调/回归用",
    )
    parser.add_argument(
        "--max-tasks", type=int, default=0,
        help="处理满 N 条任务后退出（0 = 不限，仅在 --once 之外叠加时生效）",
    )
    parser.add_argument(
        "--batch-size", type=int, default=None,
        help=f"每轮领取任务数（默认 {settings.NEWS_CONTENT_BATCH_SIZE}）",
    )
    parser.add_argument(
        "--poll-interval", type=float, default=None,
        help=f"无任务时的轮询间隔秒（默认 {settings.NEWS_CONTENT_POLL_INTERVAL_SECONDS}）",
    )
    parser.add_argument(
        "--worker-id", type=str, default=None,
        help="实例标识（写 task.locked_by）；默认 hostname:pid",
    )
    parser.add_argument(
        "--no-agent", action="store_true",
        help="本次运行禁用 Agent 兜底（只跑规则通道，省钱）",
    )
    parser.add_argument(
        "--skip-backfill", action="store_true",
        help="本次运行不做 embedding 补跑循环",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="DEBUG 日志")
    return parser.parse_args(argv)


# ================================================================ 只读自检

def _is_missing_table(exc: BaseException) -> bool:
    """MySQL 1146：表不存在（= DDL 还没执行，而非 worker 自身有问题）。"""
    args = getattr(exc, "args", ()) or ()
    return bool(args) and args[0] == 1146


def _print_ddl_pending() -> None:
    """两张表的 DDL 尚未执行时的提示（DDL 归 Java 侧 SQL 脚本，gd25 不建表）。"""
    print("  FAIL 两张表尚未创建 —— exhibition 侧 DDL 未执行")
    print("       待执行脚本（Java 侧 SQL，gd25 不负责建表、也不改 exhibition 仓库）：")
    print("         projectDocs/技术设计文档-0905/SQL脚本/17_radar_news_content_schema.sql")
    print("       建表后本自检即应全绿；在此之前 worker 起来也抢不到任务。")


async def run_dry_run(batch_size: int) -> int:
    """
        只读自检（**绝不写数据**）。

        Returns:
            进程退出码（0 成功，1 有硬伤）
    """
    print("=" * 78)
    print("雷达新闻知识库 worker —— 只读自检（--dry-run，不写任何数据）")
    print("=" * 78)

    hard_fail = False

    print("\n[1/5] 配置检查")
    checks = [
        ("exhibition MySQL 配置", settings.is_exhibition_mysql_enabled,
         "EXHIBITION_MYSQL_HOST / USER / DB"),
        ("Milvus 配置", settings.is_milvus_enabled, "MILVUS_URI / MILVUS_USER / MILVUS_PASSWORD"),
        ("embedding 配置", settings.is_embedding_enabled, "HUAYUAN_API_URL_embeddings / HUAYUAN_API_KEY"),
        ("Agent 兜底开关", bool(settings.NEWS_CONTENT_AGENT_FALLBACK_ENABLED),
         "NEWS_CONTENT_AGENT_FALLBACK_ENABLED"),
    ]
    for name, ok, hint in checks:
        print(f"  {'OK  ' if ok else 'MISS'} {name}" + ("" if ok else f"   ← 检查 {hint}"))
        if name == "exhibition MySQL 配置" and not ok:
            hard_fail = True
    print(f"  INFO 主库 PG（DATABASE_URL）启用={settings.is_database_enabled}"
          "  ← 本链路不使用，无影响")
    print(f"  INFO NEWS_CONTENT_WORKER_IN_APP={settings.NEWS_CONTENT_WORKER_IN_APP}"
          "  ← true 时可由 FastAPI lifespan 拉起同一主循环")
    print(f"  INFO embedding 模型={settings.EMBEDDING_MODEL} 端点="
          f"{'已配置' if settings.HUAYUAN_API_URL_embeddings else '未配置'}")
    print(f"  INFO Milvus collection={settings.MILVUS_COLLECTION} "
          f"db={settings.MILVUS_DB_NAME} uri={'已配置' if settings.MILVUS_URI else '未配置'}")
    print(f"  INFO 每轮领取数={batch_size} 轮询间隔={settings.NEWS_CONTENT_POLL_INTERVAL_SECONDS}s "
          f"锁超时={settings.NEWS_CONTENT_LOCK_TIMEOUT_SECONDS}s "
          f"同站最小间隔={settings.NEWS_CONTENT_SITE_MIN_INTERVAL_SECONDS}s")
    print(f"  INFO Agent 兜底：日配额={settings.NEWS_CONTENT_AGENT_DAILY_QUOTA} "
          f"熔断阈值={settings.NEWS_CONTENT_AGENT_MAX_CONSECUTIVE_FAILURES} "
          f"超时={settings.NEWS_CONTENT_AGENT_TIMEOUT_SECONDS}s")

    print("\n[2/5] exhibition MySQL 连通性")
    if settings.is_exhibition_mysql_enabled:
        if mysql_ping():
            print("  OK   SELECT 1 通过")
        else:
            print("  FAIL 连接失败（检查网络/账号/白名单）")
            hard_fail = True
    else:
        print("  SKIP  未配置 exhibition MySQL")

    if settings.is_exhibition_mysql_enabled and not hard_fail:
        print("\n[3/5] radar_news_content_task 状态分布（只读）")
        try:
            counts = await repo.count_tasks_by_status()
            if not counts:
                print("  INFO 表内暂无数据")
            for status in sorted(counts):
                print(f"  {TASK_STATUS_TEXT.get(status, str(status)):<8} {counts[status]}")
            pending = counts.get(0, 0)
            print(f"  INFO 当前可领取（PENDING）={pending}")
        except Exception as exc:
            if _is_missing_table(exc):
                _print_ddl_pending()
                hard_fail = True
            else:
                print(f"  FAIL 查询失败: {type(exc).__name__}: {exc}")
                hard_fail = True

        print("\n[4/5] PENDING 预览（只读，不抢锁）")
        try:
            rows = await repo.list_pending_tasks_preview(min(batch_size, 10))
            if not rows:
                print("  INFO 没有待处理任务")
            for row in rows:
                print(
                    f"  #{row['id']} company_id={row['company_id']} "
                    f"news_url_id={row['news_url_id']} source_url_id={row['source_url_id']} "
                    f"level={row['source_level']} url={str(row['url'])[:80]}"
                )
        except Exception as exc:
            if not _is_missing_table(exc):
                print(f"  FAIL 查询失败: {type(exc).__name__}: {exc}")
                hard_fail = True
            elif not hard_fail:
                _print_ddl_pending()
                hard_fail = True

        try:
            doc_counts = await repo.count_documents_by_embed_status()
            print("\n      radar_company_news_document embed_status 分布（只读）")
            if not doc_counts:
                print("        INFO 表内暂无数据")
            for status in sorted(doc_counts):
                label = {0: "待向量化", 1: "已向量化", 2: "失败"}.get(status, str(status))
                print(f"        {label:<8}({status}) {doc_counts[status]}")
            backfillable = sum(n for s, n in doc_counts.items() if s in (0, 2))
            print(f"        INFO 可补跑（embed_status in 0/2）={backfillable}")
        except Exception as exc:
            if _is_missing_table(exc):
                print("        SKIP document 表未建（同 [3/5]，待执行 DDL）")
            else:
                print(f"      WARN document 表查询失败: {type(exc).__name__}: {exc}")

    print("\n[5/5] Milvus collection 概况（只读；collection 不存在也不会被创建）")
    if settings.is_milvus_enabled:
        from backend.infrastructure.milvus.radar_news_doc_store import RadarNewsDocStore

        store = RadarNewsDocStore()
        try:
            info = await store.describe_async()
            print(f"  uri={info.get('uri')} db={info.get('db_name')} "
                  f"collection={info.get('collection')} dim={info.get('dim')}")
            if info.get("exists"):
                print(f"  OK   collection 存在；row_count={info.get('row_count', 'N/A')}")
                for field in info.get("fields", []):
                    flags = []
                    if field.get("is_primary"):
                        flags.append("PK")
                    if field.get("is_partition_key"):
                        flags.append("PARTITION_KEY")
                    print(f"       - {field.get('name'):<12} {field.get('type'):<20} {' '.join(flags)}")
            else:
                print("  INFO collection 尚不存在（由 worker 首次写入时自动创建）")
        except Exception as exc:
            print(f"  WARN Milvus 探测失败（不影响只读自检结论）: {type(exc).__name__}: {exc}")
        finally:
            await store.close_async()
    else:
        print("  SKIP  未配置 Milvus")

    print("\n" + "=" * 78)
    print("自检结论：" + ("发现阻塞性问题（见上）" if hard_fail else "全部通过，worker 可以启动"))
    print("=" * 78)
    return 1 if hard_fail else 0


async def run_worker(args: argparse.Namespace) -> int:
    """
        CLI 包装：组装 Options 后调用共用主循环。

        Returns:
            退出码
    """
    stop = asyncio.Event()
    options = NewsContentWorkerOptions(
        batch_size=args.batch_size,
        poll_interval=args.poll_interval,
        worker_id=args.worker_id,
        skip_backfill=bool(args.skip_backfill),
        once=bool(args.once),
        max_tasks=int(args.max_tasks or 0),
        disable_agent=bool(args.no_agent),
        close_pool_on_exit=True,
        install_signals=True,
    )
    return await run_news_content_loop(stop, options)


def main(argv: Optional[list[str]] = None) -> int:
    """入口。"""
    args = _parse_args(argv)
    _setup_logging(args.verbose)

    if args.dry_run:
        try:
            return asyncio.run(run_dry_run(int(args.batch_size or settings.NEWS_CONTENT_BATCH_SIZE)))
        finally:
            close_pool()

    if not settings.is_exhibition_mysql_enabled:
        log.error(
            "未配置 exhibition MySQL（EXHIBITION_MYSQL_HOST / USER / PASSWORD / DB），worker 无法启动"
        )
        return 2

    try:
        return asyncio.run(run_worker(args))
    except KeyboardInterrupt:
        log.warning("KeyboardInterrupt，退出")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
