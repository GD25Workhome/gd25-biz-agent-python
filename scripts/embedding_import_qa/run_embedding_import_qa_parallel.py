#!/usr/bin/env python
"""
知识库 Embedding 导入脚本入口（并行化版本）

从 knowledge_base 表读取未处理记录，组装 state，执行 embedding_knowledge_agent 流程。
使用并行处理提升执行速度。

使用方式：
    python scripts/embedding_import_qa/run_embedding_import_qa_parallel.py [--limit N] [--max-concurrent M] [--dry-run]

未指定 --limit 时，默认 batch_size=5。
未指定 --max-concurrent 时，默认并发数=5。

设计文档：cursor_docs/012901-知识库Embedding导入脚本设计.md
"""
import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any, List, Tuple, TYPE_CHECKING

# 项目根加入 path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.app.config import find_project_root
from backend.domain.flows.manager import FlowManager
from backend.infrastructure.llm.providers.manager import ProviderManager

from scripts.embedding_import_qa.core import DEFAULT_BATCH_SIZE, FLOW_KEY
from scripts.embedding_import_qa.core.repository import fetch_records_excluding_processed
from scripts.embedding_import_qa.core.runner import run_batch_parallel

if TYPE_CHECKING:
    from backend.infrastructure.database.models.knowledge_base import (
        KnowledgeBaseRecord,
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="知识库 Embedding 导入（并行化）：读 knowledge_base 表 -> 组装 state -> 跑 embedding_knowledge_agent 流程"
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
        help="最大并发数（默认 5）",
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
    max_concurrent = args.max_concurrent
    dry_run = args.dry_run

    logger.info("=" * 60)
    logger.info("知识库 Embedding 导入脚本（并行化版本）")
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

    # 3. 查询未处理的知识库记录
    try:
        records: List["KnowledgeBaseRecord"] = fetch_records_excluding_processed(
            limit=limit, offset=0
        )
        logger.info("查询到 %d 条未处理记录", len(records))
    except Exception as e:
        logger.error("查询知识库表失败: %s", e)
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
