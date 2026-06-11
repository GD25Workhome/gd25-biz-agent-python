"""
系统级路由（健康检查、根路径）
"""
from fastapi import APIRouter

router = APIRouter(tags=["系统"])


@router.get("/")
async def root() -> dict:
    """根路径"""
    return {"message": "动态流程系统 MVP", "status": "running"}


@router.get("/health")
async def health() -> dict:
    """健康检查"""
    return {"status": "healthy"}
