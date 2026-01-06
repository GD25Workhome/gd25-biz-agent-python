"""
Langfuse 分布式追踪测试：已完成的 Span 下添加子 Span

测试场景：
- 之前的代码已经执行完成（span 已经结束）
- 使用相同的 trace_id 和 parent_span_id 再次创建 span
- 验证是否可以在已完成的 span 下添加子 span

运行方式：
==========
# 直接运行测试文件
python cursor_test/langfuse/simple/test_distributed_trace_A2.py

# 或者先运行 test_distributed_trace.py 获取 trace_id 和 parent_span_id
# 然后修改下面的 TRACE_ID 和 PARENT_SPAN_ID 后运行此文件
"""
import os
import sys
import logging
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

# ==================== 配置：从终端输出中获取或手动设置 ====================
# 方式1：从命令行参数传入（推荐）
#   python test_distributed_trace_A2.py --trace-id <trace_id> --parent-span-id <parent_span_id>
# 方式2：手动设置（从 Langfuse 控制台或之前的日志中获取）
# 方式3：从之前的执行中获取 trace_id 和 parent_span_id

# 默认值（如果未通过命令行参数传入，则使用这些值）
TRACE_ID = "044002b6ad0f962e132ae996f8f98c84"  # 从终端输出中获取
PARENT_SPAN_ID = "5c9c03fc7438ec33"  # 从终端输出中获取，这是节点A-1的 span_id

# 注意：如果 parent_span_id 是节点A-1的 ID，那么新创建的 span 会成为节点A-1的子节点
# 如果 parent_span_id 是节点A的 ID，那么新创建的 span 会成为节点A的子节点（与节点A-1同级）


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
    """规范化 trace_id（移除连字符，转小写）"""
    return trace_id.replace("-", "").lower()


def add_child_span_to_completed_parent(
    client: "Langfuse",
    trace_id: str,
    parent_span_id: str,
    child_name: str = "节点A-3"
) -> Optional[str]:
    """
    在已完成的 Span 下添加子 Span
    
    测试场景：
    - 之前的代码已经执行完成（span 已经结束）
    - 使用相同的 trace_id 和 parent_span_id 再次创建 span
    - 验证是否可以在已完成的 span 下添加子 span
    
    Args:
        client: Langfuse 客户端
        trace_id: Trace ID
        parent_span_id: 父 Span ID（已完成的 span）
        child_name: 子 Span 的名称
        
    Returns:
        新创建的 Span ID，如果失败则返回 None
    """
    print("\n" + "="*80)
    print("测试：在已完成的 Span 下添加子 Span")
    print("="*80)
    print(f"\n参数：")
    print(f"  trace_id: {trace_id}")
    print(f"  parent_span_id: {parent_span_id}")
    print(f"  child_name: {child_name}")
    print("\n" + "-"*80)
    
    # 规范化 trace_id
    normalized_trace_id = normalize_trace_id(trace_id)
    
    # 构建 trace_context
    trace_context = {
        "trace_id": normalized_trace_id,
        "parent_span_id": parent_span_id  # 指定父 Span ID（已完成的 span）
    }
    
    try:
        print(f"\n[步骤1] 使用 trace_context 创建子 Span...")
        print(f"  trace_context = {trace_context}")
        
        # 使用 trace_context 创建 Span
        # 注意：即使父 Span 已经完成，Langfuse 也应该能够关联
        with client.start_as_current_span(
            name=child_name,
            trace_context=trace_context,  # 关键：使用 trace_context 指定父 Span
            input={
                "test_type": "retroactive_child",
                "description": "这是在已完成的 Span 下添加的子 Span",
                "parent_span_id": parent_span_id,
                "created_at": datetime.now().isoformat()
            },
            metadata={
                "test_scenario": "completed_parent_add_child",
                "parent_span_id": parent_span_id,
                "note": "这个 Span 是在父 Span 完成后创建的"
            }
        ) as child_span:
            print(f"  ✅ 子 Span 创建成功")
            print(f"  Span ID: {child_span.id}")
            print(f"  Span Name: {child_name}")
            
            # 执行一些操作
            print(f"\n[步骤2] 执行子 Span 的业务逻辑...")
            time.sleep(0.1)
            
            # 可以创建更深层的子 Span
            # with client.start_as_current_span(
            #     name="节点A-2-子任务-深层任务",
            #     input={"deep_task": "深层任务处理"},
            #     metadata={"depth": 2}
            # ):
            #     print(f"    └─ 创建更深层的子 Span")
            #     time.sleep(0.05)
            
            # 更新子 Span 的输出
            result = {
                "status": "完成",
                "message": "这是在已完成的 Span 下成功添加的子 Span",
                "parent_span_id": parent_span_id,
                "timestamp": datetime.now().isoformat()
            }
            
            child_span.update(output=result)
            print(f"\n[步骤3] 子 Span 执行完成")
            print(f"  输出: {result}")
            
            child_span_id = child_span.id
            
        print("\n" + "-"*80)
        print(f"✅ 测试完成！")
        print(f"\n预期结果：")
        print(f"  在 Langfuse 控制台中，你应该能看到：")
        print(f"  - Trace: {normalized_trace_id}")
        print(f"    └─ ... (之前的层级结构)")
        print(f"      └─ Span: {child_name} (parent_span_id={parent_span_id})")
        print(f"          └─ Span: 节点A-2-子任务-深层任务")
        print(f"\n  注意：这个 Span 是在父 Span 完成后创建的")
        
        return child_span_id
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        print(f"\n❌ 错误: {e}")
        print(f"\n可能的原因：")
        print(f"  1. trace_id 或 parent_span_id 不正确")
        print(f"  2. Langfuse 不支持在已完成的 Span 下添加子 Span")
        print(f"  3. 网络或配置问题")
        return None


