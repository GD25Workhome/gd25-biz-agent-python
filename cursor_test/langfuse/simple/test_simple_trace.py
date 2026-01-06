"""
简单的 Langfuse Trace 记录测试
模拟 client 创建方式，实现单次的 langfuse 日志记录功能

运行方式：
==========
# 直接运行测试文件
python cursor_test/langfuse/simple/test_simple_trace.py

# 或者在项目根目录运行
python -m cursor_test.langfuse.simple.test_simple_trace
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
    """
    查找项目根目录（包含 .env 文件的目录）
    
    Returns:
        Path: 项目根目录路径
    """
    # 当前文件位于: cursor_test/langfuse/simple/test_simple_trace.py
    # 项目根目录应该是: cursor_test/langfuse/simple/../../../
    current = Path(__file__).resolve()
    
    # 先尝试从当前文件位置向上查找
    for parent in current.parents:
        env_file = parent / ".env"
        if env_file.exists():
            return parent
    
    # 如果找不到，返回计算出的项目根目录（向上4级）
    project_root = current.parent.parent.parent.parent
    return project_root


def load_env_file(env_path: Path) -> Dict[str, str]:
    """
    加载 .env 文件
    
    Args:
        env_path: .env 文件路径
        
    Returns:
        Dict[str, str]: 配置字典
    """
    config = {}
    
    if not env_path.exists():
        logger.warning(f".env 文件不存在: {env_path}")
        return config
    
    try:
        if DOTENV_AVAILABLE:
            # 使用 python-dotenv 加载
            load_dotenv(env_path, override=False)
            # 从环境变量读取（dotenv 已经加载到环境变量中）
            config = {
                "LANGFUSE_ENABLED": os.getenv("LANGFUSE_ENABLED", "false"),
                "LANGFUSE_PUBLIC_KEY": os.getenv("LANGFUSE_PUBLIC_KEY"),
                "LANGFUSE_SECRET_KEY": os.getenv("LANGFUSE_SECRET_KEY"),
                "LANGFUSE_HOST": os.getenv("LANGFUSE_HOST"),
            }
        else:
            # 手动解析 .env 文件
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # 跳过空行和注释
                    if not line or line.startswith('#'):
                        continue
                    # 解析 KEY=VALUE 格式
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        # 移除引号
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        config[key] = value
    except Exception as e:
        logger.warning(f"加载 .env 文件失败: {e}")
    
    return config


def create_langfuse_client() -> Optional["Langfuse"]:
    """
    从 .env 文件读取配置并创建 Langfuse 客户端
    
    Returns:
        Langfuse: Langfuse客户端实例，如果配置不完整或初始化失败则返回None
    """
    if not LANGFUSE_AVAILABLE:
        logger.error("Langfuse SDK 未安装")
        return None
    
    # 查找项目根目录
    project_root = find_project_root()
    env_file = project_root / ".env"
    
    # 加载 .env 文件
    env_config = load_env_file(env_file)
    
    # 读取配置（优先使用 .env 文件，如果没有则使用环境变量）
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
    
    # 检查是否启用
    if not langfuse_enabled:
        logger.warning("Langfuse 未启用（LANGFUSE_ENABLED=false）")
        return None
    
    # 检查配置是否完整
    if not public_key or not secret_key:
        logger.error(
            "Langfuse配置不完整：缺少LANGFUSE_PUBLIC_KEY或LANGFUSE_SECRET_KEY，"
            "请检查 .env 文件配置。"
        )
        return None
    
    try:
        # 创建Langfuse客户端
        langfuse_kwargs = {
            "public_key": public_key,
            "secret_key": secret_key,
        }
        if host:
            langfuse_kwargs["host"] = host
        else:
            logger.warning("LANGFUSE_HOST未设置，Langfuse将使用默认host")
        
        client = Langfuse(**langfuse_kwargs)
        
        logger.info(
            f"✅ Langfuse客户端初始化成功: "
            f"host={host or 'default'}, "
            f"public_key_prefix={public_key[:8] if public_key else 'None'}..."
        )
        return client
    
    except Exception as e:
        logger.error(f"❌ Langfuse客户端初始化失败: {e}", exc_info=True)
        return None


def normalize_langfuse_trace_id(trace_id: str) -> str:
    """
    将 trace_id 转换为 Langfuse 要求的格式
    
    Langfuse SDK 要求 trace_id 必须是 32 个小写十六进制字符（不带连字符）。
    如果传入的是 UUID v4 格式（带连字符），需要转换为 32 位十六进制字符串。
    
    Args:
        trace_id: 原始的 trace_id（可能是 UUID v4 格式或其他格式）
        
    Returns:
        符合 Langfuse 要求的 trace_id（32 个小写十六进制字符）
    """
    # 移除连字符并转换为小写
    normalized = trace_id.replace("-", "").lower()
    
    # 验证是否为有效的十六进制字符串
    try:
        int(normalized, 16)
    except ValueError:
        logger.warning(f"trace_id 不是有效的十六进制字符串: {trace_id}")
        # 如果无效，返回原值（让 Langfuse SDK 自己处理）
        return trace_id
    
    # 如果长度不是 32，记录警告但返回转换后的值
    if len(normalized) != 32:
        logger.warning(
            f"trace_id 长度不是 32 位: {trace_id} (转换后: {normalized}, 长度: {len(normalized)})"
        )
    
    return normalized


def record_simple_trace(
    client: "Langfuse",
    name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    记录一个简单的 Trace 到 Langfuse
    
    正确的调用方式：
    1. 使用 start_as_current_span() 创建 trace（最外层的 span 就是 trace）
    2. 通过 trace_context 参数指定 trace_id（如果提供）
    3. 在 span 上下文中使用 update_current_trace() 更新 trace 元数据
    
    注意：
    - update_current_trace() 需要一个活动的 span 上下文才能工作
    - update_current_trace() 不支持 id 参数，需要通过 start_as_current_span() 的 trace_context 参数指定
    
    参考：
    - app/api/routes.py 中使用 set_langfuse_trace_context() 函数
    - domain/router/graph.py 中使用 start_as_current_span() 创建 span
    
    Args:
        client: Langfuse 客户端实例
        name: Trace 名称
        user_id: 用户ID（可选）
        session_id: 会话ID（可选）
        trace_id: 自定义Trace ID（可选，如果不提供则自动生成）
        metadata: 元数据（可选）
        
    Returns:
        str: Trace ID（用于后续关联），如果记录失败则返回None
    """
    # 规范化 trace_id（如果提供）
    normalized_trace_id = None
    if trace_id:
        normalized_trace_id = normalize_langfuse_trace_id(trace_id)
    
    # 构建 span 参数（最外层的 span 就是 trace）
    span_params = {
        "name": name,
        "input": {},  # 可以添加输入数据
        "metadata": metadata or {},
    }
    
    # 如果提供了 trace_id，通过 trace_context 参数传入
    if normalized_trace_id:
        span_params["trace_context"] = {"trace_id": normalized_trace_id}
    
    try:
        # 使用 start_as_current_span() 创建 trace（最外层的 span 就是 trace）
        # 这会创建一个活动的 span 上下文，后续的 update_current_trace() 才能工作
        with client.start_as_current_span(**span_params):
            # 在 span 上下文中，使用 update_current_trace() 更新 trace 元数据
            # 注意：update_current_trace() 不支持 id 参数，trace_id 已经通过 trace_context 传入
            client.update_current_trace(
                name=name+"AA",
                user_id=user_id,
                session_id=session_id,
                metadata=metadata or {},
            )
            
            actual_trace_id = normalized_trace_id or client.get_current_trace_id()
            
            logger.info(
                f"✅ Trace 记录成功: name={name}, trace_id={actual_trace_id}, "
                f"user_id={user_id}, session_id={session_id}"
            )
            
            # 刷新客户端，确保数据发送到服务器
            client.flush()
            
            return actual_trace_id
            
    except Exception as e:
        logger.error(f"❌ Trace 记录失败: {e}", exc_info=True)
        return None


