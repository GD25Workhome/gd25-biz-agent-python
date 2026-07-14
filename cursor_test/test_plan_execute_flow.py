"""
Plan-and-Execute 路线 B 单元测试与流程编译测试
"""
import pytest

from backend.domain.planning.summarizer import summarize_tool_result
from backend.domain.planning.state_helpers import merge_edges_var, validate_tool_names
from backend.domain.planning.models import PlanStepModel
from backend.domain.flows.condition_evaluator import ConditionEvaluator
from backend.domain.state import FlowState


class TestSummarizeToolResult:
    """工具结果摘要测试"""

    def test_short_string_unchanged(self) -> None:
        """短字符串不截断"""
        assert summarize_tool_result("hello", max_chars=100) == "hello"

    def test_long_string_truncated(self) -> None:
        """长字符串截断并追加标记"""
        text = "x" * 3000
        result = summarize_tool_result(text, max_chars=100)
        assert len(result) > 100
        assert "结果已截断" in result

    def test_dict_serialized(self) -> None:
        """字典序列化为 JSON 字符串"""
        result = summarize_tool_result({"a": 1, "b": [1, 2]})
        assert '"a"' in result


class TestMergeEdgesVar:
    """edges_var 合并测试"""

    def test_merge_preserves_existing_keys(self) -> None:
        """合并时保留已有键"""
        state: FlowState = {
            "edges_var": {"intent": "qa", "confidence": 0.9},
        }
        merged = merge_edges_var(state, {"has_plan": True, "plan_finished": False})
        assert merged["intent"] == "qa"
        assert merged["confidence"] == 0.9
        assert merged["has_plan"] is True
        assert merged["plan_finished"] is False


class TestValidateToolNames:
    """计划步骤工具名校验测试"""

    def test_invalid_tool_cleared(self) -> None:
        """未知工具名清空为 None"""
        steps = [
            PlanStepModel(
                step_id="step_1",
                description="查询血压",
                tool_name="query_blood_pressure",
            ),
            PlanStepModel(
                step_id="step_2",
                description="无效工具",
                tool_name="unknown_tool",
            ),
        ]
        allowed = ["query_blood_pressure", "query_medication"]
        validated = validate_tool_names(steps, allowed)
        assert validated[0].tool_name == "query_blood_pressure"
        assert validated[1].tool_name is None


class TestConditionEvaluatorPlanRoutes:
    """Plan-and-Execute 条件边路由测试"""

    def _state_with_edges(self, edges: dict) -> FlowState:
        return {"edges_var": edges}

    def test_has_plan_routes_to_executor(self) -> None:
        """has_plan=true 时路由到 executor"""
        state = self._state_with_edges({"has_plan": True})
        assert ConditionEvaluator.evaluate("has_plan == true", state) is True

    def test_plan_finished_routes_to_end(self) -> None:
        """plan_finished=true 时结束"""
        state = self._state_with_edges({"plan_finished": True, "should_abort": False})
        assert ConditionEvaluator.evaluate("plan_finished == true || should_abort == true", state) is True

    def test_continue_loop_condition(self) -> None:
        """未完成且未熔断时继续循环"""
        state = self._state_with_edges({"plan_finished": False, "should_abort": False})
        assert ConditionEvaluator.evaluate("plan_finished != true && should_abort != true", state) is True

    def test_should_abort_stops_loop(self) -> None:
        """should_abort=true 时停止循环"""
        state = self._state_with_edges({"plan_finished": False, "should_abort": True})
        assert ConditionEvaluator.evaluate("plan_finished != true && should_abort != true", state) is False


class TestPlanExecuteFlowCompile:
    """plan_execute_agent 流程编译测试"""

    @pytest.fixture(autouse=True)
    def setup_flow_env(self) -> None:
        """加载模型供应商与工具，供流程编译与节点创建使用"""
        from backend.app.config import find_project_root
        from backend.domain.tools import init_tools
        from backend.infrastructure.llm.providers.manager import ProviderManager

        project_root = find_project_root()
        config_path = project_root / "config" / "model_providers.yaml"
        if not ProviderManager.is_loaded():
            ProviderManager.load_providers(config_path)
        init_tools()

    def test_flow_compiles_without_error(self) -> None:
        """流程图可成功编译"""
        from backend.domain.flows.manager import FlowManager

        # 清除缓存，强制重新扫描与编译
        FlowManager._compiled_graphs.pop("plan_execute_agent", None)
        FlowManager._flow_definitions.pop("plan_execute_agent", None)

        graph = FlowManager.get_flow("plan_execute_agent")
        assert graph is not None

    def test_flow_definition_has_plan_nodes(self) -> None:
        """流程定义包含 planner / plan_executor / replanner 节点"""
        from backend.domain.flows.manager import FlowManager

        FlowManager.scan_flows()
        flow_def = FlowManager._flow_definitions.get("plan_execute_agent")
        assert flow_def is not None
        node_types = {n.type for n in flow_def.nodes}
        assert "planner" in node_types
        assert "plan_executor" in node_types
        assert "replanner" in node_types
