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
        - intent: 当前意图（字符串）
        - confidence: 意图识别置信度（浮点数，0.0-1.0）
        - need_clarification: 是否需要澄清（布尔值）
        
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
                f"可用变量: intent, confidence, need_clarification"
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
        从流程状态构建变量字典
        
        Args:
            state: 流程状态
            
        Returns:
            Dict[str, Any]: 变量字典，用于条件表达式评估
        """
        names = {
            "intent": state.get("intent"),
            "confidence": state.get("confidence"),
            "need_clarification": state.get("need_clarification"),
        }
        
        # 处理 None 值：如果字段不存在，设置为合理的默认值
        # 这样可以避免条件表达式中的 None 比较问题
        if names["intent"] is None:
            names["intent"] = ""
        if names["confidence"] is None:
            names["confidence"] = 0.0
        if names["need_clarification"] is None:
            names["need_clarification"] = False
        
        return names

