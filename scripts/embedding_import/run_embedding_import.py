#!/usr/bin/env python
"""
Embedding 导入脚本入口

从 blood_pressure_session_records 表读取数据，组装 state/config，执行 embedding_agent 流程。
使用方式：
    python scripts/embedding_import/run_embedding_import.py [--limit N] [--dry-run]

未指定 --limit 时，默认 batch_size=5。
"""
import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# 项目根加入 path（与 import_blood_pressure_session_data 等脚本一致）
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.domain.flows.manager import FlowManager
from backend.infrastructure.llm.providers.manager import ProviderManager
from backend.app.config import find_project_root

from scripts.embedding_import.core import DEFAULT_BATCH_SIZE, FLOW_KEY
from scripts.embedding_import.core.repository import fetch_records_excluding_processed
from scripts.embedding_import.core.runner import run_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Embedding 导入：读表 -> 组装 -> 跑 embedding_agent 流程")
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help=f"单次拉取条数（默认 {DEFAULT_BATCH_SIZE}）",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="仅组装 state，不执行 graph.ainvoke",
    )
    return p.parse_args()


async def main() -> None:
    script_start_time = time.time()
    args = _parse_args()
    limit = args.limit if args.limit is not None else DEFAULT_BATCH_SIZE
    dry_run = args.dry_run

    logger.info("=" * 60)
    logger.info("Embedding 导入脚本")
    logger.info("=" * 60)
    logger.info("limit=%s dry_run=%s", limit, dry_run)

    # 1. 加载模型供应商配置（必须在加载流程图之前）
    try:
        logger.info("加载模型供应商配置...")
        project_root = find_project_root()
        config_path = project_root / "config" / "model_providers.yaml"
        ProviderManager.load_providers(config_path)
        logger.info("模型供应商配置加载成功")
    except Exception as e:
        logger.error("加载模型供应商配置失败: %s", e)
        sys.exit(1)

    # 2. 加载流程图
    try:
        graph = FlowManager.get_flow(FLOW_KEY)
        logger.info("流程图加载成功: %s", FLOW_KEY)
    except Exception as e:
        logger.error("加载流程图失败: %s", e)
        sys.exit(1)

    try:
        records = fetch_records_excluding_processed(limit=limit, offset=0)
        logger.info("查询到 %d 条未处理记录", len(records))
    except Exception as e:
        logger.error("查询表失败: %s", e)
        sys.exit(1)

    if not records:
        logger.info("无数据，退出")
        total_elapsed = time.time() - script_start_time
        logger.info("总耗时: %.2f 秒", total_elapsed)
        return

    batch_start_time = time.time()
    ok, fail = await run_batch(records, graph, dry_run=dry_run)
    batch_elapsed = time.time() - batch_start_time
    total_elapsed = time.time() - script_start_time
    
    logger.info("=" * 60)
    logger.info("批次结果: 成功=%d 失败=%d", ok, fail)
    logger.info("批次执行耗时: %.2f 秒", batch_elapsed)
    if len(records) > 0:
        logger.info("平均每条耗时: %.2f 秒", batch_elapsed / len(records))
    logger.info("总耗时: %.2f 秒", total_elapsed)
    logger.info("=" * 60)
    if fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
