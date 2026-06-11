"""
FastAPI 应用生命周期管理
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.bootstrap import ApplicationBootstrap

logger = logging.getLogger(__name__)
_bootstrap = ApplicationBootstrap()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期上下文（替代已弃用的 on_event）。

    启动与关闭逻辑委托给 ApplicationBootstrap。
    """
    try:
        await _bootstrap.startup()
    except Exception as e:
        logger.error("系统启动失败: %s", e, exc_info=True)
        raise

    yield

    await _bootstrap.shutdown()
