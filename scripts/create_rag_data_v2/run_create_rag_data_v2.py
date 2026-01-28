#!/usr/bin/env python
"""
create_rag_data_v2 脚本入口。

功能：
- 从指定目录读取 QA 场景独立记录 Markdown 文件；
- 通过 create_rag_agent 流程执行大模型调用与入库；
- 输出成功/失败统计信息。

使用方式：
    python scripts/create_rag_data_v2/run_create_rag_data_v2.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

# 将项目根目录加入 sys.path，风格对齐 import_blood_pressure_session_data.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import find_project_root
from backend.domain.flows.manager import FlowManager
from backend.infrastructure.llm.providers.manager import ProviderManager

from scripts.create_rag_data_v2.config import load_config
from scripts.create_rag_data_v2.file_loader import load_all_markdowns
from scripts.create_rag_data_v2.flow_runner import run_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """主函数，风格对齐 import_blood_pressure_session_data.py。"""

    logger.info("=" * 60)
    logger.info("create_rag_data_v2 知识库导入脚本")
    logger.info("=" * 60)

    script_start_time = time.time()

    # 1. 加载运行配置
    try:
        cfg = load_config()
        logger.info(
            "配置加载成功: base_dir=%s, include_files=%s, exclude_files=%s, "
            "max_concurrency=%s, retry_times=%s, flow_key=%s, dry_run=%s",
            cfg.base_dir,
            cfg.include_files,
            cfg.exclude_files,
            cfg.max_concurrency,
            cfg.retry_times,
            cfg.flow_key,
            cfg.dry_run,
        )
    except Exception as e:
        logger.error("加载脚本配置失败: %s", e)
        sys.exit(1)

    # 2. 加载模型供应商配置
    try:
        logger.info("加载模型供应商配置...")
        project_root = find_project_root()
        config_path = project_root / "config" / "model_providers.yaml"
        ProviderManager.load_providers(config_path)
        logger.info("模型供应商配置加载成功")
    except Exception as e:
        logger.error("加载模型供应商配置失败: %s", e)
        sys.exit(1)

    # 3. 加载流程图
    try:
        graph = FlowManager.get_flow(cfg.flow_key)
        logger.info("流程图加载成功: %s", cfg.flow_key)
    except Exception as e:
        logger.error("加载流程图失败: %s", e)
        sys.exit(1)

    # 4. 构造 MarkdownSource 列表
    try:
        sources = load_all_markdowns(cfg, PROJECT_ROOT)
        logger.info("发现待处理 Markdown 文件数: %d", len(sources))
    except Exception as e:
        logger.error("扫描或读取 Markdown 文件失败: %s", e)
        sys.exit(1)

    if not sources:
        logger.info("无待处理 Markdown 文件，脚本结束")
        total_elapsed = time.time() - script_start_time
        logger.info("总耗时: %.2f 秒", total_elapsed)
        sys.exit(0)

    # 5. 执行批处理
    try:
        batch_start_time = time.time()
        ok, fail = asyncio.run(run_batch(sources, cfg, graph))
        batch_elapsed = time.time() - batch_start_time
        total_elapsed = time.time() - script_start_time

        logger.info("=" * 60)
        logger.info("批次结果: 成功=%d 失败=%d", ok, fail)
        logger.info("批次执行耗时: %.2f 秒", batch_elapsed)
        logger.info("总耗时: %.2f 秒", total_elapsed)
        logger.info("=" * 60)

        if fail > 0:
            sys.exit(1)
        sys.exit(0)
    except KeyboardInterrupt:
        logger.warning("\n⚠️  用户中断操作")
        sys.exit(130)
    except Exception as e:
        logger.error("\n✗ 执行失败: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

