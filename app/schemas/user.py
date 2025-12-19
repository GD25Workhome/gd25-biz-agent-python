"""
用户接口的请求和响应模型
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., description="用户名", min_length=1, max_length=100)
    phone: Optional[str] = Field(default=None, description="手机号", max_length=20)
    email: Optional[str] = Field(default=None, description="邮箱", max_length=100)
    is_active: bool = Field(default=True, description="是否激活")


class UserCreate(UserBase):
    """创建用户请求模型"""
    pass


class UserUpdate(BaseModel):
    """更新用户请求模型"""
    username: Optional[str] = Field(default=None, description="用户名", min_length=1, max_length=100)
    phone: Optional[str] = Field(default=None, description="手机号", max_length=20)
    email: Optional[str] = Field(default=None, description="邮箱", max_length=100)
    is_active: Optional[bool] = Field(default=None, description="是否激活")


class UserResponse(UserBase):
    """用户响应模型"""
    id: str = Field(..., description="用户ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    
    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """用户列表响应模型"""
    users: list[UserResponse] = Field(..., description="用户列表")
    total: int = Field(..., description="总数")
