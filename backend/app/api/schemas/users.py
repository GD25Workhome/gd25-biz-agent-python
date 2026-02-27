"""
用户相关Schema
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """创建用户请求"""
    user_name: str = Field(min_length=1, max_length=100, description="用户名（1-100字符）")
    user_info: Optional[str] = Field(None, description="用户信息（JSON格式字符串）")


class UserUpdate(BaseModel):
    """更新用户请求"""
    user_name: Optional[str] = Field(None, min_length=1, max_length=100, description="用户名")
    user_info: Optional[str] = Field(None, description="用户信息（JSON格式字符串）")


class UserResponse(BaseModel):
    """用户响应"""
    id: str
    user_name: str
    user_info: Optional[dict] = None
    created_at: datetime
    updated_at: Optional[datetime]
    # 前端兼容字段
    username: Optional[str] = Field(None, description="用户名（前端兼容字段，等于user_name）")
    phone: Optional[str] = Field(None, description="手机号（前端兼容字段）")
    email: Optional[str] = Field(None, description="邮箱（前端兼容字段）")
    
    class Config:
        from_attributes = True  # 允许从ORM模型创建
        
    @classmethod
    def from_orm_with_compat(cls, obj):
        """从ORM对象创建响应对象，添加前端兼容字段"""
        data = {
            "id": obj.id,
            "user_name": obj.user_name,
            "username": obj.user_name,  # 前端兼容字段
            "user_info": obj.user_info,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
            "phone": None,  # 前端兼容字段
            "email": None,  # 前端兼容字段
        }
        return cls(**data)


class UserListResponse(BaseModel):
    """用户列表响应"""
    users: list[UserResponse] = Field(description="用户列表")

