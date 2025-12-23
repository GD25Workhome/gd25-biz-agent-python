"""
性能测试运行脚本
需要应用已经启动并运行在 http://localhost:8000

使用方法：
==========
1. 启动应用：
   uvicorn app.main:app --host 0.0.0.0 --port 8000

2. 运行性能测试：
   python cursor_test/M5_test/langfuse/run_performance_test.py

3. 对比测试：
   - 禁用 Langfuse：设置环境变量 LANGFUSE_ENABLED=False，重启应用，运行测试
   - 启用 Langfuse：设置环境变量 LANGFUSE_ENABLED=True，配置 Langfuse 密钥，重启应用，运行测试
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
test_file_path = Path(__file__).resolve()
project_root = test_file_path.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import requests
import time
import statistics
import uuid
from typing import List, Dict, Optional
from datetime import datetime


class PerformanceMetrics:
    """性能指标类"""
    
    def __init__(self):
        self.response_times: List[float] = []
        self.total_requests: int = 0
        self.successful_requests: int = 0
        self.failed_requests: int = 0
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.errors: List[Dict] = []
    
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
    
    def add_failure(self, error_info: Optional[Dict] = None):
        """记录失败请求"""
        self.failed_requests += 1
        if error_info:
            self.errors.append(error_info)
    
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
        
        if self.errors:
            print(f"\n错误详情（前5个）:")
            for i, error in enumerate(self.errors[:5], 1):
                print(f"  错误 {i}: {error}")
        
        print(f"{'='*60}\n")


def send_chat_request(
    message: str,
    session_id: str,
    user_id: str,
    base_url: str = "http://localhost:8000",
    timeout: int = 60
) -> tuple[float, Dict]:
    """
    发送聊天请求并返回响应时间和响应数据
    
    Args:
        message: 用户消息
        session_id: 会话ID
        user_id: 用户ID
        base_url: 应用基础URL
        timeout: 请求超时时间（秒）
        
    Returns:
        (响应时间, 响应数据)
    """
    url = f"{base_url}/api/v1/chat"
    data = {
        "message": message,
        "session_id": session_id,
        "user_id": user_id
    }
    
    start_time = time.time()
    try:
        response = requests.post(url, json=data, timeout=timeout)
        end_time = time.time()
        
        response_time = end_time - start_time
        
        if response.status_code == 200:
            return response_time, response.json()
        else:
            error_info = {
                "status_code": response.status_code,
                "error": response.text[:200]  # 截断过长错误信息
            }
            return response_time, {"error": error_info}
    except requests.exceptions.Timeout:
        end_time = time.time()
        response_time = end_time - start_time
        error_info = {
            "error_type": "Timeout",
            "timeout": timeout
        }
        return response_time, {"error": error_info}
    except requests.exceptions.ConnectionError:
        end_time = time.time()
        response_time = end_time - start_time
        error_info = {
            "error_type": "ConnectionError",
            "message": "无法连接到服务器，请确保应用已启动"
        }
        return response_time, {"error": error_info}
    except Exception as e:
        end_time = time.time()
        response_time = end_time - start_time
        error_info = {
            "error_type": type(e).__name__,
            "message": str(e)
        }
        return response_time, {"error": error_info}


def run_baseline_test(
    num_requests: int = 10,
    base_url: str = "http://localhost:8000",
    request_interval: float = 0.1
) -> PerformanceMetrics:
    """
    运行基准测试
    
    Args:
        num_requests: 请求数量
        base_url: 应用基础URL
        request_interval: 请求间隔（秒）
        
    Returns:
        性能指标对象
    """
    print(f"\n开始基准测试（{num_requests} 个请求）...")
    print(f"应用地址: {base_url}")
    print(f"请求间隔: {request_interval} 秒")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    metrics = PerformanceMetrics()
    metrics.start()
    
    for i in range(num_requests):
        print(f"\n请求 {i+1}/{num_requests}...", end=" ", flush=True)
        
        response_time, response_data = send_chat_request(
            message=f"测试消息 {i+1}",
            session_id=f"test_session_{uuid.uuid4().hex[:8]}",
            user_id=f"test_user_{uuid.uuid4().hex[:8]}",
            base_url=base_url
        )
        
        metrics.add_response_time(response_time)
        
        if "error" not in response_data:
            metrics.add_success()
            print(f"✅ 成功，响应时间: {response_time:.3f} 秒")
        else:
            metrics.add_failure(response_data.get("error"))
            print(f"❌ 失败，响应时间: {response_time:.3f} 秒")
            error = response_data.get("error", {})
            if isinstance(error, dict):
                error_type = error.get("error_type", "Unknown")
                print(f"   错误类型: {error_type}")
        
        # 避免请求过快
        if i < num_requests - 1:  # 最后一个请求不需要等待
            time.sleep(request_interval)
    
    metrics.stop()
    metrics.print_stats()
    
    return metrics


def compare_performance(
    baseline_metrics: PerformanceMetrics,
    langfuse_metrics: PerformanceMetrics
):
    """
    对比两个性能测试结果
    
    Args:
        baseline_metrics: 基准测试指标（禁用 Langfuse）
        langfuse_metrics: Langfuse 测试指标（启用 Langfuse）
    """
    baseline_stats = baseline_metrics.get_stats()
    langfuse_stats = langfuse_metrics.get_stats()
    
    print("\n" + "="*60)
    print("性能对比分析")
    print("="*60)
    
    # 响应时间对比
    if baseline_stats['avg_response_time'] and langfuse_stats['avg_response_time']:
        overhead = ((langfuse_stats['avg_response_time'] - baseline_stats['avg_response_time']) 
                   / baseline_stats['avg_response_time'] * 100)
        print(f"\n平均响应时间:")
        print(f"  禁用 Langfuse: {baseline_stats['avg_response_time']:.3f} 秒")
        print(f"  启用 Langfuse: {langfuse_stats['avg_response_time']:.3f} 秒")
        print(f"  增加: {overhead:+.2f}%")
        
        # 性能目标检查
        if overhead > 5:
            print(f"  ⚠️  警告: 响应时间增加超过 5% 的目标值")
        else:
            print(f"  ✅ 通过: 响应时间增加在 5% 目标范围内")
    
    # 吞吐量对比
    if baseline_stats['throughput'] and langfuse_stats['throughput']:
        throughput_decrease = ((baseline_stats['throughput'] - langfuse_stats['throughput']) 
                             / baseline_stats['throughput'] * 100)
        print(f"\n吞吐量:")
        print(f"  禁用 Langfuse: {baseline_stats['throughput']:.2f} 请求/秒")
        print(f"  启用 Langfuse: {langfuse_stats['throughput']:.2f} 请求/秒")
        print(f"  下降: {throughput_decrease:+.2f}%")
        
        # 性能目标检查
        if throughput_decrease > 5:
            print(f"  ⚠️  警告: 吞吐量下降超过 5% 的目标值")
        else:
            print(f"  ✅ 通过: 吞吐量下降在 5% 目标范围内")
    
    # P95 响应时间对比
    if baseline_stats['p95_response_time'] and langfuse_stats['p95_response_time']:
        p95_overhead = ((langfuse_stats['p95_response_time'] - baseline_stats['p95_response_time']) 
                       / baseline_stats['p95_response_time'] * 100)
        print(f"\nP95 响应时间:")
        print(f"  禁用 Langfuse: {baseline_stats['p95_response_time']:.3f} 秒")
        print(f"  启用 Langfuse: {langfuse_stats['p95_response_time']:.3f} 秒")
        print(f"  增加: {p95_overhead:+.2f}%")
    
    # P99 响应时间对比
    if baseline_stats['p99_response_time'] and langfuse_stats['p99_response_time']:
        p99_overhead = ((langfuse_stats['p99_response_time'] - baseline_stats['p99_response_time']) 
                       / baseline_stats['p99_response_time'] * 100)
        print(f"\nP99 响应时间:")
        print(f"  禁用 Langfuse: {baseline_stats['p99_response_time']:.3f} 秒")
        print(f"  启用 Langfuse: {langfuse_stats['p99_response_time']:.3f} 秒")
        print(f"  增加: {p99_overhead:+.2f}%")
    
    # 成功率对比
    baseline_success_rate = (baseline_metrics.successful_requests / baseline_metrics.total_requests * 100 
                           if baseline_metrics.total_requests > 0 else 0)
    langfuse_success_rate = (langfuse_metrics.successful_requests / langfuse_metrics.total_requests * 100 
                            if langfuse_metrics.total_requests > 0 else 0)
    print(f"\n成功率:")
    print(f"  禁用 Langfuse: {baseline_success_rate:.2f}%")
    print(f"  启用 Langfuse: {langfuse_success_rate:.2f}%")
    
    print("="*60 + "\n")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="性能测试运行脚本")
    parser.add_argument(
        "--num-requests",
        type=int,
        default=10,
        help="请求数量（默认: 10）"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8000",
        help="应用基础URL（默认: http://localhost:8000）"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.1,
        help="请求间隔（秒，默认: 0.1）"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="运行对比测试（需要手动切换 Langfuse 配置）"
    )
    
    args = parser.parse_args()
    
    print("="*60)
    print("性能测试运行脚本")
    print("="*60)
    print(f"应用地址: {args.base_url}")
    print(f"请求数量: {args.num_requests}")
    print(f"请求间隔: {args.interval} 秒")
    
    # 检查应用是否可访问
    try:
        health_url = f"{args.base_url}/docs"  # 使用 docs 端点检查应用是否运行
        response = requests.get(health_url, timeout=5)
        if response.status_code != 200:
            print(f"\n⚠️  警告: 应用可能未正常运行（状态码: {response.status_code}）")
    except requests.exceptions.ConnectionError:
        print(f"\n❌ 错误: 无法连接到应用服务器 {args.base_url}")
        print("请确保应用已启动：")
        print("  uvicorn app.main:app --host 0.0.0.0 --port 8000")
        return 1
    except Exception as e:
        print(f"\n⚠️  警告: 检查应用连接时出错: {e}")
    
    if args.compare:
        print("\n" + "="*60)
        print("对比测试模式")
        print("="*60)
        print("\n步骤 1: 测试禁用 Langfuse 时的性能")
        print("请确保已设置环境变量: LANGFUSE_ENABLED=False")
        print("并重启应用，然后按 Enter 继续...")
        input()
        
        baseline_metrics = run_baseline_test(
            num_requests=args.num_requests,
            base_url=args.base_url,
            request_interval=args.interval
        )
        
        print("\n" + "="*60)
        print("步骤 2: 测试启用 Langfuse 时的性能")
        print("请确保已设置环境变量: LANGFUSE_ENABLED=True")
        print("并配置 Langfuse 密钥，重启应用，然后按 Enter 继续...")
        input()
        
        langfuse_metrics = run_baseline_test(
            num_requests=args.num_requests,
            base_url=args.base_url,
            request_interval=args.interval
        )
        
        # 对比分析
        compare_performance(baseline_metrics, langfuse_metrics)
    else:
        # 单次测试
        run_baseline_test(
            num_requests=args.num_requests,
            base_url=args.base_url,
            request_interval=args.interval
        )
    
    return 0


if __name__ == "__main__":
    exit(main())

