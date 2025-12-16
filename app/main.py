"""
FastAPI 应用入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from psycopg_pool import AsyncConnectionPool
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    
    Args:
        app: FastAPI 应用实例
    """
    # Startup
    print("正在启动应用...")
    
    # 初始化数据库连接池（用于 Checkpointer）
    checkpointer_pool = AsyncConnectionPool(
        conninfo=settings.CHECKPOINTER_DB_URI,
        max_size=20,
        kwargs={"autocommit": True}
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
    
    print("应用启动完成")
    
    yield
    
    # Shutdown
    print("正在关闭应用...")
    await checkpointer_pool.close()
    await db_pool.close()
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

