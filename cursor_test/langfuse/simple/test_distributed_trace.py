"""
Langfuse 分布式追踪示例

演示如何在两个服务器之间实现分布式追踪：
- 服务器A：主流程服务器
- 服务器B：子流程服务器

服务器B的执行记录会作为服务器A节点A的子节点。

运行方式：
==========
# 直接运行测试文件
python cursor_test/langfuse/simple/test_distributed_trace.py
"""
import os
import sys
import logging
import secrets
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# 尝试导入 langfuse
try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    print("⚠️  警告: langfuse 模块未安装，请先安装: pip install langfuse")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def find_project_root() -> Path:
    """查找项目根目录"""
    current = Path(__file__).resolve()
    for parent in current.parents:
        env_file = parent / ".env"
        if env_file.exists():
            return parent
    return current.parent.parent.parent.parent


def load_env_config() -> Dict[str, str]:
    """加载环境配置"""
    project_root = find_project_root()
    env_file = project_root / ".env"
    
    config = {}
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False)
            config = {
                "LANGFUSE_ENABLED": os.getenv("LANGFUSE_ENABLED", "false"),
                "LANGFUSE_PUBLIC_KEY": os.getenv("LANGFUSE_PUBLIC_KEY"),
                "LANGFUSE_SECRET_KEY": os.getenv("LANGFUSE_SECRET_KEY"),
                "LANGFUSE_HOST": os.getenv("LANGFUSE_HOST"),
            }
        except Exception as e:
            logger.warning(f"加载 .env 文件失败: {e}")
    
    return config


def create_langfuse_client() -> Optional["Langfuse"]:
    """创建 Langfuse 客户端"""
    if not LANGFUSE_AVAILABLE:
        return None
    
    config = load_env_config()
    
    langfuse_enabled = config.get("LANGFUSE_ENABLED", "false").lower() == "true"
    public_key = config.get("LANGFUSE_PUBLIC_KEY")
    secret_key = config.get("LANGFUSE_SECRET_KEY")
    host = config.get("LANGFUSE_HOST")
    
    if not langfuse_enabled or not public_key or not secret_key:
        return None
    
    try:
        kwargs = {
            "public_key": public_key,
            "secret_key": secret_key,
        }
        if host:
            kwargs["host"] = host
        
        return Langfuse(**kwargs)
    except Exception as e:
        logger.error(f"创建 Langfuse 客户端失败: {e}")
        return None


def normalize_trace_id(trace_id: str) -> str:
    """规范化 trace_id"""
    return trace_id.replace("-", "").lower()


# ==================== 服务器A：主流程服务器 ====================

def simulate_server_a_node_a(client: "Langfuse", trace_id: str) -> Dict[str, Any]:
    """
    模拟服务器A的节点A执行
    
    节点A会调用服务器B的接口
    """
    print("\n[服务器A] 节点A 开始执行...")
    
    # 在 Trace 上下文中创建节点A
    with client.start_as_current_span(
        name="节点A",
        input={"step": "A", "server": "server-a"},
        metadata={"node_type": "主节点", "has_children": True}
    ) as span_a:
        # 获取当前追踪信息
        current_trace_id = client.get_current_trace_id()
        current_span_id = span_a.id  # 获取当前 span 的 ID
        
        print(f"  [服务器A] 节点A: trace_id={current_trace_id}, span_id={current_span_id}")
        
        # 模拟调用服务器B的接口
        print("  [服务器A] 准备调用服务器B...")
        
        # 传递追踪信息给服务器B
        result_b = simulate_server_b_call(
            client=client,
            data={"task": "process data"},
            trace_id=current_trace_id,
            parent_span_id=current_span_id  # 关键：传递父 span ID
        )
        
        print(f"  [服务器A] 收到服务器B的响应: {result_b}")
        
        # 更新节点A的输出
        span_a.update(output={"result": result_b})
        
        print("[服务器A] 节点A 执行完成")
        
        return result_b


def simulate_server_a_node_b(client: "Langfuse") -> Dict[str, Any]:
    """模拟服务器A的节点B执行"""
    print("\n[服务器A] 节点B 开始执行...")
    
    with client.start_as_current_span(
        name="节点B",
        input={"step": "B", "server": "server-a"},
        metadata={"node_type": "独立节点"}
    ):
        time.sleep(0.1)
        result = {"status": "完成", "data": "节点B处理完成"}
        print("[服务器A] 节点B 执行完成")
        return result


# ==================== 服务器B：子流程服务器 ====================

def simulate_server_b_call(
    client: "Langfuse",
    data: Dict[str, Any],
    trace_id: str,
    parent_span_id: str
) -> Dict[str, Any]:
    """
    模拟服务器B接收请求并处理
    
    这个函数模拟了服务器B的接口处理逻辑
    在实际场景中，这应该是一个独立的服务
    """
    print("\n  [服务器B] 收到请求...")
    print(f"  [服务器B] trace_id={trace_id}, parent_span_id={parent_span_id}")
    
    # 构建 trace_context，关联到服务器A的追踪
    trace_context = {
        "trace_id": normalize_trace_id(trace_id),
        "parent_span_id": parent_span_id  # 关键：指定父 Span ID
    }
    
    # 使用 trace_context 创建 Span（会自动关联到服务器A的 Trace）
    with client.start_as_current_span(
        name="节点A-1",
        trace_context=trace_context,  # 关键：使用 trace_context
        input={
            "received_data": data,
            "server": "server-b"
        },
        metadata={
            "server": "server-b",
            "parent_server": "server-a",
            "node_type": "子节点"
        }
    ) as span_b:
        print("  [服务器B] 开始处理...")
        
        # 执行服务器B的业务逻辑
        time.sleep(0.15)
        
        # 可以创建子 Span（如果需要）
        with client.start_as_current_span(
            name="节点A-1-子任务",
            input={"sub_task": "处理子任务"},
            metadata={"task_type": "sub_task"}
        ):
            time.sleep(0.05)
            sub_result = {"sub_task_status": "完成"}
        
        # 处理结果
        processed_data = {
            "original": data,
            "processed": "服务器B处理后的数据",
            "timestamp": datetime.now().isoformat(),
            "sub_result": sub_result
        }
        
        # 更新 Span 输出
        span_b.update(output=processed_data)
        
        print("  [服务器B] 处理完成")
        
        return processed_data


