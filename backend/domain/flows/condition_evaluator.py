"""
流程边条件表达式评估器

GraphBuilder 编译条件边时，route_func 通过本模块评估 flow.yaml 中的 condition 字符串，
决定下一跳节点。使用 simpleeval 限制可执行语法，禁止任意函数调用。
"""
import logging
import re
from typing import Any, Dict

from simpleeval import NameNotDefined, simple_eval

from backend.domain.state import FlowState

logger = logging.getLogger(__name__)


class ConditionEvaluator:
    """
        安全评估 flow.yaml 边条件（如 intent == 'blood_pressure' && confidence >= 0.8）。

        变量来自 persistence_edges_var 与 edges_var 的合并，同名 key 以 edges_var 为准。
    """

    @staticmethod
    def evaluate(condition: str, state: FlowState) -> bool:
        """
            判断条件表达式在当前 state 下是否为真。

            支持 == != < <= > >=、and/or（或 flow.yaml 中的 &&/||）、括号；
            未定义变量、语法错误或评估异常时返回 False 并打日志。

            Args:
                condition: flow.yaml 边 condition 字符串
                state: 当前流程状态（含 edges_var / persistence_edges_var）

            Returns:
                条件成立为 True，否则 False
        """
        if not condition or not condition.strip():
            logger.warning("条件表达式为空")
            return False

        names: Dict[str, Any] = {}
        try:
            # 1. 将 flow.yaml 中的 &&/||/true/false 转为 Python 语法
            normalized_condition = ConditionEvaluator._normalize_condition(condition)

            # 2. 合并 persistence_edges_var 与 edges_var 为 simpleeval 变量表
            names = ConditionEvaluator._build_names_dict(state)

            # 3. simple_eval：仅允许表达式与 names，不注入自定义函数
            result = simple_eval(
                normalized_condition,
                names=names,
            )
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
            将 flow.yaml 条件写法规范为 simpleeval 可解析的 Python 表达式。

            Args:
                condition: 原始条件字符串

            Returns:
                替换 &&/||/true/false 后的表达式
        """
        # 先 || 后 &&，避免 & 被误替换
        normalized = condition.replace("||", " or ")
        normalized = normalized.replace("&&", " and ")
        normalized = re.sub(r"\btrue\b", "True", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\bfalse\b", "False", normalized, flags=re.IGNORECASE)
        return normalized

    @staticmethod
    def _build_names_dict(state: FlowState) -> Dict[str, Any]:
        """
            从 state 合并边变量，并为 None 填充默认值以避免比较异常。

            persistence_edges_var 为底，edges_var 覆盖同名 key。

            Args:
                state: 当前流程状态

            Returns:
                供 simple_eval names= 使用的变量字典
        """
        persistence_edges_var = state.get("persistence_edges_var") or {}
        if not isinstance(persistence_edges_var, dict):
            persistence_edges_var = {}
        names = persistence_edges_var.copy()

        edges_var = state.get("edges_var", {})
        if edges_var is None:
            edges_var = {}
        for k, v in edges_var.items():
            names[k] = v

        # 为 None 设默认值，避免 intent == 'x' 等比较因 None 行为不一致
        for key, value in list(names.items()):
            if value is None:
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
                        names[key] = ""
                else:
                    names[key] = ""

        return names
