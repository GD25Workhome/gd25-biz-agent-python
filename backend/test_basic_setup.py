"""
基础架构测试
测试第一阶段实现的基础模块

Pytest 命令示例：
================

# 运行整个测试文件
pytest backend/test_basic_setup.py

# 运行整个测试文件（详细输出）
pytest backend/test_basic_setup.py -v

# 运行整个测试文件（详细输出 + 显示 print 输出）
pytest backend/test_basic_setup.py -v -s

# 运行特定的测试类
pytest backend/test_basic_setup.py::TestProviderRegistry

# 运行特定的测试方法
pytest backend/test_basic_setup.py::TestProviderRegistry::test_register_and_get
"""
import os
import sys
import pytest
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.llm.providers.registry import ProviderRegistry, ProviderConfig
from backend.infrastructure.llm.providers.manager import ProviderManager
from backend.app.config import settings, find_project_root


class TestProviderRegistry:
    """测试模型供应商注册表"""
    
    def test_register_and_get(self):
        """测试注册和获取供应商配置"""
        registry = ProviderRegistry()
        registry.clear()  # 清空现有配置
        
        # 注册供应商
        registry.register(
            provider="test_provider",
            api_key="test_api_key",
            base_url="https://test.api.com"
        )
        
        # 获取供应商配置
        config = registry.get("test_provider")
        assert config is not None
        assert config.provider == "test_provider"
        assert config.api_key == "test_api_key"
        assert config.base_url == "https://test.api.com"
    
    def test_get_nonexistent_provider(self):
        """测试获取不存在的供应商"""
        registry = ProviderRegistry()
        config = registry.get("nonexistent_provider")
        assert config is None
    
    def test_get_all(self):
        """测试获取所有供应商配置"""
        registry = ProviderRegistry()
        registry.clear()
        
        # 注册多个供应商
        registry.register("provider1", "key1", "url1")
        registry.register("provider2", "key2", "url2")
        
        all_providers = registry.get_all()
        assert len(all_providers) == 2
        assert "provider1" in all_providers
        assert "provider2" in all_providers
    
    def test_is_registered(self):
        """测试检查供应商是否已注册"""
        registry = ProviderRegistry()
        registry.clear()
        
        registry.register("test_provider", "key", "url")
        
        assert registry.is_registered("test_provider") is True
        assert registry.is_registered("nonexistent") is False


class TestProviderManager:
    """测试模型供应商管理器"""
    
    def test_load_providers(self):
        """测试加载供应商配置"""
        # 确保配置已加载
        if not ProviderManager.is_loaded():
            config_path = find_project_root() / "config" / "model_providers.yaml"
            if config_path.exists():
                ProviderManager.load_providers(config_path)
        
        # 验证配置已加载
        assert ProviderManager.is_loaded() is True
    
    def test_get_provider(self):
        """测试获取供应商配置"""
        # 确保配置已加载
        if not ProviderManager.is_loaded():
            config_path = find_project_root() / "config" / "model_providers.yaml"
            if config_path.exists():
                ProviderManager.load_providers(config_path)
        
        # 尝试获取一个供应商（如果配置文件中有的话）
        all_providers = ProviderManager.get_all_providers()
        if all_providers:
            provider_name = list(all_providers.keys())[0]
            config = ProviderManager.get_provider(provider_name)
            assert config is not None
            assert config.provider == provider_name
    
    def test_get_nonexistent_provider(self):
        """测试获取不存在的供应商"""
        # 确保配置已加载
        if not ProviderManager.is_loaded():
            config_path = find_project_root() / "config" / "model_providers.yaml"
            if config_path.exists():
                ProviderManager.load_providers(config_path)
        
        config = ProviderManager.get_provider("nonexistent_provider")
        assert config is None


class TestConfig:
    """测试配置管理"""
    
    def test_find_project_root(self):
        """测试查找项目根目录"""
        root = find_project_root()
        assert root.exists()
        assert root.is_dir()
    
    def test_settings_loaded(self):
        """测试配置已加载"""
        assert settings is not None
        assert hasattr(settings, "LLM_MODEL")
        assert hasattr(settings, "LLM_TEMPERATURE")


class TestLLMClient:
    """测试LLM客户端"""
    
    def test_get_llm_with_provider(self):
        """测试使用供应商配置创建LLM客户端"""
        from backend.infrastructure.llm.client import get_llm
        
        # 确保配置已加载
        if not ProviderManager.is_loaded():
            config_path = find_project_root() / "config" / "model_providers.yaml"
            if config_path.exists():
                ProviderManager.load_providers(config_path)
        
        # 检查是否有可用的供应商
        all_providers = ProviderManager.get_all_providers()
        if not all_providers:
            pytest.skip("没有可用的模型供应商配置，跳过测试")
        
        # 使用第一个可用的供应商
        provider_name = list(all_providers.keys())[0]
        
        # 注意：这里只测试创建LLM实例，不实际调用API
        # 因为需要真实的API密钥
        try:
            llm = get_llm(
                provider=provider_name,
                model="test-model",
                temperature=0.7
            )
            assert llm is not None
        except ValueError as e:
            # 如果API密钥未设置，这是预期的
            if "未注册" in str(e):
                pytest.skip(f"供应商 {provider_name} 配置无效，跳过测试")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

