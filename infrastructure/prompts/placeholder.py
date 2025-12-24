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
    user_id: str
    session_id: str
    current_agent: Optional[str]
    messages: list

logger = logging.getLogger(__name__)


class PlaceholderManager:
    """占位符管理器"""
    
    # 系统占位符（从state中提取）
    SYSTEM_PLACEHOLDERS = {
        "user_id": lambda state: state.get("user_id", ""),
        "session_id": lambda state: state.get("session_id", ""),
        "current_date": lambda state: datetime.now().strftime("%Y-%m-%d"),
        "current_time": lambda state: datetime.now().strftime("%H:%M:%S"),
        "current_datetime": lambda state: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    
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

