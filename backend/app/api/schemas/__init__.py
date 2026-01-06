"""
API Schema模块
导出所有Schema类
"""
from backend.app.api.schemas.chat import ChatRequest, ChatResponse
from backend.app.api.schemas.blood_pressure import (
    BloodPressureRecordCreate,
    BloodPressureRecordUpdate,
    BloodPressureRecordResponse,
)
from backend.app.api.schemas.users import (
    UserCreate,
    UserUpdate,
    UserResponse,
)

__all__ = [
    # 聊天相关
    "ChatRequest",
    "ChatResponse",
    # 血压记录相关
    "BloodPressureRecordCreate",
    "BloodPressureRecordUpdate",
    "BloodPressureRecordResponse",
    # 用户相关
    "UserCreate",
    "UserUpdate",
    "UserResponse",
]

