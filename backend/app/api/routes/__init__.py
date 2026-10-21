"""
API 路由模块（规则二最小集）

只注册展厅项目需求评分路由。
"""
from fastapi import APIRouter

from backend.app.api.routes.huayuan_radar_event import (
    router as huayuan_radar_event_router,
)

# 创建主路由
router = APIRouter()

# 注册规则二评分路由（统一添加 /api/v1 前缀）
router.include_router(
    huayuan_radar_event_router,
    prefix="/api/v1",
    tags=["华院规则二"],
)

__all__ = ["router"]
