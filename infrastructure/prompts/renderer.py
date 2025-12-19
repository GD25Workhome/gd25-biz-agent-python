"""
模板渲染器
负责渲染提示词模板，支持变量替换、条件逻辑和模块组合
"""
from typing import Dict, Any, Optional
import re
import logging

logger = logging.getLogger(__name__)


class TemplateRenderer:
    """模板渲染器"""
    
    @staticmethod
    def render_template(template: str, variables: Dict[str, Any]) -> str:
        """
        渲染模板，支持变量替换
        
        Args:
            template: 模板字符串，支持 {variable_name} 格式的变量
            variables: 变量字典
        
        Returns:
            渲染后的字符串
        """
        if not template:
            return ""
        
        result = template
        
        # 替换变量 {variable_name}
        # 使用正则表达式匹配，避免替换部分匹配的内容
        for key, value in variables.items():
            # 转义特殊字符
            escaped_key = re.escape(key)
            pattern = f"{{{escaped_key}}}"
            result = re.sub(pattern, str(value), result)
        
        return result
    
    @staticmethod
    def evaluate_condition(condition: str, context: Dict[str, Any]) -> bool:
        """
        评估条件表达式
        
        支持的条件表达式示例：
        - {user_id is not None}
        - {len(missing_fields) > 0}
        - {agent_type == "blood_pressure"}
        
        Args:
            condition: 条件表达式字符串
            context: 上下文字典
        
        Returns:
            条件是否满足
        """
        if not condition:
            return True
        
        try:
            # 替换变量 {variable_name}
            # 注意：这里需要小心处理，避免代码注入
            # 只允许简单的表达式，不执行任意代码
            
            # 处理条件表达式
            # 如果整个条件被花括号包围，先去掉外层花括号
            if condition.startswith("{") and condition.endswith("}"):
                # 检查是否是单个变量 {variable} 还是表达式 {expression}
                inner = condition[1:-1].strip()
                # 提取所有可能的变量名（单词，不包括关键字）
                var_pattern = r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b"
                potential_vars = re.findall(var_pattern, inner)
                # 过滤掉Python关键字和内置函数
                python_keywords = {'is', 'not', 'None', 'True', 'False', 'and', 'or', 'in', 'len', 'str', 'int', 'float', 'bool'}
                # 分离出在上下文中的变量和不在上下文中的变量
                vars_in_context = [v for v in potential_vars if v not in python_keywords and v in context]
                vars_not_in_context = [v for v in potential_vars if v not in python_keywords and v not in context]
                
                evaluated_condition = inner
                
                # 先替换在上下文中的变量
                if vars_in_context:
                    # 按长度倒序排序，避免部分匹配问题
                    sorted_matches = sorted(set(vars_in_context), key=len, reverse=True)
                    for var_name in sorted_matches:
                        value = context[var_name]
                        # 根据值的类型进行适当的格式化
                        if isinstance(value, str):
                            replacement = f"'{value}'"
                        elif value is None:
                            replacement = "None"
                        elif isinstance(value, (list, tuple)):
                            replacement = str(list(value))
                        else:
                            replacement = str(value)
                        
                        # 使用单词边界确保完整匹配变量名
                        pattern = r"\b" + re.escape(var_name) + r"\b"
                        evaluated_condition = re.sub(pattern, replacement, evaluated_condition)
                
                # 对于不在上下文中的变量，替换为 None（这样条件可以正确评估，不会产生警告）
                if vars_not_in_context:
                    sorted_missing = sorted(set(vars_not_in_context), key=len, reverse=True)
                    for var_name in sorted_missing:
                        # 使用单词边界确保完整匹配变量名
                        pattern = r"\b" + re.escape(var_name) + r"\b"
                        evaluated_condition = re.sub(pattern, "None", evaluated_condition)
            else:
                # 条件表达式没有被花括号包围，尝试提取变量
                var_pattern = r"\{(\w+)\}"
                matches = re.findall(var_pattern, condition)
                evaluated_condition = condition
                for var_name in matches:
                    if var_name in context:
                        value = context[var_name]
                        replacement = f"'{value}'" if isinstance(value, str) else str(value)
                        pattern = f"\\{{{re.escape(var_name)}\\}}"
                        evaluated_condition = re.sub(pattern, replacement, evaluated_condition)
                    else:
                        pattern = f"\\{{{re.escape(var_name)}\\}}"
                        evaluated_condition = re.sub(pattern, "None", evaluated_condition)
            
            # 执行条件表达式（限制在安全范围内）
            # 提供必要的内置函数（如len）和操作符
            safe_builtins = {
                "__builtins__": {
                    "len": len,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                    "None": None,
                    "True": True,
                    "False": False,
                }
            }
            logger.debug(f"评估条件: {condition} -> {evaluated_condition}")
            try:
                result = eval(evaluated_condition, safe_builtins, {})
                return bool(result)
            except NameError as e:
                # 如果还有未定义的变量，说明替换失败（可能是Python关键字或其他特殊情况）
                # 这种情况应该很少见，因为我们已经将不在上下文中的变量替换为 None
                logger.debug(f"条件表达式包含未定义的变量（可能是关键字或特殊情况）: {evaluated_condition}, 错误: {str(e)}，返回 False")
                return False
            except Exception as e:
                logger.warning(f"条件表达式评估失败: {evaluated_condition}, 错误: {str(e)}")
                return False
            
        except Exception as e:
            logger.warning(f"条件表达式处理失败: {condition}, 错误: {str(e)}，默认返回 False")
            return False
    
    @staticmethod
    def compose_modules(
        modules_content: Dict[str, str],
        order: list,
        separator: str = "\n\n"
    ) -> str:
        """
        组合模块内容
        
        Args:
            modules_content: 模块内容字典 {模块名: 内容}
            order: 模块组合顺序列表
            separator: 模块之间的分隔符
        
        Returns:
            组合后的提示词字符串
        """
        if not modules_content:
            return ""
        
        parts = []
        for module_name in order:
            if module_name in modules_content:
                content = modules_content[module_name].strip()
                if content:  # 只添加非空内容
                    parts.append(content)
        
        # 如果指定了顺序但有些模块不在顺序中，添加剩余的模块
        for module_name, content in modules_content.items():
            if module_name not in order:
                content = content.strip()
                if content:
                    parts.append(content)
        
        return separator.join(parts)
