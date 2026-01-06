"""
Langfuse Trace 和 Span 层级结构演示

演示如何创建嵌套的 Span 结构：
- Trace（最外层，根节点）
  - Span A（节点A）
    - Span A-1（子节点A-1）
    - Span A-2（子节点A-2）
  - Span B（节点B）

运行方式：
==========
# 直接运行测试文件
python cursor_test/langfuse/simple/test_flow_trace.py

# 或者在项目根目录运行
python -m cursor_test.langfuse.simple.test_flow_trace
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

# 尝试导入 dotenv
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    print("⚠️  警告: python-dotenv 模块未安装，将使用手动解析方式")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def find_project_root() -> Path:
    """查找项目根目录（包含 .env 文件的目录）"""
    current = Path(__file__).resolve()
    for parent in current.parents:
        env_file = parent / ".env"
        if env_file.exists():
            return parent
    return current.parent.parent.parent.parent


def load_env_file(env_path: Path) -> Dict[str, str]:
    """加载 .env 文件"""
    config = {}
    if not env_path.exists():
        logger.warning(f".env 文件不存在: {env_path}")
        return config
    
    try:
        if DOTENV_AVAILABLE:
            load_dotenv(env_path, override=False)
            config = {
                "LANGFUSE_ENABLED": os.getenv("LANGFUSE_ENABLED", "false"),
                "LANGFUSE_PUBLIC_KEY": os.getenv("LANGFUSE_PUBLIC_KEY"),
                "LANGFUSE_SECRET_KEY": os.getenv("LANGFUSE_SECRET_KEY"),
                "LANGFUSE_HOST": os.getenv("LANGFUSE_HOST"),
            }
        else:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        config[key] = value
    except Exception as e:
        logger.warning(f"加载 .env 文件失败: {e}")
    
    return config


def create_langfuse_client() -> Optional["Langfuse"]:
    """从 .env 文件读取配置并创建 Langfuse 客户端"""
    if not LANGFUSE_AVAILABLE:
        logger.error("Langfuse SDK 未安装")
        return None
    
    project_root = find_project_root()
    env_file = project_root / ".env"
    env_config = load_env_file(env_file)
    
    langfuse_enabled = (
        env_config.get("LANGFUSE_ENABLED", os.getenv("LANGFUSE_ENABLED", "false"))
        .lower() == "true"
    )
    public_key = env_config.get(
        "LANGFUSE_PUBLIC_KEY", os.getenv("LANGFUSE_PUBLIC_KEY")
    )
    secret_key = env_config.get(
        "LANGFUSE_SECRET_KEY", os.getenv("LANGFUSE_SECRET_KEY")
    )
    host = env_config.get(
        "LANGFUSE_HOST", os.getenv("LANGFUSE_HOST")
    )
    
    if not langfuse_enabled:
        logger.warning("Langfuse 未启用（LANGFUSE_ENABLED=false）")
        return None
    
    if not public_key or not secret_key:
        logger.error(
            "Langfuse配置不完整：缺少LANGFUSE_PUBLIC_KEY或LANGFUSE_SECRET_KEY"
        )
        return None
    
    try:
        langfuse_kwargs = {
            "public_key": public_key,
            "secret_key": secret_key,
        }
        if host:
            langfuse_kwargs["host"] = host
        
        client = Langfuse(**langfuse_kwargs)
        logger.info(f"✅ Langfuse客户端初始化成功")
        return client
    except Exception as e:
        logger.error(f"❌ Langfuse客户端初始化失败: {e}", exc_info=True)
        return None


def normalize_langfuse_trace_id(trace_id: str) -> str:
    """将 trace_id 转换为 Langfuse 要求的格式（32 个小写十六进制字符）"""
    normalized = trace_id.replace("-", "").lower()
    try:
        int(normalized, 16)
    except ValueError:
        logger.warning(f"trace_id 不是有效的十六进制字符串: {trace_id}")
        return trace_id
    
    if len(normalized) != 32:
        logger.warning(
            f"trace_id 长度不是 32 位: {trace_id} (转换后: {normalized}, 长度: {len(normalized)})"
        )
    
    return normalized


def simulate_node_a_1(client: "Langfuse", input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    模拟节点 A-1 的执行
    
    这是一个子节点，会在节点 A 的上下文中执行
    """
    print("    └─ [节点 A-1] 开始执行...")
    
    # 在节点 A 的上下文中创建子节点 A-1
    with client.start_as_current_span(
        name="节点A-1",
        input={"step": "A-1", "data": input_data.get("data_a1", "默认数据A-1")},
        metadata={"node_type": "子节点", "parent": "节点A"}
    ):
        # 模拟节点 A-1 的处理逻辑
        time.sleep(0.1)  # 模拟处理时间
        
        result_a1 = {
            "status": "完成",
            "processed_data": f"节点A-1处理了: {input_data.get('data_a1', '默认数据A-1')}",
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"    └─ [节点 A-1] 执行完成: {result_a1['processed_data']}")
        
        return result_a1


