"""
Langfuse模版加载器
支持从Langfuse加载提示词模版
"""
from typing import Dict, Any, Optional
import logging

from .data_loaders import DataLoader
from .langfuse_adapter import LangfusePromptAdapter

logger = logging.getLogger(__name__)


class LangfuseLoader(DataLoader):
    """Langfuse模版加载器"""
    
    def __init__(self, adapter: Optional[LangfusePromptAdapter] = None):
        """
        初始化Langfuse加载器
        
        Args:
            adapter: Langfuse适配器实例（可选，如果不提供则自动创建）
        """
        self._adapter: Optional[LangfusePromptAdapter] = None
        self._adapter_instance = adapter
        logger.debug("Langfuse加载器已初始化")
    
    @property
    def adapter(self) -> Optional[LangfusePromptAdapter]:
        """获取Langfuse适配器实例（延迟初始化）"""
        if self._adapter is None:
            if self._adapter_instance:
                self._adapter = self._adapter_instance
            else:
                # 尝试创建适配器（如果Langfuse未启用，会抛出异常）
                try:
                    self._adapter = LangfusePromptAdapter()
                except (ValueError, ImportError) as e:
                    logger.warning(f"无法创建Langfuse适配器: {e}，Langfuse加载器将不可用")
                    self._adapter = None
        return self._adapter
    
    def load(self, source: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        从Langfuse加载模版
        
        Args:
            source: 模版名称（如 "blood_pressure_agent_prompt"）
            context: 上下文（用于占位符填充，当前版本暂不支持）
        
        Returns:
            模版内容字符串
        
        Raises:
            ValueError: Langfuse未启用或适配器不可用
            ConnectionError: 无法从Langfuse获取模版
        """
        if not self.adapter:
            raise ValueError("Langfuse适配器不可用，请检查Langfuse配置")
        
        # 从context中提取版本信息（如果提供）
        version = None
        if context:
            version = context.get("version")
        
        # 从Langfuse获取模版
        template = self.adapter.get_template(
            template_name=source,
            version=version,
            fallback_to_local=True  # 启用降级机制
        )
        
        # 如果context中有占位符，进行填充
        if context:
            template = self._fill_placeholders(template, context)
        
        return template
    
    def _fill_placeholders(self, template: str, context: Dict[str, Any]) -> str:
        """
        填充占位符
        
        Args:
            template: 模版内容
            context: 上下文信息（包含占位符值）
        
        Returns:
            填充后的模版内容
        """
        # 简单的占位符替换：{{placeholder_name}}
        # 注意：这里只做基础的占位符替换，复杂的占位符管理由PlaceholderManager处理
        result = template
        for key, value in context.items():
            if key != "version":  # 跳过版本信息
                placeholder = f"{{{{{key}}}}}"
                if placeholder in result:
                    result = result.replace(placeholder, str(value))
        
        return result
    
    def supports(self, source: str) -> bool:
        """
        检查是否支持该数据源
        
        Args:
            source: 数据源字符串
        
        Returns:
            是否支持该数据源
        """
        # Langfuse加载器支持以 "langfuse://" 开头的路径
        # 或者如果适配器可用，也支持直接的模版名称（在PromptManager中会判断）
        if source.startswith("langfuse://"):
            return True
        
        # 如果适配器可用，且source看起来像是一个模版名称（不包含路径分隔符和特殊字符）
        if self.adapter and self.adapter.is_available():
            # 模版名称通常不包含路径分隔符、协议前缀等
            if not any(char in source for char in ["/", "\\", "://", "."]):
                # 可能是模版名称，但需要进一步验证
                # 这里返回True，让PromptManager决定是否使用
                return True
        
        return False

