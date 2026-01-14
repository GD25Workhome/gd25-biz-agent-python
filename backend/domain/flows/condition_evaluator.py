"""
条件表达式评估器
使用 simpleeval 库安全地评估流程边条件表达式
"""
import logging
import re
from typing import Dict, Any
from simpleeval import simple_eval, NameNotDefined

from backend.domain.state import FlowState

logger = logging.getLogger(__name__)


class ConditionEvaluator:
    """条件表达式评估器"""
    
    @staticmethod
    def evaluate(condition: str, state: FlowState) -> bool:
        """
        评估条件表达式
        
        支持的操作符：
        - 比较运算符：==, !=, <, <=, >, >=
        - 逻辑运算符：and (&&), or (||), not (!)
        - 括号：用于改变运算优先级
        
        支持的变量：
        - 所有存储在 state.edges_var 中的变量都可以在条件表达式中使用
        - 变量名直接对应 edges_var 中的 key
        - 例如：如果 edges_var 中有 {"intent": "record", "confidence": 0.9}，则可以使用 intent == "record" && confidence >= 0.8
        
        Args:
            condition: 条件表达式字符串（如 "intent == 'blood_pressure' && confidence >= 0.8"）
            state: 流程状态
            
        Returns:
            bool: 条件是否为真
            
        Examples:
            >>> evaluate("intent == 'blood_pressure'", state)
            >>> evaluate("intent == 'blood_pressure' and confidence >= 0.8", state)
            >>> evaluate("intent == 'greeting' or need_clarification == True", state)
        """
        if not condition or not condition.strip():
            logger.warning("条件表达式为空")
            return False
        
        try:
            # 将条件表达式中的 && 和 || 转换为 Python 的 and 和 or
            # 同时处理 True/true 和 False/false
            normalized_condition = ConditionEvaluator._normalize_condition(condition)
            
            # 构建变量字典，从状态中获取值
            names = ConditionEvaluator._build_names_dict(state)
            
            # 使用 simple_eval 安全地评估表达式
            # 不传入 operators 参数，使用 simpleeval 的默认操作符（安全且支持所有常用操作符）
            # 不传入 functions 参数，禁止使用函数，提高安全性
            result = simple_eval(
                normalized_condition,
                names=names
            )
            
            # 将结果转换为布尔值
            return bool(result)
            
        except NameNotDefined as e:
            logger.warning(
                f"条件表达式中使用了未定义的变量: {e.name}。"
                f"条件: {condition}。"
                f"可用变量: {list(names.keys()) if names else '无'}"
            )
            return False
        except SyntaxError as e:
            logger.error(f"条件表达式语法错误: {condition}, 错误: {e}")
            return False
        except Exception as e:
            logger.error(f"条件表达式评估失败: {condition}, 错误: {e}")
            return False
    
    @staticmethod
    def _normalize_condition(condition: str) -> str:
        """
        规范化条件表达式
        
        将 JavaScript 风格的逻辑运算符转换为 Python 风格：
        - && -> and
        - || -> or
        - true -> True
        - false -> False
        
        Args:
            condition: 原始条件表达式
            
        Returns:
            str: 规范化后的条件表达式
        """
        # 替换逻辑运算符（注意顺序：先替换 ||，避免 && 中的 & 被误替换）
        normalized = condition.replace("||", " or ")
        normalized = normalized.replace("&&", " and ")
        
        # 替换布尔值（使用单词边界确保不会误替换）
        # 替换 true（注意大小写）
        normalized = re.sub(r'\btrue\b', 'True', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\bfalse\b', 'False', normalized, flags=re.IGNORECASE)
        
        return normalized
    
    @staticmethod
    def _build_names_dict(state: FlowState) -> Dict[str, Any]:
        """
        从流程状态构建变量字典（通用化设计）
        
        直接从 edges_var 获取所有变量，不再定制化
        
        Args:
            state: 流程状态
            
        Returns:
            Dict[str, Any]: 变量字典，用于条件表达式评估
        """
        # 直接从 edges_var 获取所有变量
        edges_var = state.get("edges_var", {})
        if edges_var is None:
            edges_var = {}
        
        # 直接使用 edges_var 作为变量字典
        names = edges_var.copy()
        
        # 处理 None 值：为所有 None 值设置合理的默认值
        # 这样可以避免条件表达式中的 None 比较问题
        for key, value in list(names.items()):
            if value is None:
                # 根据 key 的特征设置默认值
                if isinstance(key, str):
                    if key.endswith("_success"):
                        names[key] = False
                    elif key.endswith("_type"):
                        names[key] = ""
                    elif key == "confidence":
                        names[key] = 0.0
                    elif key == "need_clarification":
                        names[key] = False
                    elif key == "intent":
                        names[key] = ""
                    else:
                        # 其他情况，根据值的类型推断（但 value 是 None，所以使用空字符串）
                        names[key] = ""
                else:
                    names[key] = ""
        
        return names

