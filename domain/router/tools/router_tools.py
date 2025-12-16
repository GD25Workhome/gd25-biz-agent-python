"""
路由工具：意图识别和澄清
"""
from typing import Dict, Any, Optional
import json
import logging
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate

from domain.router.state import IntentResult
from infrastructure.llm.client import get_llm

logger = logging.getLogger(__name__)

# 意图识别系统提示词
INTENT_IDENTIFICATION_PROMPT = """你是一个智能路由助手，负责识别用户的真实意图。

支持的意图类型：
1. blood_pressure: 用户想要记录、查询或管理血压数据
   - 关键词：血压、收缩压、舒张压、高压、低压、记录血压、查询血压、血压记录、血压数据、心率
   - 示例："我想记录血压"、"查询我的血压记录"、"更新血压数据"、"我的收缩压是120，舒张压是80"

2. appointment: 用户想要预约、查询或管理复诊
   - 关键词：预约、复诊、挂号、就诊、看病、门诊、预约医生、预约时间、取消预约
   - 示例："我想预约复诊"、"查询我的预约"、"取消预约"、"帮我挂个号"

3. unclear: 意图不明确，需要进一步澄清
   - 当用户的消息无法明确归类到上述两种意图时
   - 示例："你好"、"在吗"、"有什么功能"、"谢谢"

请分析用户消息和对话历史，返回JSON格式的意图识别结果：
{{
    "intent_type": "意图类型（blood_pressure/appointment/unclear）",
    "confidence": 置信度（0.0-1.0之间的浮点数）,
    "entities": {{}},
    "need_clarification": 是否需要澄清（true/false）,
    "reasoning": "识别理由"
}}

规则：
- 如果意图明确且置信度>0.8，设置need_clarification=false
- 如果意图不明确（置信度<0.8），设置need_clarification=true
- 如果用户同时提及多个意图，按优先级选择（优先级：appointment > blood_pressure）
- 如果用户的消息很短（如"你好"、"在吗"），且当前有活跃的智能体，可能继续当前意图
- 如果对话历史中有明确的意图上下文，应该考虑上下文信息
"""


def _extract_conversation_context(messages: list[BaseMessage]) -> tuple[str, str]:
    """
    从消息列表中提取当前用户消息和对话历史
    
    Args:
        messages: 消息列表
        
    Returns:
        tuple: (当前用户消息, 对话历史文本)
    """
    if not messages:
        return "", ""
    
    # 获取最后一条用户消息
    last_message = messages[-1]
    current_query = ""
    if isinstance(last_message, HumanMessage):
        current_query = last_message.content if hasattr(last_message, 'content') else str(last_message)
    elif hasattr(last_message, 'content'):
        current_query = last_message.content
    else:
        current_query = str(last_message)
    
    # 构建对话历史（排除最后一条消息）
    history_parts = []
    for msg in messages[:-1]:
        if isinstance(msg, HumanMessage):
            content = msg.content if hasattr(msg, 'content') else str(msg)
            history_parts.append(f"用户: {content}")
        elif isinstance(msg, AIMessage):
            content = msg.content if hasattr(msg, 'content') else str(msg)
            history_parts.append(f"助手: {content}")
        elif hasattr(msg, 'content'):
            history_parts.append(f"消息: {msg.content}")
    
    history_text = "\n".join(history_parts) if history_parts else "无"
    
    return current_query, history_text


def _get_current_intent_from_state(messages: list[BaseMessage]) -> Optional[str]:
    """
    从消息列表中推断当前意图（基于对话历史）
    
    Args:
        messages: 消息列表
        
    Returns:
        当前意图类型，如果无法推断则返回 None
    """
    # 如果消息很少，无法推断
    if len(messages) < 2:
        return None
    
    # 检查最近的对话是否围绕某个主题
    # 这里可以进一步优化，但为了简化，暂时返回 None
    return None


def _parse_intent_result(llm_response: str) -> IntentResult:
    """
    解析LLM返回的意图识别结果
    
    Args:
        llm_response: LLM 返回的文本响应
        
    Returns:
        IntentResult: 解析后的意图识别结果
    """
    try:
        # 尝试提取JSON部分
        json_start = llm_response.find('{')
        json_end = llm_response.rfind('}') + 1
        
        if json_start == -1 or json_end == 0:
            logger.warning(f"无法找到JSON部分，返回默认结果。响应: {llm_response}")
            return IntentResult(
                intent_type="unclear",
                confidence=0.0,
                entities={},
                need_clarification=True,
                reasoning="无法解析LLM响应"
            )
        
        json_str = llm_response[json_start:json_end]
        data = json.loads(json_str)
        
        # 验证并创建IntentResult
        intent_type = data.get("intent_type", "unclear")
        valid_intents = ["blood_pressure", "appointment", "unclear"]
        if intent_type not in valid_intents:
            logger.warning(f"无效的意图类型: {intent_type}，使用unclear")
            intent_type = "unclear"
        
        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))  # 限制在0-1之间
        
        # 根据置信度自动设置 need_clarification
        need_clarification = data.get("need_clarification")
        if need_clarification is None:
            need_clarification = confidence < 0.8
        
        return IntentResult(
            intent_type=intent_type,
            confidence=confidence,
            entities=data.get("entities", {}),
            need_clarification=need_clarification,
            reasoning=data.get("reasoning", "")
        )
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {str(e)}，响应: {llm_response}")
        return IntentResult(
            intent_type="unclear",
            confidence=0.0,
            entities={},
            need_clarification=True,
            reasoning=f"JSON解析失败: {str(e)}"
        )
    except Exception as e:
        logger.error(f"解析意图识别结果失败: {str(e)}")
        return IntentResult(
            intent_type="unclear",
            confidence=0.0,
            entities={},
            need_clarification=True,
            reasoning=f"解析失败: {str(e)}"
        )