def main():
    """主测试函数"""
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="测试在已完成的 Span 下添加子 Span"
    )
    parser.add_argument(
        "--trace-id",
        type=str,
        default=TRACE_ID,
        help="Trace ID（从之前的执行中获取）"
    )
    parser.add_argument(
        "--parent-span-id",
        type=str,
        default=PARENT_SPAN_ID,
        help="父 Span ID（从之前的执行中获取）"
    )
    parser.add_argument(
        "--child-name",
        type=str,
        default="节点A-4",
        help="子 Span 的名称"
    )
    
    args = parser.parse_args()
    
    trace_id = args.trace_id
    parent_span_id = args.parent_span_id
    child_name = args.child_name
    
    print("="*80)
    print("Langfuse 测试：在已完成的 Span 下添加子 Span")
    print("="*80)
    print("\n测试场景：")
    print("  - 之前的代码已经执行完成（span 已经结束）")
    print("  - 使用相同的 trace_id 和 parent_span_id 再次创建 span")
    print("  - 验证是否可以在已完成的 span 下添加子 span")
    
    if not LANGFUSE_AVAILABLE:
        print("\n❌ 错误: langfuse 模块未安装")
        print("   请先安装: pip install langfuse")
        return 1
    
    # 检查配置
    if not trace_id or not parent_span_id:
        print("\n⚠️  警告: 未设置 trace_id 或 parent_span_id")
        print("   使用方式：")
        print("   1. 通过命令行参数传入：")
        print("      python test_distributed_trace_A2.py --trace-id <trace_id> --parent-span-id <parent_span_id>")
        print("   2. 修改文件中的 TRACE_ID 和 PARENT_SPAN_ID 常量")
        print("   3. 从 Langfuse 控制台中获取这些值")
        print(f"\n   当前配置：")
        print(f"   trace_id = {trace_id}")
        print(f"   parent_span_id = {parent_span_id}")
        return 1
    
    # 创建 Langfuse 客户端
    print("\n步骤 1: 创建 Langfuse 客户端...")
    client = create_langfuse_client()
    
    if not client:
        print("\n❌ 错误: Langfuse 客户端创建失败")
        print("   请检查 .env 文件中的配置")
        return 1
    
    # 执行测试
    print("\n步骤 2: 执行测试...")
    child_span_id = add_child_span_to_completed_parent(
        client=client,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        child_name=child_name
    )
    
    if child_span_id:
        print(f"\n等待数据发送到 Langfuse 服务器...")
        time.sleep(2)
        
        try:
            client.flush()
            print("✅ 数据已刷新到服务器")
        except Exception as e:
            print(f"⚠️  刷新数据时出错: {e}")
        
        print(f"\n你可以在 Langfuse 控制台中查看结果")
        print(f"  - 查找 Trace ID: {normalize_trace_id(trace_id)}")
        print(f"  - 查找父 Span ID: {parent_span_id}")
        print(f"  - 查看新添加的子 Span: {child_name}")
        return 0
    else:
        print("\n❌ 测试失败")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