# ==================== 主流程 ====================

def simulate_distributed_trace(
    client: "Langfuse",
    trace_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Optional[str]:
    """
    模拟完整的分布式追踪流程
    
    流程：
    Trace（开始）
      └─ 节点A（服务器A）
          └─ 节点A-1（服务器B）  ← 跨服务器关联
      └─ 节点B（服务器A）
    Trace（结束）
    """
    # 规范化 trace_id
    normalized_trace_id = None
    if trace_id:
        normalized_trace_id = normalize_trace_id(trace_id)
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    trace_name = f"分布式追踪测试_{timestamp}"
    
    # 构建 Trace 参数
    trace_params = {
        "name": trace_name,
        "input": {
            "flow_type": "分布式追踪",
            "description": "演示跨服务器的追踪关联"
        },
        "metadata": {
            "test_type": "distributed_trace",
            "timestamp": timestamp
        }
    }
    
    if normalized_trace_id:
        trace_params["trace_context"] = {"trace_id": normalized_trace_id}
    
    try:
        print("\n" + "="*80)
        print("开始执行分布式追踪流程")
        print("="*80)
        print(f"\n流程结构：")
        print(f"Trace: {trace_name}")
        print(f"  └─ 节点A (服务器A)")
        print(f"      └─ 节点A-1 (服务器B)  ← 跨服务器关联")
        print(f"  └─ 节点B (服务器A)")
        print("\n" + "-"*80)
        
        # 创建 Trace
        with client.start_as_current_span(**trace_params):
            # 更新 Trace 元数据
            client.update_current_trace(
                name=trace_name,
                user_id=user_id,
                session_id=session_id,
                metadata={
                    "test_type": "distributed_trace",
                    "description": "跨服务器追踪演示"
                }
            )
            
            print("\n[开始节点] Trace 已创建")
            
            # ========== 执行节点 A（会调用服务器B）==========
            print("\n[服务器A] 开始执行节点A...")
            result_a = simulate_server_a_node_a(client, normalized_trace_id or client.get_current_trace_id())
            print(f"[服务器A] 节点A执行完成")
            
            # ========== 执行节点 B ==========
            print("\n[服务器A] 开始执行节点B...")
            result_b = simulate_server_a_node_b(client)
            print(f"[服务器A] 节点B执行完成")
            
            # ========== 流程结束 ==========
            print("\n[结束节点] 流程执行完成")
            print("-"*80)
            
            # 获取实际的 trace_id
            actual_trace_id = normalized_trace_id or client.get_current_trace_id()
            
            logger.info(
                f"✅ 分布式追踪流程完成: trace_id={actual_trace_id}"
            )
            
            # 刷新客户端
            client.flush()
            
            print(f"\n✅ 分布式追踪执行完成！Trace ID: {actual_trace_id}")
            print(f"\n你可以在 Langfuse 控制台中查看这个 Trace 的层级结构：")
            print(f"   - Trace: {trace_name}")
            print(f"     └─ Span: 节点A (服务器A)")
            print(f"         └─ Span: 节点A-1 (服务器B)  ← 跨服务器关联")
            print(f"             └─ Span: 节点A-1-子任务 (服务器B)")
            print(f"     └─ Span: 节点B (服务器A)")
            
            return actual_trace_id
            
    except Exception as e:
        logger.error(f"❌ 分布式追踪流程失败: {e}", exc_info=True)
        return None


def main():
    """主测试函数"""
    print("="*80)
    print("Langfuse 分布式追踪示例")
    print("="*80)
    print("\n演示目标: 跨服务器的追踪关联")
    print("\n场景：")
    print("  - 服务器A：主流程服务器")
    print("  - 服务器B：子流程服务器")
    print("  - 服务器B的执行记录作为服务器A节点A的子节点")
    
    if not LANGFUSE_AVAILABLE:
        print("\n❌ 错误: langfuse 模块未安装")
        print("   请先安装: pip install langfuse")
        return 1
    
    # 创建 Langfuse 客户端
    print("\n步骤 1: 创建 Langfuse 客户端...")
    client = create_langfuse_client()
    
    if not client:
        print("\n❌ 错误: Langfuse 客户端创建失败")
        print("   请检查 .env 文件中的配置")
        return 1
    
    # 生成 Trace ID
    print("\n步骤 2: 生成 Trace ID...")
    generated_trace_id = secrets.token_hex(16)
    print(f"   生成的 Trace ID: {generated_trace_id}")
    
    # 执行分布式追踪
    print("\n步骤 3: 执行分布式追踪流程...")
    trace_id = simulate_distributed_trace(
        client=client,
        trace_id=generated_trace_id,
        user_id="test_user_001",
        session_id="test_session_001"
    )
    
    if trace_id:
        print(f"\n等待数据发送到 Langfuse 服务器...")
        time.sleep(2)
        
        try:
            client.flush()
            print("✅ 数据已刷新到服务器")
        except Exception as e:
            print(f"⚠️  刷新数据时出错: {e}")
        
        print(f"\n你可以在 Langfuse 控制台中查看完整的层级结构")
        return 0
    else:
        print("\n❌ 测试失败: 分布式追踪流程失败")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

