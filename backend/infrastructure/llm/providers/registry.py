"""
模型供应商注册表
用于缓存和管理模型供应商配置信息
"""
from typing import Dict, Optional
from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    """模型供应商配置"""
    provider: str = Field(description="供应商名称")
    api_key: str = Field(description="API密钥")
    base_url: str = Field(description="API基础URL")


class ProviderRegistry:
    """模型供应商注册表（单例模式）"""
    
    _instance: Optional['ProviderRegistry'] = None
    _providers: Dict[str, ProviderConfig] = {}
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, provider: str, api_key: str, base_url: str) -> None:
        """
        注册模型供应商配置
        
        Args:
            provider: 供应商名称
            api_key: API密钥
            base_url: API基础URL
        """
        self._providers[provider] = ProviderConfig(
            provider=provider,
            api_key=api_key,
            base_url=base_url
        )
    
    def get(self, provider: str) -> Optional[ProviderConfig]:
        """
        获取模型供应商配置
        
        Args:
            provider: 供应商名称
            
        Returns:
            ProviderConfig: 供应商配置，如果不存在则返回None
        """
        return self._providers.get(provider)
    
    def get_all(self) -> Dict[str, ProviderConfig]:
        """
        获取所有已注册的供应商配置
        
        Returns:
            Dict[str, ProviderConfig]: 所有供应商配置的字典
        """
        return self._providers.copy()
    
    def clear(self) -> None:
        """清空所有供应商配置"""
        self._providers.clear()
    
    def is_registered(self, provider: str) -> bool:
        """
        检查供应商是否已注册
        
        Args:
            provider: 供应商名称
            
        Returns:
            bool: 如果已注册返回True，否则返回False
        """
        return provider in self._providers


# 创建全局注册表实例
provider_registry = ProviderRegistry()

