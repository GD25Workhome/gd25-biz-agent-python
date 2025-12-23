"""
提示词管理器
核心类，提供统一的提示词管理接口
"""
from typing import Dict, Any, Optional, List
import logging

from .loader import TemplateLoader, PromptTemplate
from .registry import LoaderRegistry
from .renderer import TemplateRenderer
from .version import VersionManager
from .validator import PromptValidator

logger = logging.getLogger(__name__)


class PromptManager:
    """提示词管理器"""
    
    def __init__(self, templates_dir: str = "config/prompts/templates"):
        """
        初始化提示词管理器
        
        Args:
            templates_dir: 模板文件目录
        """
        self._template_loader = TemplateLoader(templates_dir)
        self._loader_registry = LoaderRegistry()
        self._renderer = TemplateRenderer()
        self._templates: Dict[str, PromptTemplate] = {}
        self._cache: Dict[str, str] = {}
        self._version_manager = VersionManager()
        self._validator = PromptValidator()
        logger.info("提示词管理器已初始化")
    
    def load_template(self, agent_key: str) -> PromptTemplate:
        """
        加载模板
        
        Args:
            agent_key: Agent键名
        
        Returns:
            PromptTemplate对象
        
        Raises:
            FileNotFoundError: 模板文件不存在
        """
        if agent_key in self._templates:
            return self._templates[agent_key]
        
        template = self._template_loader.load(agent_key)
        
        # 验证模板
        is_valid, errors = self._validator.validate_template(template)
        if not is_valid:
            error_msg = f"模板验证失败: {agent_key}, 错误: {', '.join(errors)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 验证模块
        for module_name, module in template.modules.items():
            is_valid, errors = self._validator.validate_module(module)
            if not is_valid:
                error_msg = f"模块验证失败: {agent_key}.{module_name}, 错误: {', '.join(errors)}"
                logger.warning(error_msg)
                # 模块验证失败不阻止加载，只记录警告
        
        self._templates[agent_key] = template
        return template
    
    def render(
        self,
        agent_key: str,
        context: Optional[Dict[str, Any]] = None,
        include_modules: Optional[List[str]] = None,
        exclude_modules: Optional[List[str]] = None
    ) -> str:
        """
        渲染提示词
        
        Args:
            agent_key: Agent键名
            context: 上下文信息（用于动态模块）
            include_modules: 包含的模块列表（None表示全部）
            exclude_modules: 排除的模块列表
        
        Returns:
            渲染后的提示词字符串
        
        Raises:
            FileNotFoundError: 模板文件不存在
            ValueError: 加载器未找到
        """
        context = context or {}
        
        # 检查缓存
        cache_key = self._build_cache_key(agent_key, context, include_modules, exclude_modules)
        if cache_key in self._cache:
            logger.debug(f"使用缓存提示词: {agent_key}")
            return self._cache[cache_key]
        
        # 加载模板
        template = self.load_template(agent_key)
        
        # 加载模块内容
        modules_content = {}
        for module_name, module in template.modules.items():
            # 检查是否启用
            if not module.enabled:
                logger.debug(f"模块 {module_name} 已禁用，跳过")
                continue
            
            # 检查包含/排除
            if include_modules and module_name not in include_modules:
                logger.debug(f"模块 {module_name} 不在包含列表中，跳过")
                continue
            if exclude_modules and module_name in exclude_modules:
                logger.debug(f"模块 {module_name} 在排除列表中，跳过")
                continue
            
            # 检查条件
            if module.condition:
                if not self._renderer.evaluate_condition(module.condition, context):
                    logger.debug(f"模块 {module_name} 条件不满足，跳过")
                    continue
            
            # 加载模块内容
            content = self._load_module_content(module, context)
            if not content:
                raise ValueError(f"模块 {module_name} 内容为空")
            modules_content[module_name] = content
        
        # 组合模块
        order = template.composition.get("order", list(modules_content.keys()))
        separator = template.composition.get("separator", "\n\n")
        prompt = self._renderer.compose_modules(modules_content, order, separator)
        
        # 验证提示词
        is_valid, warnings = self._validator.validate_prompt(prompt, agent_key)
        if warnings:
            for warning in warnings:
                logger.warning(f"提示词验证警告: {agent_key}, {warning}")
        
        # 保存版本（可选，用于版本管理）
        # 注意：这里可以选择性地保存版本，避免版本过多
        # self._version_manager.save_version(agent_key, prompt)
        
        # 缓存结果
        self._cache[cache_key] = prompt
        logger.debug(f"提示词渲染完成: {agent_key}, 模块数: {len(modules_content)}")
        
        return prompt
    
    def _load_module_content(
        self,
        module,
        context: Dict[str, Any]
    ) -> str:
        """
        加载模块内容
        
        Args:
            module: PromptModule对象
            context: 上下文信息
        
        Returns:
            模块内容字符串
        
        Raises:
            ValueError: 加载器未找到
        """
        # 首先尝试根据source获取加载器
        loader = self._loader_registry.get_loader(module.source)
        
        # 如果找不到，尝试使用模块指定的loader类型
        if not loader:
            loader = self._loader_registry.get_loader_by_name(module.loader)
        
        if not loader:
            raise ValueError(f"未找到支持 {module.source} 的加载器（loader类型: {module.loader}）")
        
        # 如果是动态模板，先渲染模板
        if module.template:
            content = self._renderer.render_template(module.template, context)
        else:
            content = loader.load(module.source, context)
        
        return content
    
    def _build_cache_key(
        self,
        agent_key: str,
        context: Dict[str, Any],
        include_modules: Optional[List[str]],
        exclude_modules: Optional[List[str]]
    ) -> str:
        """
        构建缓存键
        
        Args:
            agent_key: Agent键名
            context: 上下文信息
            include_modules: 包含的模块列表
            exclude_modules: 排除的模块列表
        
        Returns:
            缓存键字符串
        """
        parts = [agent_key]
        if include_modules:
            parts.append(f"include:{','.join(sorted(include_modules))}")
        if exclude_modules:
            parts.append(f"exclude:{','.join(sorted(exclude_modules))}")
        if context:
            # 对context进行排序以确保一致性
            sorted_context = sorted(context.items())
            parts.append(f"ctx:{str(sorted_context)}")
        return "|".join(parts)
    
    def reload_template(self, agent_key: str):
        """
        重新加载模板（热更新）
        
        Args:
            agent_key: Agent键名
        """
        if agent_key in self._templates:
            del self._templates[agent_key]
            logger.info(f"已清除模板缓存: {agent_key}")
        
        # 清除相关缓存
        self._clear_cache(agent_key)
        
        # 重新加载
        try:
            self.load_template(agent_key)
            logger.info(f"模板已重新加载: {agent_key}")
        except Exception as e:
            logger.error(f"重新加载模板失败: {agent_key}, 错误: {str(e)}")
            raise
    
    def reload_all_templates(self):
        """重新加载所有模板（热更新）"""
        agent_keys = list(self._templates.keys())
        logger.info(f"开始重新加载所有模板，共 {len(agent_keys)} 个")
        
        for agent_key in agent_keys:
            try:
                self.reload_template(agent_key)
            except Exception as e:
                logger.error(f"重新加载模板失败: {agent_key}, 错误: {str(e)}")
                # 继续加载其他模板
    
    def _clear_cache(self, agent_key: str):
        """
        清除缓存
        
        Args:
            agent_key: Agent键名
        """
        keys_to_remove = [k for k in self._cache.keys() if k.startswith(agent_key + "|")]
        for key in keys_to_remove:
            del self._cache[key]
        logger.debug(f"已清除缓存: {agent_key}, 清除项数: {len(keys_to_remove)}")
    
    def get_version(self, agent_key: str) -> str:
        """
        获取模板版本
        
        Args:
            agent_key: Agent键名
        
        Returns:
            版本字符串
        """
        template = self.load_template(agent_key)
        return template.version
    
    def save_prompt_version(
        self,
        agent_key: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        保存提示词版本
        
        Args:
            agent_key: Agent键名
            prompt: 提示词内容
            metadata: 元数据
        
        Returns:
            版本号
        """
        return self._version_manager.save_version(agent_key, prompt, metadata)
    
    def list_versions(self, agent_key: str) -> List[Dict[str, Any]]:
        """
        列出所有版本
        
        Args:
            agent_key: Agent键名
        
        Returns:
            版本信息列表
        """
        return self._version_manager.list_versions(agent_key)
    
    def get_prompt_version(self, agent_key: str, version: int) -> Optional[str]:
        """
        获取指定版本的提示词
        
        Args:
            agent_key: Agent键名
            version: 版本号
        
        Returns:
            提示词内容
        """
        return self._version_manager.get_version(agent_key, version)
    
    def clear_all_cache(self):
        """清除所有缓存"""
        self._cache.clear()
        logger.info("已清除所有缓存")
    
    def get_cached_keys(self) -> List[str]:
        """
        获取所有缓存键
        
        Returns:
            缓存键列表
        """
        return list(self._cache.keys())
