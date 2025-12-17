"""
路由智能体状态定义
定义 RouterState 和 IntentResult 数据结构
"""
from typing import TypedDict, List, Optional, Dict, Any, NotRequired
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


class BloodPressureForm(TypedDict, total=False):
    """血压记录表单槽位，显式记录已收集/待收集字段"""
    systolic: NotRequired[int]  # 收缩压（必填）
    diastolic: NotRequired[int]  # 舒张压（必填）
    heart_rate: NotRequired[int]  # 心率（可选）
    record_time: NotRequired[str]  # 记录时间（可选，ISO 格式）
    notes: NotRequired[str]  # 备注（可选）


class RouterState(TypedDict):
    """路由状态数据结构"""
    messages: List[BaseMessage]  # 消息列表
    current_intent: Optional[str]  # 当前意图：blood_pressure, appointment, unclear
    current_agent: Optional[str]  # 当前活跃的智能体名称
    need_reroute: bool  # 是否需要重新路由
    session_id: str  # 会话ID
    user_id: str  # 用户ID
    bp_form: NotRequired[BloodPressureForm]  # 血压表单槽位（显式槽位）


class IntentResult(BaseModel):
    """意图识别结果"""
    intent_type: str  # "blood_pressure", "appointment", "unclear"
    confidence: float = Field(ge=0.0, le=1.0, description="置信度，范围 0.0-1.0")  # 0.0-1.0
    entities: Dict[str, Any]  # 提取的实体信息
    need_clarification: bool  # 是否需要澄清
    reasoning: Optional[str] = None  # 识别理由（可选）
    
