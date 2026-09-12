"""
API路由模块
华院最小部署：仅注册 chat / portrait / radar 三条路由。
"""
from fastapi import APIRouter

from backend.app.api.routes.huayuan_chat import router as huayuan_chat_router
from backend.app.api.routes.huayuan_portrait import router as huayuan_portrait_router
from backend.app.api.routes.huayuan_radar_event import router as huayuan_radar_event_router

# 创建主路由
router = APIRouter()

# 注册华院子路由（统一添加 /api/v1 前缀）
router.include_router(huayuan_chat_router, prefix="/api/v1", tags=["华院联通"])
router.include_router(huayuan_portrait_router, prefix="/api/v1", tags=["华院联通"])
router.include_router(huayuan_radar_event_router, prefix="/api/v1", tags=["华院联通"])

__all__ = ["router"]