def main():
    """主测试函数"""
    print("="*80)
    print("简单的 Langfuse Trace 记录测试")
    print("="*80)
    print("\n测试目标: 从 .env 读取配置，创建 Langfuse 客户端，并记录一个 Trace")
    
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
    
    # 记录一个简单的 Trace
    print("\n步骤 2: 生成 Trace ID...")
    # 生成 32 位十六进制字符的 trace_id（符合 Langfuse 要求的格式）
    generated_trace_id = secrets.token_hex(16)  # 生成 32 位十六进制字符
    print(f"   生成的 Trace ID: {generated_trace_id}")
    
    print("\n步骤 3: 记录 Trace...")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    trace_id = record_simple_trace(
        client=client,
        name=f"simple_test_{timestamp}",
        user_id="test_user_001",
        session_id="test_session_001",
        trace_id=generated_trace_id,  # 传入生成的 trace_id
        metadata={
            "test_type": "simple_trace",
            "timestamp": timestamp,
            "description": "这是一个简单的 Trace 记录测试"
        }
    )
    
    if trace_id:
        print(f"\n✅ 测试成功！Trace ID: {trace_id}")
        print(f"\n等待数据发送到 Langfuse 服务器...")
        # 等待数据发送完成（Langfuse SDK 是异步发送的）
        time.sleep(2)
        
        # 再次刷新，确保所有数据都已发送
        try:
            client.flush()
            print("✅ 数据已刷新到服务器")
        except Exception as e:
            print(f"⚠️  刷新数据时出错: {e}")
        
        print(f"\n你可以在 Langfuse 控制台中查看这个 Trace:")
        print(f"   - Trace ID: {trace_id}")
        print(f"   - Trace 名称: simple_test_{timestamp}")
        print(f"   - 用户ID: test_user_001")
        print(f"   - 会话ID: test_session_001")
        return 0
    else:
        print("\n❌ 测试失败: Trace 记录失败")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

