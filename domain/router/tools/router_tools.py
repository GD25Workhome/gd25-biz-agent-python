"""
路由工具：意图识别
"""
from typing import Dict, Any
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage

from domain.router.state import IntentResult


@tool
def identify_intent(messages: list[BaseMessage]) -> Dict[str, Any]:
    """
    识别用户意图
    
    支持的意图类型：
    - blood_pressure: 血压相关（记录、查询、更新血压）
    - appointment: 预约相关（创建、查询、更新预约）
    - unclear: 意图不明确
    
    Args:
        messages: 消息列表，包含用户输入
        
    Returns:
        意图识别结果字典，包含：
        - intent_type: 意图类型
        - confidence: 置信度（0.0-1.0）
        - entities: 提取的实体信息
        - need_clarification: 是否需要澄清
        - reasoning: 识别理由
    """
    # 简化版实现：基于关键词匹配
    # 后续可以使用 LLM 进行更智能的意图识别
    
    if not messages:
        return {
            "intent_type": "unclear",
            "confidence": 0.0,
            "entities": {},
            "need_clarification": True,
            "reasoning": "没有输入消息"
        }
    
    # 获取最后一条用户消息
    last_message = messages[-1]
    if hasattr(last_message, 'content'):
        content = last_message.content.lower()
    else:
        content = str(last_message).lower()
    
    # 关键词匹配
    blood_pressure_keywords = ["血压", "高压", "低压", "收缩压", "舒张压", "心率"]
    appointment_keywords = ["预约", "挂号", "复诊", "就诊", "看病"]
    
    blood_pressure_score = sum(1 for keyword in blood_pressure_keywords if keyword in content)
    appointment_score = sum(1 for keyword in appointment_keywords if keyword in content)
    
    if blood_pressure_score > 0 and blood_pressure_score >= appointment_score:
        return {
            "intent_type": "blood_pressure",
            "confidence": min(0.9, 0.5 + blood_pressure_score * 0.1),
            "entities": {},
            "need_clarification": False,
            "reasoning": f"检测到血压相关关键词（匹配{blood_pressure_score}个）"
        }
    elif appointment_score > 0:
        return {
            "intent_type": "appointment",
            "confidence": min(0.9, 0.5 + appointment_score * 0.1),
            "entities": {},
            "need_clarification": False,
            "reasoning": f"检测到预约相关关键词（匹配{appointment_score}个）"
        }
    else:
        return {
            "intent_type": "unclear",
            "confidence": 0.3,
            "entities": {},
            "need_clarification": True,
            "reasoning": "未检测到明确的意图关键词"
        }

