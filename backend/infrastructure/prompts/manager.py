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
    _cache_flow_rule: Dict[str, str] = {}  # 缓存：key为flow_rule文件名（不含扩展名），value为文件内容
    
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
        
        # 替换占位符（如 {route_llm_resopnse}）
        prompt_content = self._replace_flow_rule_placeholders(prompt_content)
        
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

    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._cache_flow_rule.clear()
        logger.info("提示词缓存已清空")
    
    def get_cache_size(self) -> int:
        """
        获取缓存大小
        
        Returns:
            int: 缓存中提示词的数量
        """
        return len(self._cache)
    
    @property
    def cached_flow_rule(self) -> Dict[str, str]:
        """
        获取缓存的 flow_rule 文件内容
        
        如果缓存为空，会自动触发缓存逻辑
        
        Returns:
            Dict[str, str]: key为文件名（不含扩展名），value为文件内容
        """
        if not self._cache_flow_rule:
            self._load_flow_rule_cache()
        return self._cache_flow_rule
    
    def _load_flow_rule_cache(self) -> None:
        """
        加载并缓存 config/flows/flow_rule 目录下的所有文件
        
        该方法会：
        1. 扫描 config/flows/flow_rule 目录下的所有 .md 文件
        2. 读取文件内容并缓存
        3. key 为文件名（不含扩展名），value 为文件内容
        """
        # 获取项目根目录（假设 manager.py 在 backend/infrastructure/prompts/ 下）
        # 项目根目录应该是 backend 的父目录
        current_file = Path(__file__)
        # backend/infrastructure/prompts/manager.py -> 项目根目录
        project_root = current_file.parent.parent.parent.parent
        flow_rule_dir = project_root / "config" / "flows" / "flow_rule"
        
        if not flow_rule_dir.exists():
            logger.warning(f"flow_rule 目录不存在: {flow_rule_dir}")
            return
        
        # 扫描目录下的所有 .md 文件
        for file_path in flow_rule_dir.glob("*.md"):
            # 获取文件名（不含扩展名）作为 key
            file_name = file_path.stem
            
            try:
                # 读取文件内容
                content = PromptLoader.load_from_file(file_path)
                self._cache_flow_rule[file_name] = content
                logger.debug(f"已缓存 flow_rule 文件: {file_name}")
            except Exception as e:
                logger.error(f"加载 flow_rule 文件失败: {file_path}, 错误: {e}")
    
    def _replace_flow_rule_placeholders(self, template: str) -> str:
        """
        替换提示词模板中的 flow_rule 占位符
        
        支持的占位符格式：
        - {route_llm_resopnse}: 替换为 route_llm_resopnse.md 的内容
        - {end_llm_resopnse}: 替换为 end_llm_resopnse.md 的内容
        - {llm_rule_part}: 替换为 llm_rule_part.md 的内容
        
        只替换在 flow_rule 目录中实际存在的文件对应的占位符，其他占位符不处理。
        
        Args:
            template: 提示词模板
            
        Returns:
            str: 替换后的提示词内容
        """
        # 获取缓存的 flow_rule 文件
        flow_rule_cache = self.cached_flow_rule
        
        if not flow_rule_cache:
            logger.warning("flow_rule 缓存为空，无法替换占位符")
            return template
        
        # 匹配占位符：{key}
        pattern = r'\{([^}]+)\}'
        
        def replace_match(match):
            placeholder_key = match.group(1).strip()
            
            # 检查缓存中是否存在对应的文件
            if placeholder_key in flow_rule_cache:
                content = flow_rule_cache[placeholder_key]
                logger.debug(f"替换占位符: {{{placeholder_key}}}")
                return content
            else:
                # 如果不存在，保留原占位符
                logger.debug(f"占位符未找到对应的 flow_rule 文件: {{{placeholder_key}}}，保留原占位符")
                return match.group(0)  # 保留原占位符
        
        result = re.sub(pattern, replace_match, template)
        return result


# 创建全局提示词管理器实例
prompt_manager = PromptManager()

