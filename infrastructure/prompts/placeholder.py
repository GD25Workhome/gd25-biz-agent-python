"""
占位符管理系统
提供统一的占位符提取和填充功能
"""
from typing import Dict, Any, Optional, TypedDict
from datetime import datetime
import logging

# 避免直接导入RouterState，因为可能有Python版本兼容性问题
# 使用TypedDict定义简化版本
class SimpleRouterState(TypedDict, total=False):
    """简化的路由状态（用于占位符提取）"""
    token_id: str  # 令牌ID（当前阶段等于用户ID，未来可扩展为业务系统令牌）
    session_id: str
    current_agent: Optional[str]
    messages: list

logger = logging.getLogger(__name__)


class PlaceholderManager:
    """占位符管理器"""
    
    # 系统占位符（从state中提取）
    # 注意：已移除 user_id 占位符，因为方案二不需要在提示词中注入 token_id
    SYSTEM_PLACEHOLDERS = {
        "session_id": lambda state: state.get("session_id", ""),
        "current_date": lambda state: PlaceholderManager._get_current_date(state),
        "current_time": lambda state: PlaceholderManager._get_current_time(state),
        "current_datetime": lambda state: PlaceholderManager._get_current_datetime(state),
        "user_info": lambda state: state.get("user_info", "暂无患者基础信息"),
    }
    
    @staticmethod
    def _get_current_date(state: Dict[str, Any]) -> str:
        """
        获取当前日期（格式：YYYY-MM-DD）
        
        优先使用state中的current_date（如果提供），否则使用系统当前时间
        
        Args:
            state: 路由状态
            
        Returns:
            日期字符串（格式：YYYY-MM-DD）
        """
        current_date = state.get("current_date")
        if current_date:
            # 如果提供了完整日期时间（YYYY-MM-DD HH:mm），只提取日期部分
            if " " in current_date:
                return current_date.split(" ")[0]
            return current_date
        # 如果没有提供，使用系统当前时间
        return datetime.now().strftime("%Y-%m-%d")
    
    @staticmethod
    def _get_current_time(state: Dict[str, Any]) -> str:
        """
        获取当前时间（格式：HH:MM:SS）
        
        优先使用state中的current_date（如果提供），否则使用系统当前时间
        
        Args:
            state: 路由状态
            
        Returns:
            时间字符串（格式：HH:MM:SS）
        """
        current_date = state.get("current_date")
        if current_date:
            # 如果提供了完整日期时间（YYYY-MM-DD HH:mm），提取时间部分并补齐秒
            if " " in current_date:
                time_part = current_date.split(" ")[1]
                # 如果时间部分只有HH:mm，补齐为HH:mm:00
                if len(time_part) == 5:  # HH:mm
                    return time_part + ":00"
                return time_part
        # 如果没有提供，使用系统当前时间
        return datetime.now().strftime("%H:%M:%S")
    
    @staticmethod
    def _get_current_datetime(state: Dict[str, Any]) -> str:
        """
        获取当前日期时间（格式：YYYY-MM-DD HH:MM:SS）
        
        优先使用state中的current_date（如果提供），否则使用系统当前时间
        
        Args:
            state: 路由状态
            
        Returns:
            日期时间字符串（格式：YYYY-MM-DD HH:MM:SS）
        """
        current_date = state.get("current_date")
        if current_date:
            # 如果提供了日期时间（YYYY-MM-DD HH:mm），补齐秒为HH:mm:00
            if " " in current_date:
                date_part, time_part = current_date.split(" ")
                if len(time_part) == 5:  # HH:mm
                    return f"{date_part} {time_part}:00"
                return f"{date_part} {time_part}"
            # 如果只提供了日期（YYYY-MM-DD），使用00:00:00作为时间
            return f"{current_date} 00:00:00"
        # 如果没有提供，使用系统当前时间
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    @classmethod
    def _format_history_msg_from_state(cls, state: Dict[str, Any]) -> str:
        """
        从state中的messages格式化历史消息
        
        Args:
            state: 路由状态
            
        Returns:
            格式化后的历史消息文本
        """
        # 优先使用state中的history_msg（如果存在，说明已由API层格式化）
        if "history_msg" in state:
            return state.get("history_msg", "暂无历史对话")
        
        # 否则从messages中格式化
        messages = state.get("messages", [])
        if not messages:
            return "暂无历史对话"
        
        history_lines = []
        for msg in messages:
            # 跳过当前消息（最后一条）
            if msg == messages[-1]:
                continue
            # 根据消息类型格式化
            msg_type = type(msg).__name__
            if msg_type == "HumanMessage":
                history_lines.append(f"用户: {msg.content}")
            elif msg_type == "AIMessage":
                history_lines.append(f"助手: {msg.content}")
        
        if history_lines:
            return "\n".join(history_lines)
        return "暂无历史对话"
    
    # Agent特定占位符（从agents.yaml配置中读取）
    AGENT_PLACEHOLDERS: Dict[str, Dict[str, Any]] = {}
    
    @classmethod
    def load_agent_placeholders(cls, agent_key: str, config: Dict[str, Any]):
        """
        从配置加载Agent特定占位符
        
        Args:
            agent_key: Agent键名
            config: Agent配置字典
        """
        placeholders_config = config.get("placeholders", {})
        if placeholders_config:
            cls.AGENT_PLACEHOLDERS[agent_key] = placeholders_config
            logger.debug(f"已加载Agent占位符: {agent_key}, 占位符数: {len(placeholders_config)}")
        else:
            # 如果没有占位符配置，确保字典中有该agent_key（避免重复检查）
            if agent_key not in cls.AGENT_PLACEHOLDERS:
                cls.AGENT_PLACEHOLDERS[agent_key] = {}
    
    @classmethod
    def get_placeholders(cls, agent_key: str, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        获取占位符值
        
        Args:
            agent_key: Agent键名
            state: 路由状态（可选，如果不提供则只返回Agent特定占位符）
        
        Returns:
            占位符字典
        """
        placeholders = {}
        
        # 系统占位符（需要state）
        if state:
            for key, getter in cls.SYSTEM_PLACEHOLDERS.items():
                try:
                    value = getter(state)
                    placeholders[key] = value
                except Exception as e:
                    logger.warning(f"获取系统占位符失败: {key}, 错误: {e}")
                    placeholders[key] = ""
            
            # 特殊处理 history_msg（从state中的messages格式化）
            try:
                placeholders["history_msg"] = cls._format_history_msg_from_state(state)
            except Exception as e:
                logger.warning(f"获取历史消息占位符失败, 错误: {e}")
                placeholders["history_msg"] = "暂无历史对话"
        else:
            # 如果没有state，只设置时间相关的占位符
            placeholders["current_date"] = datetime.now().strftime("%Y-%m-%d")
            placeholders["current_time"] = datetime.now().strftime("%H:%M:%S")
            placeholders["current_datetime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Agent特定占位符
        if agent_key in cls.AGENT_PLACEHOLDERS:
            placeholders.update(cls.AGENT_PLACEHOLDERS[agent_key])
        
        return placeholders
    
    @classmethod
    def fill_placeholders(cls, template: str, placeholders: Dict[str, Any]) -> str:
        """
        填充占位符到模版中
        
        Args:
            template: 模版内容（支持 {{placeholder_name}} 格式）
            placeholders: 占位符字典
        
        Returns:
            填充后的模版内容
        """
        result = template
        
        # 替换所有占位符
        for key, value in placeholders.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
                logger.debug(f"填充占位符: {key} = {value}")
        
        # 检查是否有未填充的占位符（警告）
        import re
        remaining_placeholders = re.findall(r'\{\{(\w+)\}\}', result)
        if remaining_placeholders:
            logger.warning(f"模版中存在未填充的占位符: {remaining_placeholders}")
        
        return result
    
    @classmethod
    def clear_agent_placeholders(cls, agent_key: Optional[str] = None):
        """
        清除Agent占位符
        
        Args:
            agent_key: Agent键名（可选，如果不提供则清除所有）
        """
        if agent_key:
            if agent_key in cls.AGENT_PLACEHOLDERS:
                del cls.AGENT_PLACEHOLDERS[agent_key]
                logger.debug(f"已清除Agent占位符: {agent_key}")
        else:
            count = len(cls.AGENT_PLACEHOLDERS)
            cls.AGENT_PLACEHOLDERS.clear()
            logger.info(f"已清除所有Agent占位符, 清除项数: {count}")

