#!/usr/bin/env python
"""
雷达新闻知识库写入链路：gd25 常驻 worker。

    Java quartz 只建 `radar_news_content_task`（PENDING），
    本进程直连 exhibition MySQL 扫表抢锁，内部串行完成：
        规则下载正文 → 失败则 Agent 兜底一次 → embedding（公司网关）
        → 写 Milvus → 写 `radar_company_news_document` → 回写 task 状态
    另有周期补跑：扫 `embed_status IN (0,2)` 的 document 重做向量段（不重新下载）。

设计文档：exhibition `projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md` §3.1 / §3.2 / §6

用法（仓库根目录）：
    # 只读自检：起得来吗？DB 通吗？PENDING 有多少？（不写任何数据）
    python scripts/news_content_worker.py --dry-run

    # 跑一轮就退出（联调/回归用；会真实写入，谨慎）
    python scripts/news_content_worker.py --once

    # 常驻（生产；建议由 supervisor / systemd / K8s 拉起）
    python scripts/news_content_worker.py

⚠️ 独立进程托管，**不挂 FastAPI**：脚本目录下无 worker 先例，本文件即入口。
⚠️ 多实例并发安全：抢锁靠 MySQL 行锁（`FOR UPDATE SKIP LOCKED` + 条件 UPDATE），
    进程挂死后 RUNNING 任务由超时重置自动回收（默认 30 分钟）。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from typing import Optional

# 允许直接 `python scripts/news_content_worker.py` 运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.config import settings  # noqa: E402
from backend.domain.news_content import repository as repo  # noqa: E402
from backend.domain.news_content.constants import TASK_STATUS_TEXT  # noqa: E402
from backend.domain.news_content.pipeline import NewsContentProcessor  # noqa: E402
from backend.infrastructure.database.mysql_connection import (  # noqa: E402
    close_pool,
    default_worker_id,
    ping as mysql_ping,
)

log = logging.getLogger("news-content-worker")

# RUNNING 超时重置的检查间隔（秒）：与锁超时同量级即可，不必每轮都扫
_STALE_CHECK_INTERVAL_SECONDS = 60.0


def _setup_logging(verbose: bool) -> None:
    """统一日志格式（与 radar_crawl 一致）。"""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    # 第三方库日志降噪
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

    检查项：
      1. 配置齐备性：exhibition MySQL / Milvus / embedding / Agent 兜底
      2. exhibition MySQL 连通性（`SELECT 1`）
      3. task 表各状态计数 + PENDING 预览（**不抢锁、不改状态**）
      4. document 表 embed_status 分布
      5. Milvus collection 概况（**只读**，collection 不存在也不会被建出来）

    Returns:
        进程退出码（0 成功，1 有硬伤）
    """
    print("=" * 78)
    print("雷达新闻知识库 worker —— 只读自检（--dry-run，不写任何数据）")
    print("=" * 78)

    hard_fail = False

    # ---------- 1. 配置 ----------
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

    # ---------- 2. MySQL 连通性 ----------
    print("\n[2/5] exhibition MySQL 连通性")
    if settings.is_exhibition_mysql_enabled:
        if mysql_ping():
            print("  OK   SELECT 1 通过")
        else:
            print("  FAIL 连接失败（检查网络/账号/白名单）")
            hard_fail = True
    else:
        print("  SKIP  未配置 exhibition MySQL")

    # ---------- 3/4. 表数据（只读） ----------
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
            backfillable = sum(
                n for s, n in doc_counts.items() if s in (0, 2)
            )
            print(f"        INFO 可补跑（embed_status in 0/2）={backfillable}")
        except Exception as exc:
            if _is_missing_table(exc):
                print("        SKIP document 表未建（同 [3/5]，待执行 DDL）")
            else:
                print(f"      WARN document 表查询失败: {type(exc).__name__}: {exc}")

    # ---------- 5. Milvus ----------
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


# ================================================================ 常驻主循环

