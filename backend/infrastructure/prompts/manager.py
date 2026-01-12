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

logger = logging.getLogger(__name__)

# 
class PromptManager:
    """提示词管理器（单例模式）"""
    
    _instance: 'PromptManager' = None
    _cache: Dict[str, str] = {}  # 缓存：key为提示词路径，value为提示词内容
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def cached_prompt(self, prompt_path: str, flow_dir: str) -> str:
        """
        加载提示词并缓存，返回缓存的 key
        
        该方法会：
        1. 解析提示词路径，生成缓存 key
        2. 无论缓存是否存在，都重新从文件加载提示词内容
        3. 如果缓存已存在，覆盖缓存；如果不存在，新增缓存
        4. 返回缓存的 key
        
        Args:
            prompt_path: 提示词路径（相对于流程目录）
            flow_dir: 流程目录路径
            
        Returns:
            str: 缓存的 key
        """
        # 解析提示词路径
        resolved_path = PromptLoader.resolve_path(prompt_path, flow_dir)
        cache_key = str(resolved_path)
        
        # 无论缓存是否存在，都重新根据路径获取提示词内容，然后更新缓存
        prompt_content = PromptLoader.load_from_file(resolved_path)
        
        # 检查缓存中是否已经存在
        if cache_key in self._cache:
            logger.info(f"缓存已经存在，覆盖缓存 key: {cache_key}")
        else:
            logger.info(f"加载并缓存提示词: {cache_key}")
        
        self._cache[cache_key] = prompt_content
        
        return cache_key

    def get_prompt_by_key(self, cache_key: str) -> str:
        """
        根据缓存的 key 获取系统提示词
        
        该方法会：
        1. 根据 cache_key 从缓存中获取提示词内容
        2. 如果 key 不存在，抛出异常
        
        Args:
            cache_key: 缓存的 key（通常通过 cached_prompt 方法获取）
            
        Returns:
            str: 缓存的提示词内容
            
        Raises:
            KeyError: 如果缓存中不存在该 key
        """
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # 如果 key 不存在，抛出异常
        raise KeyError(f"提示词未在缓存中找到: {cache_key}")

    # 待升级-这里的提示词替换统一入口可以保留，但是内部的逻辑需要和当前的设计统一一下
    # def _replace_placeholders(
    #     self,
    #     template: str,
    #     session_context: Optional[SessionContext] = None,
    #     user_info: Optional[UserInfo] = None
    # ) -> str:
        """
        替换提示词模板中的占位符
        
        支持的占位符格式：
        - {{key}}: 从session_context或user_info获取数据
        - {{session_context.key}}: 明确指定从session_context获取
        - {{user_info.key}}: 明确指定从user_info获取
        
        Args:
            template: 提示词模板
            session_context: 聊天上下文
            user_info: 用户信息
            
        Returns:
            str: 替换后的提示词内容
        """
        # 匹配占位符：{{key}} 或 {{context.key}}
        pattern = r'\{\{([^}]+)\}\}'
        
        def replace_match(match):
            placeholder = match.group(1).strip()
            
            # 检查是否有上下文前缀
            if placeholder.startswith("session_context."):
                key = placeholder[len("session_context."):]
                if session_context:
                    value = session_context.get(key)
                    if value is not None:
                        return str(value)
            elif placeholder.startswith("flow_context."):
                # 兼容旧的 flow_context. 前缀
                key = placeholder[len("flow_context."):]
                if session_context:
                    value = session_context.get(key)
                    if value is not None:
                        return str(value)
            elif placeholder.startswith("user_info."):
                key = placeholder[len("user_info."):]
                if user_info:
                    # 支持特殊键：preferences.key, settings.key, user_info
                    if key.startswith("preferences."):
                        pref_key = key[len("preferences."):]
                        value = user_info.get_preference(pref_key)
                        if value is not None:
                            return str(value)
                    elif key.startswith("settings."):
                        setting_key = key[len("settings."):]
                        value = user_info.get_setting(setting_key)
                        if value is not None:
                            return str(value)
                    elif key == "user_info":
                        user_info_dict = user_info.get_user_info()
                        if user_info_dict:
                            import json
                            return json.dumps(user_info_dict, ensure_ascii=False)
                    else:
                        # UserInfo 没有通用的 get 方法，跳过
                        pass
            else:
                # 默认先从session_context查找
                if session_context:
                    value = session_context.get(placeholder)
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

