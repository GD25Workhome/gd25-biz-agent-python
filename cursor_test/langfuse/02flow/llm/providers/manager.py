"""
模型供应商管理器
负责加载和管理模型供应商配置（从YAML文件读取）
"""
import os
import re
import logging
from pathlib import Path
from typing import Optional
import yaml

from core.config import settings, find_project_root
from .registry import provider_registry, ProviderConfig

logger = logging.getLogger(__name__)


class ProviderManager:
    """模型供应商管理器"""
    
    _config_path: Optional[Path] = None
    _loaded: bool = False
    
    @classmethod
    def _resolve_env_var(cls, value: str) -> str:
        """
        解析环境变量占位符
        
        支持格式：${VAR_NAME}
        
        Args:
            value: 可能包含环境变量占位符的字符串
            
        Returns:
            str: 解析后的值
        """
        # 匹配 ${VAR_NAME} 格式
        pattern = r'\$\{([^}]+)\}'
        
        def replace_env_var(match):
            var_name = match.group(1)
            # 优先从 settings 对象读取（支持 .env 文件）
            env_value = getattr(settings, var_name, None)
            # 如果 settings 中没有，再从系统环境变量读取
            if env_value is None:
                env_value = os.getenv(var_name)
            if env_value is None:
                logger.warning(f"环境变量 {var_name} 未设置，使用空字符串")
                return ""
            return env_value
        
        result = re.sub(pattern, replace_env_var, value)
        return result
    
    @classmethod
    def _get_config_path(cls) -> Path:
        """
        获取配置文件路径
        
        Returns:
            Path: 配置文件路径
        """
        if cls._config_path is None:
            project_root = find_project_root()
            config_path = project_root / settings.MODEL_PROVIDERS_CONFIG
            
            # 如果是相对路径，相对于项目根目录
            if not config_path.is_absolute():
                config_path = project_root / config_path
            
            cls._config_path = config_path
        
        return cls._config_path
    
    @classmethod
    def load_providers(cls, config_path: Optional[Path] = None) -> None:
        """
        加载模型供应商配置
        
        Args:
            config_path: 配置文件路径（可选，默认使用配置中的路径）
            
        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置文件格式错误
        """
        if config_path is None:
            config_path = cls._get_config_path()
        else:
            cls._config_path = config_path
        
        if not config_path.exists():
            raise FileNotFoundError(f"模型供应商配置文件不存在: {config_path}")
        
        logger.info(f"加载模型供应商配置: {config_path}")
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
            
            if not config_data or "providers" not in config_data:
                raise ValueError("配置文件格式错误：缺少 'providers' 字段")
            
            providers_list = config_data.get("providers", [])
            if not isinstance(providers_list, list):
                raise ValueError("配置文件格式错误：'providers' 必须是列表")
            
            # 清空现有注册表
            provider_registry.clear()
            
            # 加载每个供应商配置
            for provider_data in providers_list:
                if not isinstance(provider_data, dict):
                    logger.warning(f"跳过无效的供应商配置: {provider_data}")
                    continue
                
                provider_name = provider_data.get("provider")
                api_key = provider_data.get("api_key", "")
                base_url = provider_data.get("base_url", "")
                
                if not provider_name:
                    logger.warning(f"跳过缺少 provider 名称的配置: {provider_data}")
                    continue
                
                # 解析环境变量
                api_key = cls._resolve_env_var(api_key)
                base_url = cls._resolve_env_var(base_url)
                
                if not api_key:
                    logger.warning(f"供应商 {provider_name} 的 API 密钥为空，跳过注册")
                    continue
                
                # 注册供应商
                provider_registry.register(
                    provider=provider_name,
                    api_key=api_key,
                    base_url=base_url
                )
                
                logger.info(f"已注册模型供应商: {provider_name} (base_url: {base_url})")
            
            cls._loaded = True
            logger.info(f"成功加载 {len(provider_registry.get_all())} 个模型供应商配置")
            
        except yaml.YAMLError as e:
            raise ValueError(f"配置文件 YAML 格式错误: {e}")
        except Exception as e:
            raise ValueError(f"加载模型供应商配置失败: {e}")
    
    @classmethod
    def get_provider(cls, provider: str) -> Optional[ProviderConfig]:
        """
        获取模型供应商配置
        
        Args:
            provider: 供应商名称
            
        Returns:
            ProviderConfig: 供应商配置，如果不存在则返回None
            
        Raises:
            RuntimeError: 如果配置未加载
        """
        if not cls._loaded:
            # 自动加载配置（如果未加载）
            cls.load_providers()
        
        return provider_registry.get(provider)

