"""
应用启动与关闭编排

集中管理 lifespan 中的各子系统初始化步骤。
"""
from __future__ import annotations

import asyncio
import logging

from backend.app.config import find_project_root
from backend.domain.context.cache_loader import load_context_cache
from backend.domain.flows.manager import FlowManager
from backend.domain.tools import init_tools
from backend.infrastructure.llm.providers.manager import ProviderManager

logger = logging.getLogger(__name__)


class ApplicationBootstrap:
    """应用生命周期启动/关闭编排器"""

    def __init__(self) -> None:
        self._consumer_tasks: list[asyncio.Task] = []

    async def startup(self) -> None:
        """执行全部启动步骤，任一步骤失败将抛出异常。"""
        logger.info("=" * 60)
        logger.info("系统启动中...")
        logger.info("=" * 60)

        logger.info("1. 加载模型供应商配置...")
        config_path = find_project_root() / "config" / "model_providers.yaml"
        ProviderManager.load_providers(config_path)
        logger.info("   ✓ 成功加载模型供应商配置")

        logger.info("2. 初始化工具注册表...")
        init_tools()
        logger.info("   ✓ 工具注册表初始化完成")

        logger.info("3. 扫描流程文件...")
        flows = FlowManager.scan_flows()
        logger.info("   ✓ 扫描到 %s 个流程定义", len(flows))

        logger.info("4. 预加载常用流程...")
        loader_config = FlowManager.get_flow_loader_config()
        preload_flows = loader_config.get("preload", [])
        if preload_flows:
            FlowManager.preload_flows(preload_flows)
            logger.info("   ✓ 成功预加载 %s 个流程", len(preload_flows))
        else:
            logger.info("   ✓ 没有需要预加载的流程")

        logger.info("5. 加载Token和Session缓存...")
        await load_context_cache()
        logger.info("   ✓ 缓存加载完成")

        logger.info("6. 启动 Rewritten 任务队列消费者...")
        from backend.pipeline.rewritten_queue_service import start_consumers

        self._consumer_tasks = start_consumers()
        logger.info("   ✓ Rewritten 队列消费者已启动")

        logger.info("=" * 60)
        logger.info("系统启动完成！")
        logger.info("=" * 60)

    async def shutdown(self) -> None:
        """执行关闭清理。"""
        if self._consumer_tasks:
            for task in self._consumer_tasks:
                task.cancel()
            await asyncio.gather(*self._consumer_tasks, return_exceptions=True)
            logger.info("Rewritten 队列消费者已停止")

        logger.info("系统正在关闭...")
