"""
登录相关Schema
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class CreateTokenRequest(BaseModel):
    """创建Token请求"""
    user_id: str = Field(..., description="用户ID")


class CreateTokenResponse(BaseModel):
    """创建Token响应"""
    token_id: str = Field(..., description="Token ID")


class CreateSessionRequest(BaseModel):
    """创建Session请求"""
    user_id: str = Field(..., description="用户ID")
    flow_name: str = Field(..., description="流程名称（medical_agent 或 work_plan_agent）")


class CreateSessionResponse(BaseModel):
    """创建Session响应"""
    session_id: str = Field(..., description="Session ID")


class TokenInfoResponse(BaseModel):
    """Token信息响应"""
    token_id: str = Field(..., description="Token ID")
    user_id: str = Field(..., description="用户ID")
    user_info: Optional[Dict[str, Any]] = Field(None, description="用户信息")


class SessionInfoResponse(BaseModel):
    """Session信息响应"""
    session_id: str = Field(..., description="Session ID")
    user_id: str = Field(..., description="用户ID")
    flow_info: Dict[str, str] = Field(..., description="流程信息（包含flow_key和flow_name）")
    doctor_info: Dict[str, str] = Field(..., description="医生信息（包含doctor_id和doctor_name）")

