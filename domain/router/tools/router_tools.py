"""
路由工具：意图识别和澄清

提示词统一从 Langfuse 加载，如果获取失败则抛出异常。

路由工具提示词模版名称（Langfuse）：
- router_intent_identification_prompt：意图识别
- router_clarify_intent_prompt：意图澄清
"""
from typing import Dict, Any, Optional
import json
import logging
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from domain.router.state import IntentResult
from infrastructure.llm.client import get_llm
from infrastructure.prompts.langfuse_adapter import LangfusePromptAdapter
from infrastructure.prompts.placeholder import PlaceholderManager

logger = logging.getLogger(__name__)

# Langfuse 提示词适配器实例（单例）
_langfuse_adapter = None


def _get_langfuse_adapter() -> LangfusePromptAdapter:
    """获取 Langfuse 适配器实例（单例）"""
    global _langfuse_adapter
    if _langfuse_adapter is None:
        _langfuse_adapter = LangfusePromptAdapter()
    return _langfuse_adapter


def _load_router_prompt(template_name: str, context: Dict[str, Any]) -> str:
    """
    从 Langfuse 加载路由工具提示词
    
    Args:
        template_name: Langfuse模版名称（如 "router_intent_identification_prompt"）
        context: 上下文信息（用于占位符填充）
        
    Returns:
        填充后的提示词内容
        
    Raises:
        ValueError: Langfuse未启用或配置不完整
        ConnectionError: 无法从Langfuse获取模版
    """
    # 从 Langfuse 获取模版
    adapter = _get_langfuse_adapter()
    template = adapter.get_template(
        template_name=template_name,
        version=None
    )
    
    # 填充占位符
    placeholders = PlaceholderManager.get_placeholders("router_tools", state=None)
    placeholders.update(context)
    prompt_template = PlaceholderManager.fill_placeholders(template, placeholders)
    
    logger.debug(f"从Langfuse加载提示词成功: {template_name}")
    return prompt_template


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
        valid_intents = ["blood_pressure", "appointment", "health_event", "medication", "symptom", "unclear"]
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
    - health_event: 健康事件相关（记录、查询、更新健康事件）
    - medication: 用药相关（记录、查询、更新用药）
    - symptom: 症状相关（记录、查询、更新症状）
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
        
        # 从 Langfuse 加载提示词
        prompt_template = _load_router_prompt(
            template_name="router_intent_identification_prompt",
            context={
                "query": current_query,
                "history": history_text,
                "current_intent": current_intent_text
            }
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", prompt_template),
            ("human", """用户消息: {query}

对话历史: {history}

当前意图: {current_intent}

请识别用户的真实意图，返回JSON格式的结果。""")
        ])
        
        # 调用LLM（使用可配置的低温度以确保稳定性）
        llm = get_llm(temperature=settings.LLM_TEMPERATURE_INTENT)
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
        # 如果是提示词加载失败，直接抛出异常
        if "Langfuse" in str(e) or "模版" in str(e) or "template" in str(e).lower():
            raise ValueError(f"无法从Langfuse加载意图识别提示词: {str(e)}") from e
        # 其他错误返回默认结果
        default_result = IntentResult(
            intent_type="unclear",
            confidence=0.0,
            entities={},
            need_clarification=True,
            reasoning=f"意图识别异常: {str(e)}"
        )
        return default_result.model_dump()


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
        # 从 Langfuse 加载提示词
        prompt_template = _load_router_prompt(
            template_name="router_clarify_intent_prompt",
            context={"query": query}
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", prompt_template),
            ("human", "用户消息: {query}\n\n请生成澄清问题。")
        ])
        
        # 调用LLM（使用可配置的温度以生成更友好的问题）
        llm = get_llm(temperature=settings.LLM_TEMPERATURE_CLARIFY)
        chain = prompt | llm
        response = chain.invoke({"query": query})
        
        clarification = response.content if hasattr(response, 'content') else str(response)
        clarification = clarification.strip()
        
        # 验证澄清问题是否包含关键功能
        key_terms = ["血压", "预约", "健康事件", "用药", "症状"]
        if not any(term in clarification for term in key_terms):
            logger.warning(f"生成的澄清问题可能不完整: {clarification}")
            # 如果生成的澄清问题不包含关键功能，使用默认问题
            clarification = "抱歉，我没有理解您的意图。请告诉我您是想记录血压、预约复诊、记录健康事件、记录用药、记录症状，还是需要其他帮助？"
        
        logger.info(f"生成澄清问题: {clarification}")
        
        return clarification
        
    except Exception as e:
        logger.error(f"生成澄清问题失败: {str(e)}", exc_info=True)
        # 如果是提示词加载失败，直接抛出异常
        if "Langfuse" in str(e) or "模版" in str(e) or "template" in str(e).lower():
            raise ValueError(f"无法从Langfuse加载意图澄清提示词: {str(e)}") from e
        # 其他错误返回默认澄清问题
        default_clarification = "抱歉，我没有理解您的意图。请告诉我您是想记录血压、预约复诊、记录健康事件、记录用药、记录症状，还是需要其他帮助？"
        return default_clarification
