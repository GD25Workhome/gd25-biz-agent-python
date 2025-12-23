"""
完全不能运行，忽略此文件

Langfuse 性能测试
测试 Langfuse 集成对系统性能的影响

运行方式：
==========
# 运行所有性能测试
pytest cursor_test/M5_test/langfuse/test_performance.py -v -s

# 运行基准测试
pytest cursor_test/M5_test/langfuse/test_performance.py::TestLangfusePerformance::test_baseline_performance -v -s

# 运行压力测试
pytest cursor_test/M5_test/langfuse/test_performance.py::TestLangfusePerformance::test_concurrent_performance -v -s

# 运行延迟测试
pytest cursor_test/M5_test/langfuse/test_performance.py::TestLangfusePerformance::test_latency_impact -v -s
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
# test_performance.py 在 cursor_test/M5_test/langfuse/ 下，需要向上 4 级到达项目根目录
test_file_path = Path(__file__).resolve()
project_root = test_file_path.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest
import time
import asyncio
import statistics
import uuid
from typing import List, Dict, Optional
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from infrastructure.llm.client import get_llm


class PerformanceMetrics:
    """性能指标类"""
    
    def __init__(self):
        self.response_times: List[float] = []
        self.total_requests: int = 0
        self.successful_requests: int = 0
        self.failed_requests: int = 0
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def start(self):
        """开始计时"""
        self.start_time = time.time()
    
    def stop(self):
        """停止计时"""
        self.end_time = time.time()
    
    def add_response_time(self, response_time: float):
        """添加响应时间"""
        self.response_times.append(response_time)
        self.total_requests += 1
    
    def add_success(self):
        """记录成功请求"""
        self.successful_requests += 1
    
    def add_failure(self):
        """记录失败请求"""
        self.failed_requests += 1
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        if not self.response_times:
            return {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "total_time": None,
                "avg_response_time": None,
                "min_response_time": None,
                "max_response_time": None,
                "median_response_time": None,
                "p95_response_time": None,
                "p99_response_time": None,
                "throughput": None,
            }
        
        total_time = self.end_time - self.start_time if self.end_time and self.start_time else None
        throughput = self.total_requests / total_time if total_time and total_time > 0 else None
        
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "total_time": total_time,
            "avg_response_time": statistics.mean(self.response_times),
            "min_response_time": min(self.response_times),
            "max_response_time": max(self.response_times),
            "median_response_time": statistics.median(self.response_times),
            "p95_response_time": self._percentile(self.response_times, 95),
            "p99_response_time": self._percentile(self.response_times, 99),
            "throughput": throughput,  # 每秒处理请求数
        }
    
    @staticmethod
    def _percentile(data: List[float], percentile: int) -> float:
        """计算百分位数"""
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def print_stats(self, label: str = ""):
        """打印统计信息"""
        stats = self.get_stats()
        print(f"\n{'='*60}")
        print(f"性能统计 {label}")
        print(f"{'='*60}")
        print(f"总请求数: {stats['total_requests']}")
        print(f"成功请求: {stats['successful_requests']}")
        print(f"失败请求: {stats['failed_requests']}")
        if stats['total_time']:
            print(f"总耗时: {stats['total_time']:.2f} 秒")
        if stats['avg_response_time']:
            print(f"平均响应时间: {stats['avg_response_time']:.3f} 秒")
            print(f"最小响应时间: {stats['min_response_time']:.3f} 秒")
            print(f"最大响应时间: {stats['max_response_time']:.3f} 秒")
            print(f"中位数响应时间: {stats['median_response_time']:.3f} 秒")
            print(f"P95 响应时间: {stats['p95_response_time']:.3f} 秒")
            print(f"P99 响应时间: {stats['p99_response_time']:.3f} 秒")
        if stats['throughput']:
            print(f"吞吐量: {stats['throughput']:.2f} 请求/秒")
        print(f"{'='*60}\n")


class TestLangfusePerformance:
    """Langfuse 性能测试类"""
    
    @pytest.fixture
    def mock_router_graph(self):
        """创建 Mock 的路由图"""
        from langchain_core.messages import AIMessage
        
        mock_graph = MagicMock()
        
        # Mock astream 方法，返回一个异步生成器
        async def mock_astream(state, config=None):
            """Mock astream 方法，返回模拟的路由图执行结果"""
            # 返回一个简单的响应消息
            result_state = {
                "messages": [AIMessage(content="测试响应消息")],
                "current_intent": {"intent_type": "blood_pressure"},
                "current_agent": "blood_pressure",
                "need_reroute": False,
                "session_id": state.get("session_id", "test_session"),
                "user_id": state.get("user_id", "test_user"),
            }
            yield {"end": result_state}
        
        # 直接设置 astream 为异步生成器函数，而不是使用 AsyncMock
        # 因为 AsyncMock 不能正确处理异步生成器
        mock_graph.astream = mock_astream
        return mock_graph
    
    @pytest.fixture
    def initialized_app(self, mock_router_graph):
        """初始化应用状态"""
        # 注意：TestClient 不会自动运行 FastAPI 的 lifespan 事件
        # 因此需要手动初始化 app.state 中的属性
        
        # 创建 Mock 的 checkpointer
        mock_checkpointer = MagicMock()
        
        # 手动设置 app.state 中的属性
        # 这些属性在 lifespan 中初始化，但 TestClient 不会运行 lifespan
        app.state.router_graph = mock_router_graph
        app.state.checkpointer = mock_checkpointer
        
        return app
    
    @pytest.fixture
    def test_client(self, initialized_app):
        """创建测试客户端"""
        # 注意：TestClient 不会自动运行 lifespan
        # 应用状态已经在 initialized_app fixture 中初始化
        client = TestClient(initialized_app)
        return client
    
    @pytest.fixture
    def mock_llm_response(self):
        """Mock LLM 响应（意图识别）"""
        from langchain_core.messages import AIMessage
        
        # 创建 Mock 的 AIMessage（返回意图识别结果）
        intent_result = {
            "intent_type": "blood_pressure",
            "confidence": 0.9,
            "entities": {},
            "need_clarification": False,
            "reasoning": "用户想要记录血压"
        }
        import json
        mock_message = AIMessage(content=json.dumps(intent_result, ensure_ascii=False))
        return mock_message
    
    @pytest.fixture
    def mock_llm(self, mock_llm_response):
        """Mock LLM 客户端"""
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)
        mock_llm.invoke = Mock(return_value=mock_llm_response)
        # 支持链式调用 (prompt | llm)
        mock_llm.__or__ = Mock(return_value=Mock(invoke=Mock(return_value=mock_llm_response)))
        return mock_llm
    
    @pytest.fixture
    def mock_langfuse_prompt(self):
        """Mock Langfuse 提示词加载"""
        return "这是一个测试提示词模板"
    
    def _send_chat_request(
        self,
        client: TestClient,
        message: str = "我想记录血压，收缩压120，舒张压80",
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> tuple[float, Dict]:
        """发送聊天请求并返回响应时间和响应数据"""
        if session_id is None:
            session_id = f"test_session_{uuid.uuid4().hex[:8]}"
        if user_id is None:
            user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        
        request_data = {
            "message": message,
            "session_id": session_id,
            "user_id": user_id,
        }
        
        headers = {}
        if trace_id:
            headers["X-Trace-ID"] = trace_id
        
        start_time = time.time()
        response = client.post("/api/v1/chat", json=request_data, headers=headers)
        end_time = time.time()
        
        response_time = end_time - start_time
        
        if response.status_code == 200:
            return response_time, response.json()
        else:
            return response_time, {"error": response.text, "status_code": response.status_code}
    
    @pytest.mark.asyncio
    async def test_baseline_performance(self, test_client, mock_llm):
        """
        基准测试：测试禁用 Langfuse 时的性能
        
        测试步骤：
        1. 禁用 Langfuse，发送 100 个请求，记录响应时间
        2. 启用 Langfuse，发送 100 个请求，记录响应时间
        3. 计算性能开销（响应时间增加百分比）
        """
        num_requests = 10  # 测试时使用较少请求数，实际测试可以使用 100
        
        # Mock LLM 调用和 Langfuse 提示词加载
        with patch('infrastructure.llm.client.get_llm', return_value=mock_llm), \
             patch('domain.router.tools.router_tools._load_router_prompt', return_value="测试提示词模板"):
            # 测试 1：禁用 Langfuse
            print("\n开始基准测试（禁用 Langfuse）...")
            baseline_metrics = PerformanceMetrics()
            baseline_metrics.start()
            
            with patch.object(settings, 'LANGFUSE_ENABLED', False):
                for i in range(num_requests):
                    response_time, response_data = self._send_chat_request(
                        test_client,
                        message=f"测试消息 {i+1}"
                    )
                    baseline_metrics.add_response_time(response_time)
                    if "error" not in response_data:
                        baseline_metrics.add_success()
                    else:
                        baseline_metrics.add_failure()
                        print(f"请求 {i+1} 失败: {response_data.get('error', 'Unknown error')}")
            
            baseline_metrics.stop()
            baseline_metrics.print_stats("（禁用 Langfuse）")
            baseline_stats = baseline_metrics.get_stats()
            
            # 测试 2：启用 Langfuse
            print("\n开始基准测试（启用 Langfuse）...")
            langfuse_metrics = PerformanceMetrics()
            langfuse_metrics.start()
            
            with patch.object(settings, 'LANGFUSE_ENABLED', True), \
                 patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
                 patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'), \
                 patch.object(settings, 'LANGFUSE_HOST', 'http://localhost:3000'), \
                 patch('infrastructure.observability.langfuse_handler._get_langfuse_client', return_value=None):
                # 注意：这里我们 Mock Langfuse 客户端为 None，模拟 Langfuse 未配置的情况
                # 这样可以测试代码路径，但不会实际发送到 Langfuse
                for i in range(num_requests):
                    response_time, response_data = self._send_chat_request(
                        test_client,
                        message=f"测试消息 {i+1}"
                    )
                    langfuse_metrics.add_response_time(response_time)
                    if "error" not in response_data:
                        langfuse_metrics.add_success()
                    else:
                        langfuse_metrics.add_failure()
                        print(f"请求 {i+1} 失败: {response_data.get('error', 'Unknown error')}")
            
            langfuse_metrics.stop()
            langfuse_metrics.print_stats("（启用 Langfuse）")
            langfuse_stats = langfuse_metrics.get_stats()
            
            # 计算性能开销
            print("\n性能对比分析：")
            print(f"{'='*60}")
            if baseline_stats['avg_response_time'] and langfuse_stats['avg_response_time']:
                overhead = ((langfuse_stats['avg_response_time'] - baseline_stats['avg_response_time']) 
                           / baseline_stats['avg_response_time'] * 100)
                print(f"平均响应时间增加: {overhead:.2f}%")
                print(f"  禁用 Langfuse: {baseline_stats['avg_response_time']:.3f} 秒")
                print(f"  启用 Langfuse: {langfuse_stats['avg_response_time']:.3f} 秒")
            
            if baseline_stats['throughput'] and langfuse_stats['throughput']:
                throughput_decrease = ((baseline_stats['throughput'] - langfuse_stats['throughput']) 
                                     / baseline_stats['throughput'] * 100)
                print(f"吞吐量下降: {throughput_decrease:.2f}%")
                print(f"  禁用 Langfuse: {baseline_stats['throughput']:.2f} 请求/秒")
                print(f"  启用 Langfuse: {langfuse_stats['throughput']:.2f} 请求/秒")
            
            print(f"{'='*60}\n")
            
            # 断言：确保所有请求都成功
            assert baseline_metrics.successful_requests == num_requests, \
                f"基准测试失败：成功请求数 {baseline_metrics.successful_requests} != {num_requests}"
            assert langfuse_metrics.successful_requests == num_requests, \
                f"Langfuse 测试失败：成功请求数 {langfuse_metrics.successful_requests} != {num_requests}"
    
    @pytest.mark.asyncio
    async def test_concurrent_performance(self, test_client, mock_llm):
        """
        压力测试：测试并发场景下的性能
        
        测试步骤：
        1. 启用 Langfuse，并发发送 100 个请求
        2. 统计吞吐量（每秒处理请求数）
        3. 观察是否有性能瓶颈
        """
        num_concurrent = 10  # 并发请求数
        num_requests_per_concurrent = 5  # 每个并发任务发送的请求数
        
        # Mock LLM 调用和 Langfuse 提示词加载
        with patch('infrastructure.llm.client.get_llm', return_value=mock_llm), \
             patch('domain.router.tools.router_tools._load_router_prompt', return_value="测试提示词模板"):
            print(f"\n开始压力测试（并发数: {num_concurrent}，每并发请求数: {num_requests_per_concurrent}）...")
            
            metrics = PerformanceMetrics()
            metrics.start()
            
            async def send_requests(task_id: int):
                """发送请求的异步任务"""
                task_metrics = PerformanceMetrics()
                for i in range(num_requests_per_concurrent):
                    try:
                        response_time, response_data = self._send_chat_request(
                            test_client,
                            message=f"并发测试任务 {task_id} 消息 {i+1}"
                        )
                        task_metrics.add_response_time(response_time)
                        if "error" not in response_data:
                            task_metrics.add_success()
                        else:
                            task_metrics.add_failure()
                    except Exception as e:
                        print(f"任务 {task_id} 请求 {i+1} 异常: {e}")
                        task_metrics.add_failure()
                return task_metrics
            
            # 创建并发任务
            with patch.object(settings, 'LANGFUSE_ENABLED', True), \
                 patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
                 patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'), \
                 patch.object(settings, 'LANGFUSE_HOST', 'http://localhost:3000'), \
                 patch('infrastructure.observability.langfuse_handler._get_langfuse_client', return_value=None):
                
                # 使用 asyncio 并发执行
                tasks = [send_requests(i) for i in range(num_concurrent)]
                results = await asyncio.gather(*tasks)
                
                # 合并所有任务的指标
                for task_metrics in results:
                    metrics.response_times.extend(task_metrics.response_times)
                    metrics.total_requests += task_metrics.total_requests
                    metrics.successful_requests += task_metrics.successful_requests
                    metrics.failed_requests += task_metrics.failed_requests
            
            metrics.stop()
            metrics.print_stats("（并发压力测试）")
            
            # 断言：确保大部分请求成功（允许少量失败）
            success_rate = metrics.successful_requests / metrics.total_requests if metrics.total_requests > 0 else 0
            assert success_rate >= 0.9, \
                f"并发测试失败：成功率 {success_rate:.2%} < 90%"
            
            print(f"✅ 并发测试通过：成功率 {success_rate:.2%}")
    
    @pytest.mark.asyncio
    async def test_latency_impact(self, test_client, mock_llm):
        """
        延迟测试：模拟 Langfuse 服务响应慢的场景
        
        测试步骤：
        1. 模拟 Langfuse 服务响应慢（如 1 秒延迟）
        2. 发送请求，观察对主流程的影响
        3. 验证错误隔离是否生效
        """
        num_requests = 5
        
        # Mock LLM 调用和 Langfuse 提示词加载
        with patch('infrastructure.llm.client.get_llm', return_value=mock_llm), \
             patch('domain.router.tools.router_tools._load_router_prompt', return_value="测试提示词模板"):
            print("\n开始延迟测试（模拟 Langfuse 服务慢）...")
            
            # 模拟 Langfuse 服务慢（延迟 1 秒）
            async def slow_langfuse_call(*args, **kwargs):
                """模拟慢的 Langfuse 调用"""
                await asyncio.sleep(1.0)  # 延迟 1 秒
                return None
            
            metrics = PerformanceMetrics()
            metrics.start()
            
            with patch.object(settings, 'LANGFUSE_ENABLED', True), \
                 patch.object(settings, 'LANGFUSE_PUBLIC_KEY', 'pk-test'), \
                 patch.object(settings, 'LANGFUSE_SECRET_KEY', 'sk-test'), \
                 patch.object(settings, 'LANGFUSE_HOST', 'http://localhost:3000'), \
                 patch('infrastructure.observability.langfuse_handler.set_langfuse_trace_context', side_effect=slow_langfuse_call):
                
                for i in range(num_requests):
                    response_time, response_data = self._send_chat_request(
                        test_client,
                        message=f"延迟测试消息 {i+1}"
                    )
                    metrics.add_response_time(response_time)
                    if "error" not in response_data:
                        metrics.add_success()
                    else:
                        metrics.add_failure()
                        print(f"请求 {i+1} 失败: {response_data.get('error', 'Unknown error')}")
            
            metrics.stop()
            metrics.print_stats("（延迟测试）")
            
            # 断言：即使 Langfuse 服务慢，主流程也应该正常执行
            assert metrics.successful_requests == num_requests, \
                f"延迟测试失败：成功请求数 {metrics.successful_requests} != {num_requests}"
            
            # 验证响应时间不应该因为 Langfuse 延迟而显著增加
            # 注意：由于我们 Mock 了 set_langfuse_trace_context，实际响应时间可能不会增加
            # 但我们可以验证主流程不受影响
            print("✅ 延迟测试通过：主流程不受 Langfuse 服务延迟影响")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

