"""
提示词验证器
验证提示词模板格式、模块内容和变量引用
"""
from typing import Dict, Any, List, Optional
import re
import logging

from .loader import PromptTemplate, PromptModule

logger = logging.getLogger(__name__)


class PromptValidator:
    """提示词验证器"""
    
    @staticmethod
    def validate_template(template: PromptTemplate) -> tuple[bool, List[str]]:
        """
        验证模板格式
        
        Args:
            template: PromptTemplate对象
        
        Returns:
            (是否有效, 错误列表)
        """
        errors = []
        
        # 验证必需字段
        if not template.agent_key:
            errors.append("模板缺少 agent_key 字段")
        
        if not template.version:
            errors.append("模板缺少 version 字段")
        
        # 验证模块
        if not template.modules:
            errors.append("模板没有定义任何模块")
        
        # 验证必需模块（某些模板可能不需要必需模块，如router_tools）
        # 只对Agent模板要求必需模块
        if template.agent_key.endswith("_agent"):
            required_modules = [name for name, module in template.modules.items() 
                              if module.type == "required"]
            if not required_modules:
                errors.append("Agent模板缺少必需模块（type=required）")
        
        # 验证组合规则
        if not template.composition:
            errors.append("模板缺少 composition 配置")
        else:
            order = template.composition.get("order", [])
            if order:
                # 检查order中的模块是否都存在
                for module_name in order:
                    if module_name not in template.modules:
                        errors.append(f"组合顺序中引用了不存在的模块: {module_name}")
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    @staticmethod
    def validate_module(module: PromptModule) -> tuple[bool, List[str]]:
        """
        验证模块配置
        
        Args:
            module: PromptModule对象
        
        Returns:
            (是否有效, 错误列表)
        """
        errors = []
        
        # 验证必需字段
        if not module.name:
            errors.append("模块缺少 name 字段")
        
        if not module.loader:
            errors.append(f"模块 {module.name} 缺少 loader 字段")
        
        if not module.source and not module.template:
            errors.append(f"模块 {module.name} 缺少 source 或 template 字段")
        
        # 验证类型
        valid_types = ["required", "optional", "business"]
        if module.type not in valid_types:
            errors.append(f"模块 {module.name} 的类型无效: {module.type}, 应为 {valid_types} 之一")
        
        # 验证加载器类型
        valid_loaders = ["config", "file", "dynamic", "database"]
        if module.loader not in valid_loaders:
            errors.append(f"模块 {module.name} 的加载器类型无效: {module.loader}, 应为 {valid_loaders} 之一")
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    @staticmethod
    def validate_variable_references(template: PromptTemplate, context: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        验证变量引用
        
        Args:
            template: PromptTemplate对象
            context: 上下文字典
        
        Returns:
            (是否有效, 警告列表)
        """
        warnings = []
        
        # 提取所有模板中的变量引用
        var_pattern = r"\{(\w+)\}"
        all_vars = set()
        
        for module in template.modules.values():
            if module.template:
                matches = re.findall(var_pattern, module.template)
                all_vars.update(matches)
        
        # 检查未定义的变量
        for var_name in all_vars:
            if var_name not in context:
                warnings.append(f"变量 {var_name} 在模板中被引用但上下文中不存在")
        
        # 检查上下文中的变量是否被使用（可选，仅作为提示）
        # 这个检查可以省略，因为上下文可能包含额外的变量
        
        is_valid = len(warnings) == 0
        return is_valid, warnings
    
    @staticmethod
    def validate_prompt(prompt: str, agent_key: str) -> tuple[bool, List[str]]:
        """
        验证最终渲染的提示词
        
        Args:
            prompt: 提示词内容
            agent_key: Agent键名
        
        Returns:
            (是否有效, 警告列表)
        """
        warnings = []
        
        # 检查提示词是否为空
        if not prompt or not prompt.strip():
            warnings.append(f"提示词为空: {agent_key}")
        
        # 检查提示词长度（可选）
        if len(prompt) > 10000:
            warnings.append(f"提示词过长: {agent_key}, 长度: {len(prompt)}")
        
        # 检查是否包含未替换的变量（可选）
        var_pattern = r"\{(\w+)\}"
        unmatched_vars = re.findall(var_pattern, prompt)
        if unmatched_vars:
            warnings.append(f"提示词中包含未替换的变量: {unmatched_vars}")
        
        is_valid = len(warnings) == 0
        return is_valid, warnings