@tool
def identify_intent(messages: list[BaseMessage]) -> Dict[str, Any]:
    """
    识别用户意图（使用 LLM 进行智能识别）
    
    支持的意图类型：
    - blood_pressure: 血压相关（记录、查询、更新血压）
    - appointment: 预约相关（创建、查询、更新预约）
    - unclear: 意图不明确
    
    Args:
        messages: 消息列表，包含用户输入和对话历史
        
    Returns:
        意图识别结果字典，包含：
        - intent_type: 意图类型
        - confidence: 置信度（0.0-1.0）
        - entities: 提取的实体信息
        - need_clarification: 是否需要澄清
        - reasoning: 识别理由
    """
    try:
        # 处理空消息列表
        if not messages:
            logger.warning("收到空消息列表")
            return IntentResult(
                intent_type="unclear",
                confidence=0.0,
                entities={},
                need_clarification=True,
                reasoning="没有输入消息"
            ).model_dump()
        
        # 提取对话上下文
        current_query, history_text = _extract_conversation_context(messages)
        current_intent = _get_current_intent_from_state(messages)
        current_intent_text = current_intent if current_intent else "无"
        
        # 如果当前查询为空，返回 unclear
        if not current_query or not current_query.strip():
            logger.warning("当前查询为空")
            return IntentResult(
                intent_type="unclear",
                confidence=0.0,
                entities={},
                need_clarification=True,
                reasoning="当前查询为空"
            ).model_dump()
        
        # 构建提示词
        prompt = ChatPromptTemplate.from_messages([
            ("system", INTENT_IDENTIFICATION_PROMPT),
            ("human", """用户消息: {query}

对话历史: {history}

当前意图: {current_intent}

请识别用户的真实意图，返回JSON格式的结果。""")
        ])
        
        # 调用LLM（使用较低的温度以确保稳定性）
        llm = get_llm(temperature=0.0)
        chain = prompt | llm
        response = chain.invoke({
            "query": current_query,
            "history": history_text,
            "current_intent": current_intent_text
        })
        
        # 解析响应
        llm_text = response.content if hasattr(response, 'content') else str(response)
        intent_result = _parse_intent_result(llm_text)
        
        logger.info(
            f"意图识别结果: {intent_result.intent_type}, "
            f"置信度: {intent_result.confidence}, "
            f"需要澄清: {intent_result.need_clarification}"
        )
        
        # 返回字典格式（工具需要返回可序列化的字典）
        return intent_result.model_dump()
        
    except Exception as e:
        logger.error(f"意图识别失败: {str(e)}", exc_info=True)
        # 返回默认结果
        default_result = IntentResult(
            intent_type="unclear",
            confidence=0.0,
            entities={},
            need_clarification=True,
            reasoning=f"意图识别异常: {str(e)}"
        )
        return default_result.model_dump()


# 意图澄清提示词
CLARIFY_INTENT_PROMPT = """你是一个友好的助手，当用户的意图不明确时，你需要友好地引导用户说明他们的需求。

系统支持的功能：
1. 记录血压：帮助用户记录、查询和管理血压数据（收缩压、舒张压、心率等）
2. 预约复诊：帮助用户创建、查询和管理预约（科室、时间、医生等）

用户消息: {query}

请生成一个友好的澄清问题，引导用户说明他们的具体需求。
**重要要求**：
- 澄清问题必须明确提到两种功能：记录血压、预约复诊
- 问题应该简洁明了，不超过100字
- 使用友好、专业的语言
- 不要使用技术术语，使用用户容易理解的语言
"""


@tool
def clarify_intent(query: str) -> str:
    """
    生成意图澄清问题
    
    当用户意图不明确时，生成友好的澄清问题引导用户说明需求。
    
    Args:
        query: 用户查询内容
        
    Returns:
        str: 澄清问题文本
    """
    try:
        # 构建提示词
        prompt = ChatPromptTemplate.from_messages([
            ("system", CLARIFY_INTENT_PROMPT),
            ("human", "用户消息: {query}\n\n请生成澄清问题。")
        ])
        
        # 调用LLM（使用稍高的温度以生成更友好的问题）
        llm = get_llm(temperature=0.3)
        chain = prompt | llm
        response = chain.invoke({"query": query})
        
        clarification = response.content if hasattr(response, 'content') else str(response)
        clarification = clarification.strip()
        
        # 验证澄清问题是否包含关键功能
        if "血压" not in clarification and "预约" not in clarification:
            logger.warning(f"生成的澄清问题可能不完整: {clarification}")
            # 如果生成的澄清问题不包含关键功能，使用默认问题
            clarification = "抱歉，我没有理解您的意图。请告诉我您是想记录血压、预约复诊，还是需要其他帮助？"
        
        logger.info(f"生成澄清问题: {clarification}")
        
        return clarification
        
    except Exception as e:
        logger.error(f"生成澄清问题失败: {str(e)}", exc_info=True)
        # 返回默认澄清问题
        default_clarification = "抱歉，我没有理解您的意图。请告诉我您是想记录血压、预约复诊，还是需要其他帮助？"
        return default_clarification

