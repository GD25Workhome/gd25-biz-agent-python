"""
FastAPI应用入口

运行方式：
    方式1（推荐）：直接运行
        python backend/main.py
    
    方式2：使用 uvicorn 命令
        uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

访问地址：
    http://localhost:8000/static/index.html

说明：
    FastAPI 应用需要通过 ASGI 服务器（如 uvicorn）运行。
    直接运行 main.py 时，会自动启动 uvicorn 服务器。
    使用 uvicorn 命令可以更好地控制配置，适合生产环境。
"""
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager

# 添加项目根目录到 Python 路径（必须在导入 backend 模块之前）
# 使用绝对路径，确保无论从哪个目录运行都能正常工作
_file_path = Path(__file__).resolve()  # 获取文件的绝对路径
project_root = _file_path.parent.parent  # backend/main.py -> backend -> 项目根目录

# 确保项目根目录在 sys.path 中（避免重复添加）
project_root_str = str(project_root)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.infrastructure.llm.providers.manager import ProviderManager
from backend.domain.flows.manager import FlowManager
from backend.domain.tools import init_tools
from backend.app.config import find_project_root

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理（替代已弃用的 on_event）"""
    # 启动时执行
    logger.info("=" * 60)
    logger.info("系统启动中...")
    logger.info("=" * 60)
    
    try:
        # 1. 加载模型供应商配置
        logger.info("1. 加载模型供应商配置...")
        app_project_root = find_project_root()
        config_path = app_project_root / "config" / "model_providers.yaml"
        ProviderManager.load_providers(config_path)
        logger.info(f"   ✓ 成功加载模型供应商配置")
        
        # 2. 初始化工具注册表
        logger.info("2. 初始化工具注册表...")
        init_tools()
        logger.info(f"   ✓ 工具注册表初始化完成")
        
        # 3. 扫描流程文件
        logger.info("3. 扫描流程文件...")
        flows = FlowManager.scan_flows()
        logger.info(f"   ✓ 扫描到 {len(flows)} 个流程定义")
        
        # 4. 预加载常用流程
        logger.info("4. 预加载常用流程...")
        loader_config = FlowManager.get_flow_loader_config()
        preload_flows = loader_config.get("preload", [])
        if preload_flows:
            FlowManager.preload_flows(preload_flows)
            logger.info(f"   ✓ 成功预加载 {len(preload_flows)} 个流程")
        else:
            logger.info("   ✓ 没有需要预加载的流程")
        
        logger.info("=" * 60)
        logger.info("系统启动完成！")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"系统启动失败: {e}", exc_info=True)
        raise
    
    yield  # 应用运行期间
    
    # 关闭时执行（如果需要）
    logger.info("系统正在关闭...")


# 创建FastAPI应用，使用新的 lifespan 事件处理器
app = FastAPI(title="动态流程系统 MVP", version="1.0.0", lifespan=lifespan)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router)

# 配置静态文件服务（前端文件）
frontend_dir = project_root / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.get("/")
async def root():
    """根路径"""
    return {"message": "动态流程系统 MVP", "status": "running"}


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}


if __name__ == "__main__":
    """
    直接运行此文件时启动开发服务器
    
    使用方式：
        方式1（推荐）：从项目根目录运行
            python backend/main.py
        
        方式2：使用模块方式运行
            python -m backend.main
        
        方式3：继续使用 uvicorn 命令（生产环境推荐）
            uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
    
    注意：
        - 直接运行时会自动启用 reload 模式（开发模式）
        - 生产环境建议使用 uvicorn 命令，可以更好地控制配置
    """
    import uvicorn
    
    # 确保项目根目录在 Python 路径中（uvicorn 重新导入时需要）
    # 使用字符串形式让 uvicorn 处理导入，它会自动处理路径
    uvicorn.run(
        "backend.main:app",  # 使用字符串形式，uvicorn 会重新导入模块
        host="0.0.0.0",
        port=8000,
        reload=True,  # 开发模式：代码变更时自动重启
        log_level="info",
        reload_dirs=[str(project_root)] if project_root.exists() else None,  # 指定监听目录
    )

