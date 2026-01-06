"""
Agent注册表
管理Agent配置信息（本版本简化，后续可扩展）
"""
from typing import Dict, Any


class AgentRegistry:
    """Agent注册表（单例模式）"""
    
    _instance: 'AgentRegistry' = None
    _agents: Dict[str, Dict[str, Any]] = {}
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, name: str, config: Dict[str, Any]) -> None:
        """
        注册Agent配置
        
        Args:
            name: Agent名称
            config: Agent配置
        """
        self._agents[name] = config
    
    def get(self, name: str) -> Dict[str, Any]:
        """
        获取Agent配置
        
        Args:
            name: Agent名称
            
        Returns:
            Agent配置，如果不存在则返回None
        """
        return self._agents.get(name)
    
    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有Agent配置
        
        Returns:
            所有Agent配置的字典
        """
        return self._agents.copy()
    
    def clear(self) -> None:
        """清空所有Agent配置"""
        self._agents.clear()


# 创建全局注册表实例
agent_registry = AgentRegistry()

