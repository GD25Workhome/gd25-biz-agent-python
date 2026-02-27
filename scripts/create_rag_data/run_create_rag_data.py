#!/usr/bin/env python
"""
QA 场景独立记录转知识库脚本入口（并行化）

从 cursor_docs/012802-QA场景独立记录 读取 md，经单节点 create_rag_agent 流程得到 cases，写入 knowledge_base 表。
运行范围与并发数在 core.config 中配置，无需启动参数。

使用方式：
    python scripts/create_rag_data/run_create_rag_data.py
"""
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any, Tuple

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.domain.flows.manager import FlowManager
from backend.infrastructure.llm.providers.manager import ProviderManager
from backend.app.config import find_project_root
from backend.infrastructure.database.connection import get_session_factory

from scripts.create_rag_data.core.config import (
    CREATE_RAG_AGENT_FLOW_KEY,
    MAX_CONCURRENT,
)
from scripts.create_rag_data.core.file_loader import get_md_paths, path_to_relative
from scripts.create_rag_data.core.flow_runner import run_flow
from scripts.create_rag_data.core.parser import parse_cases_from_model_output
from scripts.create_rag_data.core.repository import save_cases

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def process_one_file(
    md_path: Path,
    graph: Any,
    semaphore: asyncio.Semaphore,
) -> Tuple[bool, int]:
    """
    处理单个 md 文件：读文件 → 调 flow → 解析 → 落库。

    Returns:
        (是否成功, 写入条数)
    """
    async with semaphore:
        file_id = md_path.stem
        source_file_rel = path_to_relative(md_path)
        try:
            content = md_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("读取文件失败 path=%s error=%s", md_path, e, exc_info=True)
            return (False, 0)

        try:
            model_output = await run_flow(graph, content, file_id=file_id)
        except Exception as e:
            logger.error("调用 flow 失败 path=%s error=%s", md_path, e, exc_info=True)
            return (False, 0)

        cases = parse_cases_from_model_output(model_output)
        if not cases:
            logger.warning("解析 cases 为空 path=%s 输出长度=%d", md_path, len(model_output or ""))
            return (False, 0)

        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                count = await save_cases(
                    session,
                    cases,
                    source_file_rel=source_file_rel,
                    raw_material_full_text=content,
                )
                await session.commit()
                logger.info("处理成功 path=%s cases=%d", md_path.name, count)
                return (True, count)
            except Exception as e:
                await session.rollback()
                logger.error("落库失败 path=%s error=%s", md_path, e, exc_info=True)
                return (False, 0)


async def main() -> None:
    script_start = time.time()
    logger.info("=" * 60)
    logger.info("QA 场景独立记录转知识库脚本（并行化）")
    logger.info("=" * 60)

    try:
        project_root = find_project_root()
        config_path = project_root / "config" / "model_providers.yaml"
        ProviderManager.load_providers(config_path)
        logger.info("模型供应商配置加载成功")
    except Exception as e:
        logger.error("加载模型供应商配置失败: %s", e)
        sys.exit(1)

    try:
        graph = FlowManager.get_flow(CREATE_RAG_AGENT_FLOW_KEY)
        logger.info("流程图加载成功: %s", CREATE_RAG_AGENT_FLOW_KEY)
    except Exception as e:
        logger.error("加载流程图失败: %s", e)
        sys.exit(1)

    md_paths = get_md_paths()
    logger.info("待处理文件数: %d", len(md_paths))
    if not md_paths:
        logger.info("无待处理文件，退出")
        return

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [process_one_file(p, graph, semaphore) for p in md_paths]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    ok, fail, total_rows = 0, 0, 0
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error("任务异常 path=%s error=%s", md_paths[i].name, r, exc_info=r)
            fail += 1
        else:
            success, count = r
            if success:
                ok += 1
                total_rows += count
            else:
                fail += 1

    elapsed = time.time() - script_start
    logger.info("=" * 60)
    logger.info("结果: 成功文件=%d 失败文件=%d 写入行数=%d 耗时=%.2fs", ok, fail, total_rows, elapsed)
    logger.info("=" * 60)
    if fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
