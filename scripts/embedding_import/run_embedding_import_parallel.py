#!/usr/bin/env python
"""
Embedding 导入脚本入口（并行化版本）

从 blood_pressure_session_records 表读取数据，组装 state/config，执行 embedding_agent 流程。
使用并行处理提升执行速度。

使用方式：
    python scripts/embedding_import/run_embedding_import_parallel.py [--limit N] [--max-concurrent M] [--dry-run]

未指定 --limit 时，默认 batch_size=5。
未指定 --max-concurrent 时，默认并发数=5。
"""
import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any, List, Tuple, TYPE_CHECKING

# 项目根加入 path（与 import_blood_pressure_session_data 等脚本一致）
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.domain.flows.manager import FlowManager
from backend.infrastructure.llm.providers.manager import ProviderManager
from backend.app.config import find_project_root

from scripts.embedding_import.core import DEFAULT_BATCH_SIZE, FLOW_KEY
from scripts.embedding_import.core.repository import fetch_records_excluding_processed
from scripts.embedding_import.core.runner import run_one

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Embedding 导入（并行化版本）：读表 -> 组装 -> 跑 embedding_agent 流程"
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help=f"单次拉取条数（默认 {DEFAULT_BATCH_SIZE}）",
    )
    p.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="最大并发数（默认 5，建议根据 LLM API 限流调整）",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="仅组装 state，不执行 graph.ainvoke",
    )
    return p.parse_args()


if TYPE_CHECKING:
    from backend.infrastructure.database.models.blood_pressure_session import (
        BloodPressureSessionRecord,
    )


async def run_batch_parallel(
    records: List["BloodPressureSessionRecord"],
    graph: Any,
    *,
    max_concurrent: int = 5,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """
    并行执行批次处理。
    
    使用 asyncio.Semaphore 控制并发数，使用 asyncio.gather 并行执行所有任务。
    
    Args:
        records: 记录列表
        graph: 流程图对象
        max_concurrent: 最大并发数
        dry_run: 是否仅组装 state，不执行 invoke
        
    Returns:
        (成功数, 失败数)
    """
    if not records:
        return (0, 0)
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def run_with_semaphore(record):
        """带并发控制的单条记录执行。"""
        async with semaphore:
            return await run_one(record, graph, dry_run=dry_run)
    
    # 创建所有任务
    tasks = [run_with_semaphore(record) for record in records]
    logger.info("创建 %d 个并行任务，最大并发数=%d", len(tasks), max_concurrent)
    
    # 并行执行所有任务
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 统计结果
    ok, fail = 0, 0
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("任务执行异常 record_id=%s error=%s", 
                        getattr(records[i], "id", "?"), result, exc_info=result)
            fail += 1
        elif result:
            ok += 1
        else:
            fail += 1
    
    return (ok, fail)


async def main() -> None:
    script_start_time = time.time()
    args = _parse_args()
    limit = args.limit if args.limit is not None else DEFAULT_BATCH_SIZE
    max_concurrent = args.max_concurrent
    dry_run = args.dry_run

    logger.info("=" * 60)
    logger.info("Embedding 导入脚本（并行化版本）")
    logger.info("=" * 60)
    logger.info("limit=%s max_concurrent=%s dry_run=%s", limit, max_concurrent, dry_run)

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

    # 3. 查询记录
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

    # 4. 并行执行批次处理
    batch_start_time = time.time()
    try:
        ok, fail = await run_batch_parallel(
            records, graph, max_concurrent=max_concurrent, dry_run=dry_run
        )
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
    except Exception as e:
        total_elapsed = time.time() - script_start_time
        logger.error("批次执行异常: %s", e, exc_info=True)
        logger.info("总耗时: %.2f 秒", total_elapsed)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
