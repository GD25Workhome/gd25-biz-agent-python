"""
TraceId 并发测试
测试在多线程和多协程并发场景下，traceId 是否会出现串用问题

运行方式：
==========
# 直接运行测试文件
python cursor_test/langfuse/traceId/test_trace_id_concurrency.py

# 或者在项目根目录运行
python -m cursor_test.langfuse.traceId.test_trace_id_concurrency
"""
import sys
import threading
import asyncio
import time
import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict
import logging

# 从当前目录导入 langfuse_handler（本地副本）
# test_trace_id_concurrency.py 位于: cursor_test/langfuse/traceId/test_trace_id_concurrency.py
# langfuse_handler.py 位于同一目录
test_file_path = Path(__file__).resolve()
test_dir = test_file_path.parent

# 将当前目录添加到 Python 路径，以便导入同目录下的模块
if str(test_dir) not in sys.path:
    sys.path.insert(0, str(test_dir))

# 从本地副本导入
from langfuse_handler import (
    set_langfuse_trace_context,
    get_current_trace_id,
    get_langfuse_client,
    is_langfuse_available
)

# 配置日志（降低日志级别，避免输出过多）
logging.basicConfig(
    level=logging.WARNING,  # 只显示警告和错误
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestResult:
    """测试结果记录类"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
        self.details = []  # 详细测试结果
    
    def add_pass(self, test_name: str, details: Optional[str] = None):
        """记录通过的测试"""
        self.passed += 1
        print(f"✅ {test_name}")
        if details:
            self.details.append(f"✅ {test_name}: {details}")
    
    def add_fail(self, test_name: str, error: str, details: Optional[Dict] = None):
        """记录失败的测试"""
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"❌ {test_name}: {error}")
        if details:
            self.details.append(f"❌ {test_name}: {error}\n详情: {details}")
    
    def summary(self):
        """打印测试总结"""
        print("\n" + "="*80)
        print("测试总结")
        print("="*80)
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")
        print(f"总计: {self.passed + self.failed}")
        print(f"成功率: {self.passed / (self.passed + self.failed) * 100:.2f}%")
        
        if self.errors:
            print("\n失败详情:")
            for error in self.errors:
                print(f"  - {error}")
        
        if self.details:
            print("\n详细结果:")
            for detail in self.details[-10:]:  # 只显示最后10条
                print(f"  {detail}")
        
        print("="*80)
        return self.failed == 0


# 全局测试结果记录
test_result = TestResult()


def test_multithread_trace_id_isolation(concurrent_count: int = 50) -> bool:
    """
    测试多线程并发场景下 traceId 隔离性
    
    Args:
        concurrent_count: 并发线程数量
        
    Returns:
        bool: 测试是否通过
    """
    print(f"\n{'='*80}")
    print(f"测试1: 多线程并发测试 (并发数: {concurrent_count})")
    print(f"{'='*80}")
    
    # 生成测试方案简写和时间戳
    test_short_name = "MT"  # MultiThread
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    test_name_prefix = f"{test_short_name}{timestamp}"
    
    # 使用线程安全的字典存储结果
    results: Dict[int, Dict] = {}
    results_lock = threading.Lock()
    
    def worker(thread_id: int, trace_id: str):
        """工作线程函数"""
        try:
            # 调用 set_langfuse_trace_context，使用格式化的 name
            actual_trace_id = set_langfuse_trace_context(
                name=f"{test_name_prefix}_t{thread_id:03d}",
                user_id=f"user_{thread_id:03d}",
                session_id=f"session_{thread_id:03d}",
                trace_id=trace_id,
                metadata={"thread_id": thread_id, "test_type": "multithread", "test_name": test_name_prefix}
            )
            
            # 获取 ContextVar 中的值
            context_trace_id = get_current_trace_id()
            
            # 记录结果
            with results_lock:
                results[thread_id] = {
                    "expected": trace_id,
                    "actual": actual_trace_id,
                    "context": context_trace_id,
                    "match": actual_trace_id == trace_id and context_trace_id == trace_id,
                    "thread_id": thread_id
                }
        except Exception as e:
            with results_lock:
                results[thread_id] = {
                    "expected": trace_id,
                    "actual": None,
                    "context": None,
                    "match": False,
                    "error": str(e),
                    "thread_id": thread_id
                }
    
    # 创建多个线程并发执行
    threads = []
    start_time = time.time()
    
    # 预生成所有符合格式要求的 traceId（32位十六进制字符）
    trace_ids = [secrets.token_hex(16) for _ in range(concurrent_count)]
    
    for i in range(concurrent_count):
        trace_id = trace_ids[i]
        t = threading.Thread(target=worker, args=(i, trace_id))
        threads.append(t)
        t.start()
    
    # 等待所有线程完成
    for t in threads:
        t.join()
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    # 验证结果
    success_count = sum(1 for r in results.values() if r.get("match", False))
    fail_count = concurrent_count - success_count
    
    print(f"\n执行时间: {elapsed_time:.2f} 秒")
    print(f"成功: {success_count}/{concurrent_count}")
    print(f"失败: {fail_count}/{concurrent_count}")
    
    # 检查是否有失败的案例
    failed_cases = []
    for thread_id, result in results.items():
        if not result.get("match", False):
            failed_cases.append({
                "thread_id": thread_id,
                "expected": result.get("expected"),
                "actual": result.get("actual"),
                "context": result.get("context"),
                "error": result.get("error")
            })
    
    if failed_cases:
        print(f"\n失败的案例 (前10个):")
        for case in failed_cases[:10]:
            print(f"  线程 {case['thread_id']}: 期望={case['expected']}, "
                  f"实际={case['actual']}, 上下文={case['context']}")
            if case.get('error'):
                print(f"    错误: {case['error']}")
    
    # 检查是否有 traceId 串用（检查是否有重复的 actual 或 context）
    actual_trace_ids = [r.get("actual") for r in results.values() if r.get("actual")]
    context_trace_ids = [r.get("context") for r in results.values() if r.get("context")]
    
    # 统计重复的 trace_id
    actual_duplicates = defaultdict(list)
    context_duplicates = defaultdict(list)
    
    for thread_id, result in results.items():
        actual = result.get("actual")
        context = result.get("context")
        if actual:
            actual_duplicates[actual].append(thread_id)
        if context:
            context_duplicates[context].append(thread_id)
    
    # 检查是否有串用（同一个 trace_id 被多个线程使用）
    actual_collisions = {k: v for k, v in actual_duplicates.items() if len(v) > 1}
    context_collisions = {k: v for k, v in context_duplicates.items() if len(v) > 1}
    
    if actual_collisions:
        print(f"\n⚠️  发现 traceId 串用 (actual):")
        for trace_id, thread_ids in list(actual_collisions.items())[:5]:
            print(f"  trace_id={trace_id} 被线程 {thread_ids} 使用")
    
    if context_collisions:
        print(f"\n⚠️  发现 traceId 串用 (context):")
        for trace_id, thread_ids in list(context_collisions.items())[:5]:
            print(f"  trace_id={trace_id} 被线程 {thread_ids} 使用")
    
    # 判断测试是否通过
    test_passed = (
        success_count == concurrent_count and
        len(actual_collisions) == 0 and
        len(context_collisions) == 0
    )
    
    if test_passed:
        test_result.add_pass(
            f"多线程并发测试 (并发数: {concurrent_count})",
            f"所有 {concurrent_count} 个线程的 traceId 都正确隔离"
        )
    else:
        test_result.add_fail(
            f"多线程并发测试 (并发数: {concurrent_count})",
            f"成功 {success_count}/{concurrent_count}, "
            f"actual串用: {len(actual_collisions)}, context串用: {len(context_collisions)}",
            {
                "success_count": success_count,
                "total_count": concurrent_count,
                "actual_collisions": dict(list(actual_collisions.items())[:5]),
                "context_collisions": dict(list(context_collisions.items())[:5]),
                "failed_cases": failed_cases[:5]
            }
        )
    
    return test_passed


async def test_async_trace_id_isolation(concurrent_count: int = 50) -> bool:
    """
    测试多协程并发场景下 traceId 隔离性
    
    Args:
        concurrent_count: 并发协程数量
        
    Returns:
        bool: 测试是否通过
    """
    print(f"\n{'='*80}")
    print(f"测试2: 多协程并发测试 (并发数: {concurrent_count})")
    print(f"{'='*80}")
    
    # 生成测试方案简写和时间戳
    test_short_name = "AC"  # Async Coroutine
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    test_name_prefix = f"{test_short_name}{timestamp}"
    
    # 使用字典存储结果（在异步环境中，每个协程有独立的上下文）
    results: Dict[int, Dict] = {}
    
    async def worker(coroutine_id: int, trace_id: str):
        """工作协程函数"""
        try:
            # 调用 set_langfuse_trace_context，使用格式化的 name
            actual_trace_id = set_langfuse_trace_context(
                name=f"{test_name_prefix}_c{coroutine_id:03d}",
                user_id=f"user_{coroutine_id:03d}",
                session_id=f"session_{coroutine_id:03d}",
                trace_id=trace_id,
                metadata={"coroutine_id": coroutine_id, "test_type": "async", "test_name": test_name_prefix}
            )
            
            # 获取 ContextVar 中的值
            context_trace_id = get_current_trace_id()
            
            # 记录结果
            results[coroutine_id] = {
                "expected": trace_id,
                "actual": actual_trace_id,
                "context": context_trace_id,
                "match": actual_trace_id == trace_id and context_trace_id == trace_id,
                "coroutine_id": coroutine_id
            }
        except Exception as e:
            results[coroutine_id] = {
                "expected": trace_id,
                "actual": None,
                "context": None,
                "match": False,
                "error": str(e),
                "coroutine_id": coroutine_id
            }
    
    # 创建多个协程并发执行
    tasks = []
    start_time = time.time()
    
    # 预生成所有符合格式要求的 traceId（32位十六进制字符）
    trace_ids = [secrets.token_hex(16) for _ in range(concurrent_count)]
    
    for i in range(concurrent_count):
        trace_id = trace_ids[i]
        tasks.append(worker(i, trace_id))
    
    # 并发执行所有协程
    await asyncio.gather(*tasks)
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    # 验证结果
    success_count = sum(1 for r in results.values() if r.get("match", False))
    fail_count = concurrent_count - success_count
    
    print(f"\n执行时间: {elapsed_time:.2f} 秒")
    print(f"成功: {success_count}/{concurrent_count}")
    print(f"失败: {fail_count}/{concurrent_count}")
    
    # 检查是否有失败的案例
    failed_cases = []
    for coroutine_id, result in results.items():
        if not result.get("match", False):
            failed_cases.append({
                "coroutine_id": coroutine_id,
                "expected": result.get("expected"),
                "actual": result.get("actual"),
                "context": result.get("context"),
                "error": result.get("error")
            })
    
    if failed_cases:
        print(f"\n失败的案例 (前10个):")
        for case in failed_cases[:10]:
            print(f"  协程 {case['coroutine_id']}: 期望={case['expected']}, "
                  f"实际={case['actual']}, 上下文={case['context']}")
            if case.get('error'):
                print(f"    错误: {case['error']}")
    
    # 检查是否有 traceId 串用
    actual_duplicates = defaultdict(list)
    context_duplicates = defaultdict(list)
    
    for coroutine_id, result in results.items():
        actual = result.get("actual")
        context = result.get("context")
        if actual:
            actual_duplicates[actual].append(coroutine_id)
        if context:
            context_duplicates[context].append(coroutine_id)
    
    actual_collisions = {k: v for k, v in actual_duplicates.items() if len(v) > 1}
    context_collisions = {k: v for k, v in context_duplicates.items() if len(v) > 1}
    
    if actual_collisions:
        print(f"\n⚠️  发现 traceId 串用 (actual):")
        for trace_id, coroutine_ids in list(actual_collisions.items())[:5]:
            print(f"  trace_id={trace_id} 被协程 {coroutine_ids} 使用")
    
    if context_collisions:
        print(f"\n⚠️  发现 traceId 串用 (context):")
        for trace_id, coroutine_ids in list(context_collisions.items())[:5]:
            print(f"  trace_id={trace_id} 被协程 {coroutine_ids} 使用")
    
    # 判断测试是否通过
    test_passed = (
        success_count == concurrent_count and
        len(actual_collisions) == 0 and
        len(context_collisions) == 0
    )
    
    if test_passed:
        test_result.add_pass(
            f"多协程并发测试 (并发数: {concurrent_count})",
            f"所有 {concurrent_count} 个协程的 traceId 都正确隔离"
        )
    else:
        test_result.add_fail(
            f"多协程并发测试 (并发数: {concurrent_count})",
            f"成功 {success_count}/{concurrent_count}, "
            f"actual串用: {len(actual_collisions)}, context串用: {len(context_collisions)}",
            {
                "success_count": success_count,
                "total_count": concurrent_count,
                "actual_collisions": dict(list(actual_collisions.items())[:5]),
                "context_collisions": dict(list(context_collisions.items())[:5]),
                "failed_cases": failed_cases[:5]
            }
        )
    
    return test_passed


async def test_mixed_concurrency(thread_count: int = 25, coroutine_count: int = 25) -> bool:
    """
    测试混合并发场景（线程+协程）
    
    Args:
        thread_count: 线程数量
        coroutine_count: 协程数量
        
    Returns:
        bool: 测试是否通过
    """
    print(f"\n{'='*80}")
    print(f"测试3: 混合并发测试 (线程: {thread_count}, 协程: {coroutine_count})")
    print(f"{'='*80}")
    
    # 生成测试方案简写和时间戳
    test_short_name = "MC"  # Mixed Concurrency
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    test_name_prefix = f"{test_short_name}{timestamp}"
    
    # 线程结果
    thread_results: Dict[int, Dict] = {}
    thread_results_lock = threading.Lock()
    
    # 协程结果
    coroutine_results: Dict[int, Dict] = {}
    
    def thread_worker(thread_id: int, trace_id: str):
        """线程工作函数"""
        try:
            actual_trace_id = set_langfuse_trace_context(
                name=f"{test_name_prefix}_t{thread_id:03d}",
                user_id=f"user_thread_{thread_id:03d}",
                session_id=f"session_thread_{thread_id:03d}",
                trace_id=trace_id,
                metadata={"thread_id": thread_id, "test_type": "thread", "test_name": test_name_prefix}
            )
            context_trace_id = get_current_trace_id()
            
            with thread_results_lock:
                thread_results[thread_id] = {
                    "expected": trace_id,
                    "actual": actual_trace_id,
                    "context": context_trace_id,
                    "match": actual_trace_id == trace_id and context_trace_id == trace_id,
                    "type": "thread"
                }
        except Exception as e:
            with thread_results_lock:
                thread_results[thread_id] = {
                    "expected": trace_id,
                    "actual": None,
                    "context": None,
                    "match": False,
                    "error": str(e),
                    "type": "thread"
                }
    
    async def coroutine_worker(coroutine_id: int, trace_id: str):
        """协程工作函数"""
        try:
            actual_trace_id = set_langfuse_trace_context(
                name=f"{test_name_prefix}_c{coroutine_id:03d}",
                user_id=f"user_coro_{coroutine_id:03d}",
                session_id=f"session_coro_{coroutine_id:03d}",
                trace_id=trace_id,
                metadata={"coroutine_id": coroutine_id, "test_type": "coroutine", "test_name": test_name_prefix}
            )
            context_trace_id = get_current_trace_id()
            
            coroutine_results[coroutine_id] = {
                "expected": trace_id,
                "actual": actual_trace_id,
                "context": context_trace_id,
                "match": actual_trace_id == trace_id and context_trace_id == trace_id,
                "type": "coroutine"
            }
        except Exception as e:
            coroutine_results[coroutine_id] = {
                "expected": trace_id,
                "actual": None,
                "context": None,
                "match": False,
                "error": str(e),
                "type": "coroutine"
            }
    
    # 预生成所有符合格式要求的 traceId（32位十六进制字符）
    thread_trace_ids = [secrets.token_hex(16) for _ in range(thread_count)]
    coro_trace_ids = [secrets.token_hex(16) for _ in range(coroutine_count)]
    
    # 启动线程
    threads = []
    for i in range(thread_count):
        trace_id = thread_trace_ids[i]
        t = threading.Thread(target=thread_worker, args=(i, trace_id))
        threads.append(t)
        t.start()
    
    # 启动协程
    coroutines = []
    for i in range(coroutine_count):
        trace_id = coro_trace_ids[i]
        coroutines.append(coroutine_worker(i, trace_id))
    
    # 等待所有任务完成
    start_time = time.time()
    await asyncio.gather(*coroutines)
    for t in threads:
        t.join()
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    # 合并结果
    all_results = {**thread_results, **{f"coro_{k}": v for k, v in coroutine_results.items()}}
    
    # 验证结果
    success_count = sum(1 for r in all_results.values() if r.get("match", False))
    total_count = thread_count + coroutine_count
    fail_count = total_count - success_count
    
    print(f"\n执行时间: {elapsed_time:.2f} 秒")
    print(f"成功: {success_count}/{total_count}")
    print(f"失败: {fail_count}/{total_count}")
    
    # 检查串用
    actual_duplicates = defaultdict(list)
    context_duplicates = defaultdict(list)
    
    for key, result in all_results.items():
        actual = result.get("actual")
        context = result.get("context")
        if actual:
            actual_duplicates[actual].append(key)
        if context:
            context_duplicates[context].append(key)
    
    actual_collisions = {k: v for k, v in actual_duplicates.items() if len(v) > 1}
    context_collisions = {k: v for k, v in context_duplicates.items() if len(v) > 1}
    
    if actual_collisions:
        print(f"\n⚠️  发现 traceId 串用 (actual): {len(actual_collisions)} 个")
    if context_collisions:
        print(f"\n⚠️  发现 traceId 串用 (context): {len(context_collisions)} 个")
    
    test_passed = (
        success_count == total_count and
        len(actual_collisions) == 0 and
        len(context_collisions) == 0
    )
    
    if test_passed:
        test_result.add_pass(
            f"混合并发测试 (线程: {thread_count}, 协程: {coroutine_count})",
            f"所有 {total_count} 个任务的 traceId 都正确隔离"
        )
    else:
        test_result.add_fail(
            f"混合并发测试 (线程: {thread_count}, 协程: {coroutine_count})",
            f"成功 {success_count}/{total_count}, "
            f"actual串用: {len(actual_collisions)}, context串用: {len(context_collisions)}"
        )
    
    return test_passed


def main():
    """主测试函数"""
    print("="*80)
    print("TraceId 并发测试")
    print("="*80)
    print("\n测试目标: 验证在多线程和多协程并发场景下，traceId 是否会出现串用问题")
    print("\n注意: 此测试需要 Langfuse 服务可用，如果不可用将跳过相关功能")
    
    # 检查 Langfuse 是否可用
    if not is_langfuse_available():
        print("\n⚠️  警告: Langfuse 不可用，测试将只验证 ContextVar 隔离性")
        print("   要启用完整测试，请配置 Langfuse 连接信息")
    else:
        print("\n✅ Langfuse 可用，将进行完整测试")
        client = get_langfuse_client()
        if client:
            print(f"   Langfuse 客户端已初始化")
    
    # 测试1: 多线程并发
    try:
        test_multithread_trace_id_isolation(concurrent_count=50)
    except Exception as e:
        test_result.add_fail("多线程并发测试", f"测试执行失败: {e}")
        print(f"\n❌ 多线程测试执行失败: {e}")
    
    # # 测试2: 多协程并发
    # try:
    #     asyncio.run(test_async_trace_id_isolation(concurrent_count=50))
    # except Exception as e:
    #     test_result.add_fail("多协程并发测试", f"测试执行失败: {e}")
    #     print(f"\n❌ 多协程测试执行失败: {e}")
    
    # # 测试3: 混合并发
    # try:
    #     asyncio.run(test_mixed_concurrency(thread_count=25, coroutine_count=25))
    # except Exception as e:
    #     test_result.add_fail("混合并发测试", f"测试执行失败: {e}")
    #     print(f"\n❌ 混合并发测试执行失败: {e}")
    
    # 打印测试总结
    all_passed = test_result.summary()
    
    # 返回退出码
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