def simulate_node_a_2(client: "Langfuse", input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    模拟节点 A-2 的执行
    
    这是另一个子节点，也会在节点 A 的上下文中执行
    """
    print("    └─ [节点 A-2] 开始执行...")
    
    # 在节点 A 的上下文中创建子节点 A-2
    with client.start_as_current_span(
        name="节点A-2",
        input={"step": "A-2", "data": input_data.get("data_a2", "默认数据A-2")},
        metadata={"node_type": "子节点", "parent": "节点A"}
    ):
        # 模拟节点 A-2 的处理逻辑
        time.sleep(0.15)  # 模拟处理时间
        
        result_a2 = {
            "status": "完成",
            "processed_data": f"节点A-2处理了: {input_data.get('data_a2', '默认数据A-2')}",
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"    └─ [节点 A-2] 执行完成: {result_a2['processed_data']}")
        
        return result_a2


def simulate_node_a(client: "Langfuse", input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    模拟节点 A 的执行
    
    节点 A 内部会调用两个子节点：A-1 和 A-2
    """
    print("  └─ [节点 A] 开始执行...")
    
    # 在 Trace 的上下文中创建节点 A
    with client.start_as_current_span(
        name="节点A",
        input={"step": "A", "data": input_data.get("data_a", "默认数据A")},
        metadata={"node_type": "父节点", "has_children": True}
    ):
        # 节点 A 的处理逻辑
        print("  └─ [节点 A] 准备执行子节点...")
        
        # 执行子节点 A-1（会自动成为节点 A 的子 span）
        result_a1 = simulate_node_a_1(client, input_data)
        
        # 执行子节点 A-2（会自动成为节点 A 的子 span）
        result_a2 = simulate_node_a_2(client, input_data)
        
        # 汇总节点 A 的结果
        result_a = {
            "status": "完成",
            "node_a_results": {
                "a1": result_a1,
                "a2": result_a2
            },
            "summary": f"节点A完成了两个子节点的处理",
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"  └─ [节点 A] 执行完成: {result_a['summary']}")
        
        return result_a


def simulate_node_b(client: "Langfuse", input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    模拟节点 B 的执行
    
    节点 B 与节点 A 是同级节点，都在 Trace 的上下文中
    """
    print("  └─ [节点 B] 开始执行...")
    
    # 在 Trace 的上下文中创建节点 B（与节点 A 同级）
    with client.start_as_current_span(
        name="节点B",
        input={"step": "B", "data": input_data.get("data_b", "默认数据B")},
        metadata={"node_type": "独立节点", "has_children": False}
    ):
        # 模拟节点 B 的处理逻辑
        time.sleep(0.2)  # 模拟处理时间
        
        result_b = {
            "status": "完成",
            "processed_data": f"节点B处理了: {input_data.get('data_b', '默认数据B')}",
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"  └─ [节点 B] 执行完成: {result_b['processed_data']}")
        
        return result_b


def record_flow_trace(
    client: "Langfuse",
    trace_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Optional[str]:
    """
    记录一个完整的流程 Trace 到 Langfuse
    
    流程结构：
    Trace（开始节点）
      └─ 节点A
          ├─ 节点A-1
          └─ 节点A-2
      └─ 节点B
    Trace（结束节点）
    
    Args:
        client: Langfuse 客户端实例
        trace_id: 自定义Trace ID（可选）
        user_id: 用户ID（可选）
        session_id: 会话ID（可选）
        
    Returns:
        str: Trace ID，如果记录失败则返回None
    """
    # 规范化 trace_id（如果提供）
    normalized_trace_id = None
    if trace_id:
        normalized_trace_id = normalize_langfuse_trace_id(trace_id)
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    trace_name = f"流程测试_{timestamp}"
    
    # 构建 Trace 参数（最外层的 span 就是 trace）
    trace_params = {
        "name": trace_name,
        "input": {
            "flow_type": "演示流程",
            "description": "这是一个演示 Trace 和 Span 层级结构的流程"
        },
        "metadata": {
            "test_type": "flow_trace",
            "timestamp": timestamp,
            "flow_steps": ["开始", "节点A", "节点B", "结束"]
        }
    }
    
    # 如果提供了 trace_id，通过 trace_context 参数传入
    if normalized_trace_id:
        trace_params["trace_context"] = {"trace_id": normalized_trace_id}
    
    try:
        print("\n" + "="*80)
        print("开始执行流程 Trace")
        print("="*80)
        print(f"\n流程结构：")
        print(f"Trace: {trace_name}")
        print(f"  └─ 节点A")
        print(f"      ├─ 节点A-1")
        print(f"      └─ 节点A-2")
        print(f"  └─ 节点B")
        print("\n" + "-"*80)
        
        # 使用 start_as_current_span() 创建 Trace（最外层的 span 就是 trace）
        # 这会创建一个活动的 span 上下文，后续的所有 span 都会自动关联到这个 trace
        with client.start_as_current_span(**trace_params):
            # 在 Trace 上下文中，更新 trace 元数据
            client.update_current_trace(
                name=trace_name,
                user_id=user_id,
                session_id=session_id,
                metadata={
                    "test_type": "flow_trace",
                    "timestamp": timestamp,
                    "description": "演示 Trace 和 Span 层级结构的流程"
                }
            )
            
            print("\n[开始节点] Trace 已创建")
            
            # 准备输入数据
            input_data = {
                "data_a": "节点A的输入数据",
                "data_a1": "节点A-1的输入数据",
                "data_a2": "节点A-2的输入数据",
                "data_b": "节点B的输入数据"
            }
            
            # ========== 执行节点 A ==========
            print("\n[节点 A] 开始执行...")
            result_a = simulate_node_a(client, input_data)
            print(f"[节点 A] 执行完成")
            
            # ========== 执行节点 B ==========
            print("\n[节点 B] 开始执行...")
            result_b = simulate_node_b(client, input_data)
            print(f"[节点 B] 执行完成")
            
            # ========== 流程结束 ==========
            print("\n[结束节点] 流程执行完成")
            print("-"*80)
            
            # 获取实际的 trace_id
            actual_trace_id = normalized_trace_id or client.get_current_trace_id()
            
            # 汇总结果
            final_result = {
                "trace_id": actual_trace_id,
                "status": "完成",
                "results": {
                    "node_a": result_a,
                    "node_b": result_b
                },
                "summary": "所有节点执行完成"
            }
            
            logger.info(
                f"✅ 流程 Trace 记录成功: trace_id={actual_trace_id}, "
                f"user_id={user_id}, session_id={session_id}"
            )
            
            # 刷新客户端，确保数据发送到服务器
            client.flush()
            
            print(f"\n✅ 流程执行完成！Trace ID: {actual_trace_id}")
            print(f"\n你可以在 Langfuse 控制台中查看这个 Trace 的层级结构：")
            print(f"   - Trace: {trace_name}")
            print(f"     └─ Span: 节点A")
            print(f"         ├─ Span: 节点A-1")
            print(f"         └─ Span: 节点A-2")
            print(f"     └─ Span: 节点B")
            
            return actual_trace_id
            
    except Exception as e:
        logger.error(f"❌ 流程 Trace 记录失败: {e}", exc_info=True)
        return None


def main():
    """主测试函数"""
    print("="*80)
    print("Langfuse Trace 和 Span 层级结构演示")
    print("="*80)
    print("\n演示目标: 创建一个包含嵌套 Span 的 Trace")
    print("\n流程结构：")
    print("Trace（开始节点）")
    print("  └─ 节点A")
    print("      ├─ 节点A-1")
    print("      └─ 节点A-2")
    print("  └─ 节点B")
    print("Trace（结束节点）")
    
    # 检查 Langfuse 是否可用
    if not LANGFUSE_AVAILABLE:
        print("\n❌ 错误: langfuse 模块未安装")
        print("   请先安装: pip install langfuse")
        return 1
    
    # 创建 Langfuse 客户端
    print("\n步骤 1: 创建 Langfuse 客户端...")
    client = create_langfuse_client()
    
    if not client:
        print("\n❌ 错误: Langfuse 客户端创建失败")
        print("   请检查 .env 文件中的配置:")
        print("   - LANGFUSE_ENABLED=true")
        print("   - LANGFUSE_PUBLIC_KEY=...")
        print("   - LANGFUSE_SECRET_KEY=...")
        print("   - LANGFUSE_HOST=... (可选)")
        return 1
    
    # 生成 Trace ID
    print("\n步骤 2: 生成 Trace ID...")
    generated_trace_id = secrets.token_hex(16)  # 生成 32 位十六进制字符
    print(f"   生成的 Trace ID: {generated_trace_id}")
    
    # 执行流程 Trace
    print("\n步骤 3: 执行流程 Trace...")
    trace_id = record_flow_trace(
        client=client,
        trace_id=generated_trace_id,
        user_id="test_user_001",
        session_id="test_session_001"
    )
    
    if trace_id:
        print(f"\n等待数据发送到 Langfuse 服务器...")
        # 等待数据发送完成
        time.sleep(2)
        
        # 再次刷新，确保所有数据都已发送
        try:
            client.flush()
            print("✅ 数据已刷新到服务器")
        except Exception as e:
            print(f"⚠️  刷新数据时出错: {e}")
        
        print(f"\n你可以在 Langfuse 控制台中查看这个 Trace 的完整层级结构")
        return 0
    else:
        print("\n❌ 测试失败: 流程 Trace 记录失败")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

