"""
FastAPI 应用工厂
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router as api_router
from backend.app.api.routes.system import router as system_router
from backend.app.config import find_project_root
from backend.app.lifespan import lifespan
from backend.app.logging_config import setup_logging
from backend.app.middleware import setup_cors


def create_app() -> FastAPI:
    """
    创建并配置 FastAPI 应用实例。

    Returns:
        FastAPI: 已完成路由、中间件、静态资源挂载的应用实例
    """
    setup_logging()

    app = FastAPI(
        title="动态流程系统 MVP",
        version="1.0.0",
        lifespan=lifespan,
    )

    setup_cors(app)

    app.include_router(system_router)
    app.include_router(api_router)

    frontend_dir = find_project_root() / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    return app
