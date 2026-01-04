"""
提示词管理器
负责提示词的加载、缓存和管理
"""
import logging
from pathlib import Path
from typing import Dict, Optional

from backend.infrastructure.prompts.loader import PromptLoader

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
    
    def get_prompt(self, prompt_path: str, flow_dir: str) -> str:
        """
        获取提示词（如果缓存中没有，则加载并缓存）
        
        Args:
            prompt_path: 提示词路径（相对于流程目录）
            flow_dir: 流程目录路径
            
        Returns:
            str: 提示词内容
        """
        # 解析提示词路径
        resolved_path = PromptLoader.resolve_path(prompt_path, flow_dir)
        cache_key = str(resolved_path)
        
        # 检查缓存
        if cache_key in self._cache:
            logger.debug(f"从缓存获取提示词: {cache_key}")
            return self._cache[cache_key]
        
        # 加载提示词
        prompt_content = PromptLoader.load_from_file(resolved_path)
        
        # 缓存提示词
        self._cache[cache_key] = prompt_content
        logger.info(f"加载并缓存提示词: {cache_key}")
        
        return prompt_content
    
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

