"""
路由智能体状态定义
定义 RouterState 和 IntentResult 数据结构
"""
from typing import TypedDict, List, Optional, Dict, Any
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


class RouterState(TypedDict, total=False):
    """路由状态数据结构"""
    messages: List[BaseMessage]  # 消息列表
    current_intent: Optional[str]  # 当前意图：blood_pressure, health_event, medication, symptom, unclear
    current_agent: Optional[str]  # 当前活跃的智能体名称
    need_reroute: bool  # 是否需要重新路由
    session_id: str  # 会话ID
    token_id: str  # 令牌ID（当前阶段等于用户ID，未来可扩展为业务系统令牌）
    trace_id: Optional[str]  # Langfuse Trace ID（用于链路追踪）
    user_info: Optional[str]  # 患者基础信息（多行文本）
    history_msg: Optional[str]  # 历史对话信息（格式化文本，由API层从conversation_history生成）
    current_date: Optional[str]  # 当前日期时间（格式：YYYY-MM-DD HH:mm，可选，如果不提供则使用系统当前时间）


class IntentResult(BaseModel):
    """意图识别结果"""
    intent_type: str  # "blood_pressure", "health_event", "medication", "symptom", "unclear"
    confidence: float = Field(ge=0.0, le=1.0, description="置信度，范围 0.0-1.0")  # 0.0-1.0
    entities: Dict[str, Any]  # 提取的实体信息
    need_clarification: bool  # 是否需要澄清
    reasoning: Optional[str] = None  # 识别理由（可选）
    
