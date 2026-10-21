"""
FastAPI 应用入口（规则二最小集）

运行方式：
    conda activate py311_GD25_base
    python backend/main.py
    # 或
    uvicorn backend.main:app --host 0.0.0.0 --port 8000

只提供：
    POST /api/v1/huayuan/radar-event-score
    GET  /health
"""
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager

# 添加项目根目录到 Python 路径（必须在导入 backend 模块之前）
_file_path = Path(__file__).resolve()
project_root = _file_path.parent.parent
project_root_str = str(project_root)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router
from backend.infrastructure.llm.providers.manager import ProviderManager
from backend.domain.flows.manager import FlowManager
from backend.domain.tools import init_tools
from backend.app.config import find_project_root, settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：只加载规则二运行所需组件。"""
    radar_score_stop = None
    radar_score_threads = None
    anysearch_pool = None

    logger.info("=" * 60)
    logger.info("规则二评分服务启动中...")
    logger.info("=" * 60)

    try:
        # 1. 加载模型供应商配置
        logger.info("1. 加载模型供应商配置...")
        app_project_root = find_project_root()
        config_path = app_project_root / "config" / "model_providers.yaml"
        ProviderManager.load_providers(config_path)
        logger.info("   ✓ 模型供应商配置加载完成")

        # 2. 初始化工具注册表
        logger.info("2. 初始化工具注册表...")
        init_tools()
        logger.info("   ✓ 工具注册表初始化完成")

        # 3. 扫描流程文件
        logger.info("3. 扫描流程文件...")
        flows = FlowManager.scan_flows()
        logger.info(f"   ✓ 扫描到 {len(flows)} 个流程定义")

        # 4. 预加载规则二流程
        logger.info("4. 预加载规则二流程...")
        loader_config = FlowManager.get_flow_loader_config()
        preload_flows = loader_config.get("preload", [])
        if preload_flows:
            FlowManager.preload_flows(preload_flows)
            logger.info(f"   ✓ 成功预加载 {len(preload_flows)} 个流程")
        else:
            logger.info("   ✓ 没有需要预加载的流程")

        # 5. 可选：应用内启动 radar_score event worker
        if settings.RADAR_SCORE_WORKER_IN_APP:
            logger.info("5. 启动 radar_score event 调度（应用内）...")
            try:
                from radar_score.in_app import start_radar_score_in_app

                radar_score_stop, radar_score_threads = start_radar_score_in_app()
                logger.info("   ✓ radar_score 已在后台线程启动")
            except Exception as exc:
                logger.error(
                    "   ✗ radar_score 启动失败（不阻断 API）：%s",
                    exc,
                    exc_info=True,
                )
        else:
            logger.info(
                "5. 跳过 radar_score 应用内调度"
                "（RADAR_SCORE_WORKER_IN_APP=false；可用 python -m radar_score）"
            )

        # 6. AnySearch 凭证池：加载 DB 快照 + 后台定时刷新（可选工具，未挂 flow，不阻断 API）
        try:
            from backend.domain.tools.anysearch.pool import get_anysearch_pool

            anysearch_pool = get_anysearch_pool()
            _as_snap = anysearch_pool.reload(force=True)
            anysearch_pool.start_background()
            logger.info(
                "6. AnySearch 池就绪 source=%s keys=%d（DB 热配置，后台刷新中）",
                _as_snap.source,
                len(_as_snap.keys),
            )
        except Exception as as_exc:
            logger.warning("6. AnySearch 池初始化失败（不阻断 API）：%s", as_exc)

        logger.info("=" * 60)
        logger.info("规则二评分服务启动完成！")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"系统启动失败: {e}", exc_info=True)
        raise

    yield  # 应用运行期间

    # 关闭时：停止评分调度
    if radar_score_stop is not None and radar_score_threads is not None:
        from radar_score.in_app import stop_radar_score_in_app

        stop_radar_score_in_app(radar_score_stop, radar_score_threads)

    # 关闭 AnySearch 池：停后台刷新并释放租约
    if anysearch_pool is not None:
        try:
            anysearch_pool.stop_background()
            await anysearch_pool.release_all()
            logger.info("AnySearch 池已停止并释放租约")
        except Exception as as_exc:
            logger.warning("AnySearch 池停止异常: %s", as_exc)

    logger.info("系统正在关闭...")


app = FastAPI(title="华院规则二评分服务", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    """根路径。"""
    return {
        "message": "华院规则二评分服务",
        "status": "running",
        "routes": ["/api/v1/huayuan/radar-event-score"],
    }


@app.get("/health")
async def health():
    """健康检查。"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        reload_dirs=[str(project_root)] if project_root.exists() else None,
    )
