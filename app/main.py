"""
FastAPI 应用入口
"""
import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path

# 确保项目根目录在 Python 路径中，支持直接运行此文件
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# 配置日志系统
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 设置 uvicorn 日志级别
logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore

from app.api.routes import router
from app.core.config import settings
from app.middleware.logging import LoggingMiddleware
from app.middleware.exception_handler import (
    exception_handler,
    validation_exception_handler,
    http_exception_handler
)
from domain.router.graph import create_router_graph
from infrastructure.database.connection import create_db_pool


def normalize_postgres_uri(uri: str) -> str:
    """
    规范化 PostgreSQL 连接 URI
    
    将 SQLAlchemy 格式（postgresql+psycopg://）转换为标准 PostgreSQL URI 格式（postgresql://）
    psycopg_pool.AsyncConnectionPool 需要标准的 PostgreSQL URI 格式
    
    Args:
        uri: 原始连接 URI
        
    Returns:
        规范化后的连接 URI
    """
    # 将 postgresql+psycopg:// 或 postgresql+asyncpg:// 转换为 postgresql://
    if uri.startswith("postgresql+psycopg://"):
        return uri.replace("postgresql+psycopg://", "postgresql://", 1)
    elif uri.startswith("postgresql+asyncpg://"):
        return uri.replace("postgresql+asyncpg://", "postgresql://", 1)
    # 如果已经是标准格式，直接返回
    return uri


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    
    Args:
        app: FastAPI 应用实例
    """
    # Startup
    print("正在启动应用...")
    
    checkpointer_pool = None
    db_pool = None
    
    try:
        # 规范化 Checkpointer 数据库连接 URI（确保使用标准 PostgreSQL URI 格式）
        checkpointer_uri = normalize_postgres_uri(settings.CHECKPOINTER_DB_URI)
        
        # 初始化数据库连接池（用于 Checkpointer）
        # 注意：AsyncPostgresStore 需要 dict_row 格式，以便通过列名访问行数据
        # 使用推荐的上下文管理器方式，避免废弃警告
        checkpointer_pool = AsyncConnectionPool(
            conninfo=checkpointer_uri,
            max_size=20,
            kwargs={
                "autocommit": True,
                "row_factory": dict_row  # 设置为字典格式，支持通过列名访问
            },
            open=False  # 手动控制打开，避免废弃警告
        )
        await checkpointer_pool.open()
        
        # 初始化业务数据库连接池
        db_pool = await create_db_pool()
        
        # 初始化 Checkpointer
        checkpointer = AsyncPostgresSaver(checkpointer_pool)
        await checkpointer.setup()
        
        # 初始化 Store（长期记忆）
        store = AsyncPostgresStore(checkpointer_pool)
        await store.setup()
        
        # 创建路由图
        router_graph = create_router_graph(
            checkpointer=checkpointer,
            pool=db_pool,
            store=store
        )
        
        # 存储到 app.state
        app.state.checkpointer_pool = checkpointer_pool
        app.state.db_pool = db_pool
        app.state.checkpointer = checkpointer
        app.state.store = store
        app.state.router_graph = router_graph
        
        # 构建访问 URL（如果 host 是 0.0.0.0，则显示为 localhost，因为浏览器无法访问 0.0.0.0）
        display_host = "localhost" if settings.APP_HOST == "0.0.0.0" else settings.APP_HOST
        chat_url = f"http://{display_host}:{settings.APP_PORT}/web/chat.html"
        print(f"应用启动完成 （{chat_url}）")
        
        yield
        
    finally:
        # Shutdown
        print("正在关闭应用...")
        if checkpointer_pool:
            try:
                await checkpointer_pool.close()
            except Exception as e:
                print(f"关闭 Checkpointer 连接池时出错: {e}")
        
        if db_pool:
            try:
                await db_pool.close()
            except Exception as e:
                print(f"关闭业务数据库连接池时出错: {e}")
        
        print("应用已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="LangGraphFlow Multi-Agent Router",
    description="多智能体路由系统 V2.0",
    version="2.0.0",
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加日志中间件
app.add_middleware(LoggingMiddleware)

# 注册异常处理器
app.add_exception_handler(Exception, exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

# 注册路由
app.include_router(router, prefix="/api/v1")

# 挂载静态资源，用于提供简易前端页面
static_dir = Path(__file__).resolve().parent.parent / "web"
app.mount(
    "/web",
    StaticFiles(directory=str(static_dir), html=True),
    name="web"
)


@app.get("/health")
def health_check():
    """
    健康检查接口
    
    Returns:
        健康状态信息
    """
    return {
        "status": "ok",
        "version": "2.0.0"
    }


def run_server() -> None:
    """
    通过 uvicorn 启动服务，端口与主机从 .env 读取
    """
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.DEBUG
    )


if __name__ == "__main__":
    run_server()

