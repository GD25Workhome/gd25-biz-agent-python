"""
Langfuse提示词模版适配器
负责从Langfuse获取提示词模版，并提供缓存和降级机制
"""
from typing import Dict, Optional, Tuple
import logging
from datetime import datetime, timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)

# 延迟导入Langfuse，避免在未安装时出错
try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    logger.warning("Langfuse未安装，提示词模版将无法从Langfuse加载")


class LangfusePromptAdapter:
    """Langfuse提示词模版适配器"""
    
    def __init__(self):
        """
        初始化Langfuse适配器
        
        Raises:
            ValueError: Langfuse未启用或配置不完整
        """
        if not LANGFUSE_AVAILABLE:
            raise ValueError("Langfuse未安装，请安装langfuse包")
        
        if not settings.LANGFUSE_ENABLED:
            raise ValueError("Langfuse未启用，请设置LANGFUSE_ENABLED=True")
        
        if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
            raise ValueError("Langfuse配置不完整，请设置LANGFUSE_PUBLIC_KEY和LANGFUSE_SECRET_KEY")
        
        # 打印连接参数（用于调试，不打印完整密钥）
        self._log_connection_params()
        
        self.client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST
        )
        self._cache: Dict[str, Tuple[str, datetime]] = {}  # key -> (content, expire_time)
        self._cache_ttl: int = settings.PROMPT_CACHE_TTL
        logger.info(f"Langfuse提示词适配器已初始化，缓存TTL: {self._cache_ttl}秒")
    
    def _log_connection_params(self):
        """
        打印Langfuse连接参数（用于调试）
        注意：为了安全，不打印完整的密钥内容
        """
        host = settings.LANGFUSE_HOST
        public_key = settings.LANGFUSE_PUBLIC_KEY
        secret_key = settings.LANGFUSE_SECRET_KEY
        
        # 打印host（完整）
        logger.info(f"Langfuse连接参数 - Host: {host}")
        
        # 打印public_key的部分信息（前4个字符和后4个字符）
        if public_key:
            if len(public_key) > 8:
                masked_public_key = f"{public_key[:4]}...{public_key[-4:]}"
            else:
                masked_public_key = "***"  # 太短则不显示
            logger.info(f"Langfuse连接参数 - Public Key: {masked_public_key} (长度: {len(public_key)})")
        else:
            logger.warning("Langfuse连接参数 - Public Key: 未设置")
        
        # 打印secret_key是否已设置（不打印内容）
        if secret_key:
            logger.info(f"Langfuse连接参数 - Secret Key: 已设置 (长度: {len(secret_key)})")
        else:
            logger.warning("Langfuse连接参数 - Secret Key: 未设置")
    
    def get_template(self, template_name: str, version: Optional[str] = None, fallback_to_local: bool = True) -> str:
        """
        从Langfuse获取提示词模版
        
        Args:
            template_name: 模版名称（如 "blood_pressure_agent_prompt"）
            version: 模版版本（可选，默认使用最新版本）
            fallback_to_local: 如果Langfuse不可用，是否降级到本地文件
        
        Returns:
            模版内容（包含占位符）
        
        Raises:
            ValueError: 模版不存在且无法降级
            ConnectionError: Langfuse服务不可用且无法降级
        """
        cache_key = f"{template_name}:{version or 'latest'}"
        
        # 检查缓存
        if cache_key in self._cache:
            content, expire_time = self._cache[cache_key]
            if datetime.now() < expire_time:
                logger.debug(f"使用缓存的Langfuse模版: {template_name}")
                return content
            else:
                # 缓存过期，清除
                del self._cache[cache_key]
        
        # 从Langfuse获取模版
        try:
            # 使用Langfuse SDK的prompt API
            # 注意：Langfuse SDK的get_prompt方法可能返回不同的对象类型
            prompt = self.client.get_prompt(template_name, version=version)
            
            # 提取模版内容
            if hasattr(prompt, 'prompt'):
                template_content = prompt.prompt
            elif hasattr(prompt, 'content'):
                template_content = prompt.content
            elif isinstance(prompt, str):
                template_content = prompt
            else:
                # 尝试转换为字符串
                template_content = str(prompt)
            
            if not template_content:
                raise ValueError(f"Langfuse模版内容为空: {template_name}")
            
            # 缓存模版
            expire_time = datetime.now() + timedelta(seconds=self._cache_ttl)
            self._cache[cache_key] = (template_content, expire_time)
            
            logger.info(f"成功从Langfuse获取模版: {template_name}, 版本: {version or 'latest'}")
            return template_content
            
        except Exception as e:
            # 打印连接参数和详细错误信息
            logger.error(f"从Langfuse获取模版失败: {template_name}, 错误: {e}")
            self._log_connection_params_on_error()
            
            # 如果启用降级，尝试从本地文件加载
            if fallback_to_local:
                logger.warning(f"尝试从本地文件降级加载: {template_name}")
                try:
                    return self._load_from_local_fallback(template_name)
                except Exception as fallback_error:
                    logger.error(f"本地文件降级加载也失败: {template_name}, 错误: {fallback_error}")
                    raise ValueError(
                        f"无法从Langfuse获取模版且本地降级失败: {template_name}, "
                        f"Langfuse错误: {e}, 本地错误: {fallback_error}"
                    )
            else:
                raise ConnectionError(f"从Langfuse获取模版失败: {template_name}, 错误: {e}")
    
    def _load_from_local_fallback(self, template_name: str) -> str:
        """
        从本地文件降级加载模版
        
        Args:
            template_name: 模版名称
        
        Returns:
            模版内容
        
        Raises:
            FileNotFoundError: 本地文件不存在
        """
        # 尝试从常见的本地路径查找
        from pathlib import Path
        
        # 可能的本地文件路径
        possible_paths = [
            Path(f"config/prompts/{template_name}.txt"),
            Path(f"config/prompts/templates/{template_name}.txt"),
            Path(f"config/prompts/{template_name}.yaml"),
        ]
        
        for path in possible_paths:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                logger.info(f"从本地文件降级加载模版: {path}")
                return content
        
        raise FileNotFoundError(f"未找到本地降级文件: {template_name}, 尝试路径: {possible_paths}")
    
    def clear_cache(self, template_name: Optional[str] = None):
        """
        清除缓存
        
        Args:
            template_name: 模版名称（可选，如果提供则只清除该模版的缓存，否则清除所有缓存）
        """
        if template_name:
            # 清除特定模版的缓存
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{template_name}:")]
            for key in keys_to_remove:
                del self._cache[key]
            logger.debug(f"已清除模版缓存: {template_name}, 清除项数: {len(keys_to_remove)}")
        else:
            # 清除所有缓存
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"已清除所有Langfuse模版缓存, 清除项数: {count}")
    
    def is_available(self) -> bool:
        """
        检查Langfuse服务是否可用
        
        Returns:
            是否可用
        """
        if not LANGFUSE_AVAILABLE:
            return False
        if not settings.LANGFUSE_ENABLED:
            return False
        try:
            # 尝试获取一个测试模版（如果失败则说明服务不可用）
            # 这里只是检查配置，不实际获取模版
            return bool(settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY)
        except Exception:
            return False
    
    def _log_connection_params_on_error(self):
        """
        在错误时打印连接参数（用于调试）
        """
        host = settings.LANGFUSE_HOST
        public_key = settings.LANGFUSE_PUBLIC_KEY
        secret_key = settings.LANGFUSE_SECRET_KEY
        
        logger.error(f"Langfuse连接参数检查 - Host: {host}")
        
        if public_key:
            if len(public_key) > 8:
                masked_public_key = f"{public_key[:4]}...{public_key[-4:]}"
            else:
                masked_public_key = "***"
            logger.error(f"Langfuse连接参数检查 - Public Key: {masked_public_key} (长度: {len(public_key)})")
        else:
            logger.error("Langfuse连接参数检查 - Public Key: 未设置")
        
        if secret_key:
            logger.error(f"Langfuse连接参数检查 - Secret Key: 已设置 (长度: {len(secret_key)})")
        else:
            logger.error("Langfuse连接参数检查 - Secret Key: 未设置")
        
        # 检查host格式
        if not host.startswith(('http://', 'https://')):
            logger.error(f"Langfuse连接参数检查 - Host格式可能不正确，当前值: {host}，应该以 http:// 或 https:// 开头")

