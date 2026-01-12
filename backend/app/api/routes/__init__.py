"""
API路由模块
聚合所有子路由
"""
from fastapi import APIRouter

from backend.app.api.routes.chat import router as chat_router
from backend.app.api.routes.blood_pressure import router as blood_pressure_router
from backend.app.api.routes.users import router as users_router
from backend.app.api.routes.login import router as login_router

# 创建主路由
router = APIRouter()

# 注册子路由（统一添加 /api/v1 前缀）
router.include_router(chat_router, prefix="/api/v1", tags=["聊天"])
router.include_router(blood_pressure_router, prefix="/api/v1", tags=["血压记录"])
router.include_router(users_router, prefix="/api/v1", tags=["用户管理"])
router.include_router(login_router, prefix="/api/v1", tags=["登录"])

__all__ = ["router"]

