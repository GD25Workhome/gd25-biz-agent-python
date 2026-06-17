"""
模型供应商管理器。

负责从 YAML 加载配置、解析 ${ENV} 占位符，并写入 provider_registry。
"""
import os
import re
import logging
from pathlib import Path
from typing import Dict, Optional
import yaml

from backend.infrastructure.llm.providers.registry import provider_registry, ProviderConfig
from backend.app.config import settings, find_project_root

logger = logging.getLogger(__name__)


class ProviderManager:
    """模型供应商管理器，以类方法维护全局配置路径、加载状态与注册表。"""

    _config_path: Optional[Path] = None
    _loaded: bool = False

    @classmethod
    def _resolve_env_var(cls, value: str) -> str:
        """
            将字符串中的 ${VAR_NAME} 占位符替换为实际环境变量值。

            Args:
                value: 可能包含 ${VAR_NAME} 占位符的配置字符串

            Returns:
                str: 替换后的字符串；未设置的变量替换为空字符串
        """
        pattern = r'\$\{([^}]+)\}'

        def replace_env_var(match: re.Match[str]) -> str:
            var_name = match.group(1)
            # 优先读 .env（settings），再读系统环境变量
            env_value = getattr(settings, var_name, None)
            if env_value is None:
                env_value = os.getenv(var_name)
            if env_value is None:
                logger.warning(f"环境变量 {var_name} 未设置，使用空字符串")
                return ""
            return env_value

        return re.sub(pattern, replace_env_var, value)

    @classmethod
    def _get_config_path(cls) -> Path:
        """
            解析并缓存 model_providers.yaml 的绝对路径。

            Returns:
                Path: 配置文件绝对路径
        """
        if cls._config_path is not None:
            return cls._config_path

        project_root = find_project_root()
        config_path = project_root / settings.MODEL_PROVIDERS_CONFIG
        if not config_path.is_absolute():
            config_path = project_root / config_path

        cls._config_path = config_path
        return cls._config_path

    @classmethod
    def load_providers(cls, config_path: Optional[Path] = None) -> None:
        """
            从 YAML 加载模型供应商配置并写入内存注册表。

            Args:
                config_path: 配置文件路径；为 None 时使用 settings.MODEL_PROVIDERS_CONFIG

            Raises:
                FileNotFoundError: 配置文件不存在
                ValueError: YAML 格式错误或 providers 结构不合法
        """
        # 1. 确定配置文件路径
        if config_path is None:
            # _get_config_path：解析默认 YAML 路径并写入 cls._config_path
            config_path = cls._get_config_path()
        else:
            cls._config_path = config_path

        if not config_path.exists():
            raise FileNotFoundError(f"模型供应商配置文件不存在: {config_path}")

        logger.info(f"加载模型供应商配置: {config_path}")

        try:
            # 2. 读取 YAML 并校验顶层结构
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            if not config_data or "providers" not in config_data:
                raise ValueError("配置文件格式错误：缺少 'providers' 字段")

            providers_list = config_data.get("providers", [])
            if not isinstance(providers_list, list):
                raise ValueError("配置文件格式错误：'providers' 必须是列表")

            # 3. 重置注册表，准备写入本次加载结果
            provider_registry.clear()

            # 4~5. 逐条解析并注册供应商
            for provider_data in providers_list:
                if not isinstance(provider_data, dict):
                    logger.warning(f"跳过无效的供应商配置: {provider_data}")
                    continue

                provider_name = provider_data.get("provider")
                api_key = provider_data.get("api_key", "")
                base_url = provider_data.get("base_url", "")
                default_model = provider_data.get("default_model")

                if not provider_name:
                    logger.warning(f"跳过缺少 provider 名称的配置: {provider_data}")
                    continue

                # _resolve_env_var：将 ${ENV} 占位符替换为环境变量实际值
                api_key = cls._resolve_env_var(api_key)
                base_url = cls._resolve_env_var(base_url)

                if not api_key:
                    logger.warning(f"供应商 {provider_name} 的 API 密钥为空，跳过注册")
                    continue

                provider_registry.register(
                    provider=provider_name,
                    api_key=api_key,
                    base_url=base_url,
                    default_model=default_model,
                )
                logger.info(f"已注册模型供应商: {provider_name} (base_url: {base_url})")

            # 6. 完成加载
            cls._loaded = True
            logger.info(f"成功加载 {len(provider_registry.get_all())} 个模型供应商配置")

        except yaml.YAMLError as e:
            raise ValueError(f"配置文件 YAML 格式错误: {e}")
        except Exception as e:
            raise ValueError(f"加载模型供应商配置失败: {e}")

    @classmethod
    def get_provider(cls, provider: str) -> Optional[ProviderConfig]:
        """
            按名称获取已注册的模型供应商配置。

            Args:
                provider: 供应商名称

            Returns:
                ProviderConfig: 供应商配置；未注册时返回 None

            Raises:
                RuntimeError: 尚未调用 load_providers()
        """
        if not cls._loaded:
            raise RuntimeError("模型供应商配置未加载，请先调用 load_providers()")

        return provider_registry.get(provider)

    @classmethod
    def get_all_providers(cls) -> Dict[str, ProviderConfig]:
        """
            获取所有已注册的模型供应商配置副本。

            Returns:
                Dict[str, ProviderConfig]: 供应商名称到配置的映射

            Raises:
                RuntimeError: 尚未调用 load_providers()
        """
        if not cls._loaded:
            raise RuntimeError("模型供应商配置未加载，请先调用 load_providers()")

        return provider_registry.get_all()

    @classmethod
    def is_loaded(cls) -> bool:
        """检查模型供应商配置是否已通过 load_providers 完成加载。"""
        return cls._loaded
