"""
API层辅助工具方法
提供请求数据转换、状态构建等通用功能
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from dateutil import parser as date_parser
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from fastapi import HTTPException

from backend.app.api.schemas.chat import ChatRequest, ChatMessage
from backend.domain.state import FlowState
from backend.domain.flows.manager import FlowManager
from backend.domain.context.context_manager import get_context_manager
from backend.domain.context.user_info import UserInfo

logger = logging.getLogger(__name__)


def parse_datetime(date_str: str) -> Optional[datetime]:
    """
    解析日期时间字符串，支持多种格式
    
    Args:
        date_str: 日期时间字符串
        
    Returns:
        datetime对象，如果解析失败则返回None
        
    支持的格式：
    - YYYY-MM-DD
    - YYYY-MM-DD HH:MM
    - YYYY-MM-DD HH:MM:SS
    - YYYY/MM/DD
    - YYYY/MM/DD HH:MM
    - 其他常见日期格式
    """
    if not date_str:
        return None
    
    try:
        # 使用dateutil.parser解析，支持多种格式
        return date_parser.parse(date_str)
    except (ValueError, TypeError) as e:
        logger.warning(f"日期解析失败: {date_str}, 错误: {e}")
        return None


def build_history_messages(conversation_history: Optional[List[ChatMessage]]) -> List[BaseMessage]:
    """
    从对话历史构建LangChain消息列表
    
    Args:
        conversation_history: 对话历史列表，可能为None
        
    Returns:
        List[BaseMessage]: LangChain消息列表
    """
    history_messages = []
    if conversation_history:
        for msg in conversation_history:
            if msg.role == "user":
                history_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                history_messages.append(AIMessage(content=msg.content))
    return history_messages


def build_current_message(message: str) -> HumanMessage:
    """
    构建当前用户消息
    
    Args:
        message: 用户消息内容
        
    Returns:
        HumanMessage: LangChain HumanMessage对象
    """
    return HumanMessage(content=message)


def _format_doctor_info(doctor_info: Dict[str, Any]) -> str:
    """
    格式化医生信息为易读的字符串格式
    
    Args:
        doctor_info: 医生信息字典，包含 doctor_name 和 schedule
        
    Returns:
        str: 格式化后的医生信息字符串
    """
    if not doctor_info:
        return ""
    
    doctor_name = doctor_info.get("doctor_name", "")
    schedule = doctor_info.get("schedule", [])
    
    if not doctor_name and not schedule:
        return ""
    
    parts = []
    
    # 医生姓名
    if doctor_name:
        parts.append(f"医生姓名：{doctor_name}；")
    
    # 排班情况
    if schedule:
        schedule_parts = []
        for item in schedule:
            date = item.get("date", "")
            morning = item.get("morning")
            afternoon = item.get("afternoon")
            
            if morning:
                schedule_parts.append(f"{date} {morning}")
            if afternoon:
                schedule_parts.append(f"{date} {afternoon}")
        
        if schedule_parts:
            parts.append("近期排班情况：")
            parts.append("，".join(schedule_parts) + "。")
    
    return "\n".join(parts)


def build_initial_state(
    request: ChatRequest,
    current_message: HumanMessage,
    history_messages: List[BaseMessage],
) -> FlowState:
    """
        构建 LangGraph 流程初始状态，并填充提示词占位符 prompt_vars。

        prompt_vars 供各 Agent 节点的 sys_prompt_builder 替换系统提示词中的
        {current_date}、{user_info}、{doctor_info} 等变量。

        Args:
            request: 聊天请求（含 token_id、session_id、可选 current_date）
            current_message: 本轮用户消息
            history_messages: 历史对话消息列表

        Returns:
            FlowState 初始字典，含消息、会话标识与 prompt_vars
    """
    context_manager = get_context_manager()
    prompt_vars: Dict[str, Any] = {}

    # 1. 填充 current_date：请求未带则取服务端当前时间
    if request.current_date:
        prompt_vars["current_date"] = request.current_date
    else:
        prompt_vars["current_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2. 从 Token 缓存加载 user_info（格式化留给 sys_prompt_builder）
    # get_token_context：按 token_id 读取 login 阶段写入的 UserInfo
    token_context = context_manager.get_token_context(request.token_id)
    if token_context and isinstance(token_context, UserInfo):
        prompt_vars["user_info"] = token_context.get_user_info()
    else:
        prompt_vars["user_info"] = None
        if token_context is None:
            logger.warning(f"Token上下文不存在: token_id={request.token_id}")
        else:
            logger.warning(
                f"Token上下文不是UserInfo对象: token_id={request.token_id}, "
                f"type={type(token_context)}"
            )

    # 3. 从 Session 缓存加载并格式化 doctor_info
    session_context = context_manager.get_session_context(request.session_id)
    if session_context:
        doctor_info = session_context.get("doctor_info")
        if doctor_info:
            # _format_doctor_info：将排班字典转为提示词可读的文本
            prompt_vars["doctor_info"] = _format_doctor_info(doctor_info)
        else:
            prompt_vars["doctor_info"] = ""
    else:
        prompt_vars["doctor_info"] = ""

    # 4. 组装 FlowState 并返回
    return {
        "current_message": current_message,
        "history_messages": history_messages,
        "flow_msgs": [],
        "session_id": request.session_id,
        "intent": None,
        "token_id": request.token_id,
        "trace_id": request.trace_id,
        "prompt_vars": prompt_vars,
    }


def get_flow_graph(session_id: str) -> Tuple[Any, str, str]:
    """
        根据 session_id 解析会话绑定的流程，并返回可执行的 LangGraph 编译图。

        从 ContextManager 读取 session_context 中的 flow_info，再经 FlowManager
        取编译图（启动预加载或首次调用时按需编译）。

        Args:
            session_id: 会话 ID（login 阶段创建 Session 时写入）

        Returns:
            (graph, flow_key, flow_name)：
            - graph: LangGraph 编译后的流程图
            - flow_key: 流程键，与 login 时 flow_def.name 一致
            - flow_name: 展示用流程名，与 login 时 description or name 一致

        Raises:
            HTTPException: Session 不存在（404）、Session 数据缺字段（500）或流程加载失败（500）
    """
    # 1. 获取上下文管理器并加载 Session
    context_manager = get_context_manager()
    session_context = context_manager.get_session_context(session_id)
    if session_context is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session不存在: {session_id}。请先创建Session。",
        )

    # 2. 校验并解析 flow_info
    flow_info = session_context.get("flow_info")
    if flow_info is None:
        raise HTTPException(
            status_code=500,
            detail=f"Session数据格式错误：缺少flow_info。session_id={session_id}",
        )

    flow_key = flow_info.get("flow_key")
    if flow_key is None:
        raise HTTPException(
            status_code=500,
            detail=f"Session数据格式错误：flow_info中缺少flow_key。session_id={session_id}",
        )
    flow_name = flow_info.get("flow_name") or flow_key

    # 3. 获取编译图并返回三元组
    try:
        # FlowManager.get_flow：命中预加载缓存，否则扫描并编译流程
        graph = FlowManager.get_flow(flow_key)
        return graph, flow_key, flow_name
    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取流程图失败: {str(e)}。flow_key={flow_key}, session_id={session_id}",
        )