async def run_worker(args: argparse.Namespace) -> int:
    """
    worker 主循环。

    每轮：
      1. （按间隔）把超时 RUNNING 任务重置回 PENDING
      2. （按间隔）补跑 embedding
      3. 抢一批 PENDING → 逐条串行处理 → 回写
      4. 没抢到就按 poll_interval 睡（可被信号打断）
    """
    batch_size = int(args.batch_size or settings.NEWS_CONTENT_BATCH_SIZE)
    poll_interval = float(
        args.poll_interval
        if args.poll_interval is not None
        else settings.NEWS_CONTENT_POLL_INTERVAL_SECONDS
    )
    worker_id = args.worker_id or settings.NEWS_CONTENT_WORKER_ID or default_worker_id()

    if args.no_agent:
        settings.NEWS_CONTENT_AGENT_FALLBACK_ENABLED = False

    stop = asyncio.Event()
    _install_signal_handlers(stop)

    processor = NewsContentProcessor(worker_id=worker_id)

    log.info(
        "worker 启动 id=%s db=%s@%s/%s collection=%s batch=%d poll=%.1fs "
        "lock_timeout=%ds agent_fallback=%s backfill=%s",
        worker_id,
        settings.EXHIBITION_MYSQL_USER, settings.EXHIBITION_MYSQL_HOST,
        settings.EXHIBITION_MYSQL_DB, settings.MILVUS_COLLECTION,
        batch_size, poll_interval, settings.NEWS_CONTENT_LOCK_TIMEOUT_SECONDS,
        settings.NEWS_CONTENT_AGENT_FALLBACK_ENABLED, not args.skip_backfill,
    )

    processed = 0
    last_stale_check = 0.0
    last_backfill = 0.0

    try:
        while not stop.is_set():
            now = time.monotonic()

            # ---- 1. RUNNING 超时重置（worker 挂死自愈） ----
            if now - last_stale_check >= _STALE_CHECK_INTERVAL_SECONDS:
                last_stale_check = now
                try:
                    reset = await repo.reset_stale_running(
                        settings.NEWS_CONTENT_LOCK_TIMEOUT_SECONDS
                    )
                    if reset:
                        log.warning("RUNNING 超时重置回 PENDING：%d 条", reset)
                except Exception:
                    log.exception("RUNNING 超时重置失败（下一轮重试）")

            # ---- 2. embedding 补跑循环 ----
            if not args.skip_backfill and now - last_backfill >= settings.NEWS_CONTENT_EMBED_BACKFILL_INTERVAL_SECONDS:
                last_backfill = now
                try:
                    await processor.backfill_embeddings()
                except Exception:
                    log.exception("补跑循环异常（不中断主循环）")

            # ---- 3. 抢一批任务 ----
            try:
                tasks = await repo.claim_tasks(worker_id, batch_size)
            except Exception:
                log.exception("抢锁失败，休眠后重试")
                if await _sleep_or_stop(stop, poll_interval):
                    break
                continue

            if not tasks:
                if await _sleep_or_stop(stop, poll_interval):
                    break
                continue

            # ---- 4. 逐条串行处理（串行是刻意的：同站限速 + embedding 单条调用） ----
            for index, task in enumerate(tasks):
                if stop.is_set():
                    remaining = len(tasks) - index
                    log.warning(
                        "收到退出信号，本轮剩余 %d 条仍为 RUNNING，"
                        "将由锁超时（%ds）自动重置回 PENDING",
                        remaining, settings.NEWS_CONTENT_LOCK_TIMEOUT_SECONDS,
                    )
                    break
                try:
                    outcome = await processor.process_task(task)
                    processed += 1
                    log.info(
                        "任务处理完毕 task_id=%s ok=%s channel=%s document_id=%s "
                        "embed_status=%s cost_ms=%s error=%s",
                        outcome.task_id, outcome.ok, outcome.channel,
                        outcome.document_id, outcome.embed_status,
                        outcome.cost_ms, outcome.error,
                    )
                except Exception:
                    # process_task 内部已兜底，走到这里说明兜底自身出问题 —— 记日志继续
                    log.exception("任务处理异常 task_id=%s（已跳过，等待超时重置）", task.get("id"))

                if args.max_tasks and processed >= args.max_tasks:
                    log.info("已达 --max-tasks=%d，退出", args.max_tasks)
                    stop.set()
                    break

            if args.once:
                log.info("--once：完成一轮处理后退出")
                break
    finally:
        log.info("worker 收尾：已处理 %d 条任务", processed)
        try:
            await processor.aclose()
        except Exception:
            log.debug("processor 收尾异常", exc_info=True)
        close_pool()

    return 0


def _install_signal_handlers(stop: asyncio.Event) -> None:
    """
    注册 SIGINT/SIGTERM 优雅退出。

    收到信号后置位 stop：当前任务处理完、连接归还、资源关闭后再退出，
    不会把任务半途丢在 RUNNING（即便丢了，也有超时重置兜底）。
    """
    loop = asyncio.get_running_loop()

    def _on_signal(signum: int) -> None:
        log.warning("收到信号 %s，准备优雅退出（当前任务处理完后停止）", signum)
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal, sig)
        except (NotImplementedError, RuntimeError):
            # Windows 等不支持 add_signal_handler 的平台：退化为默认行为
            try:
                signal.signal(sig, lambda s, _f: _on_signal(s))
            except Exception:
                log.debug("信号 %s 注册失败", sig, exc_info=True)


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> bool:
    """
    可被信号打断的 sleep。

    Returns:
        True 表示收到停止信号（调用方应退出循环）
    """
    if seconds <= 0:
        return stop.is_set()
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
        return True
    except asyncio.TimeoutError:
        return False


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
