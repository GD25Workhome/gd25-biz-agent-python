"""
Agent注册表
支持动态Agent发现和注册，从配置文件自动加载
"""
from typing import Dict, Any, Optional
import logging

from domain.agents.factory import AgentFactory
from infrastructure.prompts.placeholder import PlaceholderManager

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Agent注册表"""
    
    _agents: Dict[str, Dict[str, Any]] = {}
    _initialized: bool = False
    
    @classmethod
    def register(cls, agent_key: str, config: Dict[str, Any]):
        """
        注册Agent
        
        Args:
            agent_key: Agent键名（如 "blood_pressure_agent"）
            config: Agent配置字典
        """
        cls._agents[agent_key] = config
        logger.info(f"注册Agent: {agent_key}")
    
    @classmethod
    def get_all_agents(cls) -> Dict[str, Dict[str, Any]]:
        """
        获取所有已注册的Agent
        
        Returns:
            Agent配置字典（agent_key -> config）
        """
        if not cls._initialized:
            cls.load_from_config()
        return cls._agents.copy()
    
    @classmethod
    def load_from_config(cls, config_path: Optional[str] = None):
        """
        从配置文件加载Agent
        
        Args:
            config_path: 配置文件路径（可选，默认使用AgentFactory的配置路径）
        """
        # 如果指定了config_path，强制使用该路径加载配置
        if config_path:
            # 保存原始配置
            original_config = AgentFactory._config.copy() if AgentFactory._config else {}
            original_config_path = AgentFactory._config_path
            
            try:
                # 加载指定路径的配置
                AgentFactory.load_config(config_path)
                config = AgentFactory._config
            finally:
                # 恢复原始配置（如果测试需要）
                # 注意：这里不恢复，因为实际使用时应该使用新配置
                pass
        else:
            # 如果没有指定config_path，使用AgentFactory的配置
            if not AgentFactory._config:
                AgentFactory.load_config()
            config = AgentFactory._config
        
        # 注册所有Agent
        for agent_key, agent_config in config.items():
            cls.register(agent_key, agent_config)
            
            # 加载Agent特定占位符
            PlaceholderManager.load_agent_placeholders(agent_key, agent_config)
        
        cls._initialized = True
        logger.info(f"从配置加载了 {len(cls._agents)} 个Agent")
    
    @classmethod
    def get_agent_config(cls, agent_key: str) -> Optional[Dict[str, Any]]:
        """
        获取Agent配置
        
        Args:
            agent_key: Agent键名
        
        Returns:
            Agent配置字典，如果不存在则返回None
        """
        if not cls._initialized:
            cls.load_from_config()
        return cls._agents.get(agent_key)
    
    @classmethod
    def is_registered(cls, agent_key: str) -> bool:
        """
        检查Agent是否已注册
        
        Args:
            agent_key: Agent键名
        
        Returns:
            如果已注册返回True，否则返回False
        """
        if not cls._initialized:
            cls.load_from_config()
        return agent_key in cls._agents
    
    @classmethod
    def clear(cls):
        """清除所有注册的Agent（用于测试或重新加载）"""
        cls._agents.clear()
        cls._initialized = False
        logger.info("已清除所有Agent注册")
    
    @classmethod
    def get_agent_node_name(cls, agent_key: str) -> str:
        """
        获取Agent在路由图中的节点名称
        
        Args:
            agent_key: Agent键名
        
        Returns:
            节点名称（从配置的routing.node_name获取，如果没有则使用agent_key）
        """
        config = cls.get_agent_config(agent_key)
        if not config:
            return agent_key
        
        routing_config = config.get("routing", {})
        return routing_config.get("node_name", agent_key)
    
    @classmethod
    def get_agent_intent_type(cls, agent_key: str) -> Optional[str]:
        """
        获取Agent对应的意图类型
        
        Args:
            agent_key: Agent键名
        
        Returns:
            意图类型（从配置的routing.intent_type获取），如果没有则返回None
        """
        config = cls.get_agent_config(agent_key)
        if not config:
            return None
        
        routing_config = config.get("routing", {})
        return routing_config.get("intent_type")

