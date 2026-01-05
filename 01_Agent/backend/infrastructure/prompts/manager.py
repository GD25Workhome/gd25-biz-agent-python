"""
提示词管理器
负责提示词的加载、缓存和管理
支持从上下文替换占位符
"""
import logging
import re
from pathlib import Path
from typing import Dict, Optional

from backend.infrastructure.prompts.loader import PromptLoader
from backend.domain.context.flow_context import FlowContext
from backend.domain.context.user_context import UserContext

logger = logging.getLogger(__name__)


class PromptManager:
    """提示词管理器（单例模式）"""
    
    _instance: 'PromptManager' = None
    _cache: Dict[str, str] = {}  # 缓存：key为提示词路径，value为提示词内容
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_prompt(
        self,
        prompt_path: str,
        flow_dir: str,
        flow_context: Optional[FlowContext] = None,
        user_context: Optional[UserContext] = None
    ) -> str:
        """
        获取提示词（如果缓存中没有，则加载并缓存）
        支持从上下文替换占位符（如 {{key}}）
        
        Args:
            prompt_path: 提示词路径（相对于流程目录）
            flow_dir: 流程目录路径
            flow_context: 流程上下文（可选，用于占位符替换）
            user_context: 用户上下文（可选，用于占位符替换）
            
        Returns:
            str: 提示词内容（已替换占位符）
        """
        # 解析提示词路径
        resolved_path = PromptLoader.resolve_path(prompt_path, flow_dir)
        cache_key = str(resolved_path)
        
        # 检查缓存（如果不需要上下文替换，可以使用缓存）
        if cache_key in self._cache and flow_context is None and user_context is None:
            logger.debug(f"从缓存获取提示词: {cache_key}")
            return self._cache[cache_key]
        
        # 加载提示词
        prompt_content = PromptLoader.load_from_file(resolved_path)
        
        # 如果提供了上下文，进行占位符替换
        if flow_context is not None or user_context is not None:
            prompt_content = self._replace_placeholders(
                prompt_content,
                flow_context=flow_context,
                user_context=user_context
            )
        else:
            # 缓存提示词（未替换占位符的原始内容）
            self._cache[cache_key] = prompt_content
            logger.info(f"加载并缓存提示词: {cache_key}")
        
        return prompt_content
    
    def _replace_placeholders(
        self,
        template: str,
        flow_context: Optional[FlowContext] = None,
        user_context: Optional[UserContext] = None
    ) -> str:
        """
        替换提示词模板中的占位符
        
        支持的占位符格式：
        - {{key}}: 从flow_context或user_context获取数据
        - {{flow_context.key}}: 明确指定从flow_context获取
        - {{user_context.key}}: 明确指定从user_context获取
        
        Args:
            template: 提示词模板
            flow_context: 流程上下文
            user_context: 用户上下文
            
        Returns:
            str: 替换后的提示词内容
        """
        # 匹配占位符：{{key}} 或 {{context.key}}
        pattern = r'\{\{([^}]+)\}\}'
        
        def replace_match(match):
            placeholder = match.group(1).strip()
            
            # 检查是否有上下文前缀
            if placeholder.startswith("flow_context."):
                key = placeholder[len("flow_context."):]
                if flow_context:
                    value = flow_context.get(key)
                    if value is not None:
                        return str(value)
            elif placeholder.startswith("user_context."):
                key = placeholder[len("user_context."):]
                if user_context:
                    # 支持特殊键：preferences.key, settings.key, user_info
                    if key.startswith("preferences."):
                        pref_key = key[len("preferences."):]
                        value = user_context.get_preference(pref_key)
                        if value is not None:
                            return str(value)
                    elif key.startswith("settings."):
                        setting_key = key[len("settings."):]
                        value = user_context.get_setting(setting_key)
                        if value is not None:
                            return str(value)
                    elif key == "user_info":
                        user_info = user_context.get_user_info()
                        if user_info:
                            import json
                            return json.dumps(user_info, ensure_ascii=False)
                    else:
                        value = user_context.get(key)
                        if value is not None:
                            return str(value)
            else:
                # 默认先从flow_context查找，再从user_context查找
                if flow_context:
                    value = flow_context.get(placeholder)
                    if value is not None:
                        return str(value)
                
                if user_context:
                    value = user_context.get(placeholder)
                    if value is not None:
                        return str(value)
            
            # 如果找不到，保留原占位符（或返回空字符串）
            logger.warning(f"占位符未找到值: {placeholder}")
            return match.group(0)  # 保留原占位符
        
        result = re.sub(pattern, replace_match, template)
        return result
    
    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
        logger.info("提示词缓存已清空")
    
    def get_cache_size(self) -> int:
        """
        获取缓存大小
        
        Returns:
            int: 缓存中提示词的数量
        """
        return len(self._cache)


# 创建全局提示词管理器实例
prompt_manager = PromptManager()

