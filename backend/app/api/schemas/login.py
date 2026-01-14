"""
登录相关Schema
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from backend.domain.flows.manager import FlowManager


def _get_flow_names_description() -> str:
    """
    获取流程名称描述（从 flow_loader.yaml 配置中读取）
    
    Returns:
        str: 流程名称描述字符串
    """
    try:
        config = FlowManager.get_flow_loader_config()
        all_flows = config.get("preload", []) + config.get("lazy_load", [])
        if all_flows:
            flow_list = "、".join(all_flows)
            return f"流程名称（支持的流程：{flow_list}，参考 config/flow_loader.yaml 配置）"
        else:
            return "流程名称（参考 config/flow_loader.yaml 配置）"
    except Exception:
        # 如果读取配置失败，使用通用描述
        return "流程名称（参考 config/flow_loader.yaml 配置）"


class CreateTokenRequest(BaseModel):
    """创建Token请求"""
    user_id: str = Field(..., description="用户ID")


class CreateTokenResponse(BaseModel):
    """创建Token响应"""
    token_id: str = Field(..., description="Token ID")


class CreateSessionRequest(BaseModel):
    """创建Session请求"""
    user_id: str = Field(..., description="用户ID")
    flow_name: str = Field(..., description=_get_flow_names_description())


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

