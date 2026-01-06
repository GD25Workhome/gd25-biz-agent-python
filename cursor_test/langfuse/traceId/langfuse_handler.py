"""
Langfuse可观测性集成（测试副本）
提供Trace追踪、LLM调用日志记录等功能

此文件是 01_Agent/backend/infrastructure/observability/langfuse_handler.py 的副本
用于测试，不依赖 backend.app.config，而是从项目根目录的 .env 文件读取配置
"""
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from contextvars import ContextVar

# 直接导入，如果模块不存在会直接报错，便于及时发现配置问题
try:
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
except ImportError:
    Langfuse = None
    LangfuseCallbackHandler = None

# 尝试导入 dotenv，如果不存在则使用简单的解析方式
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

logger = logging.getLogger(__name__)

# 全局Langfuse客户端实例
_langfuse_client: Optional["Langfuse"] = None

# Trace上下文变量（用于在异步上下文中传递Trace ID）
_trace_context: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def find_project_root() -> Path:
    """
    查找项目根目录（包含 .env 文件的目录）
    
    从当前文件位置向上查找，直到找到包含 .env 文件的目录
    
    Returns:
        Path: 项目根目录路径
    """
    # 当前文件位于: cursor_test/langfuse/traceId/langfuse_handler.py
    # 项目根目录应该是: cursor_test/langfuse/traceId/../../../
    current = Path(__file__).resolve()
    
    # 先尝试从当前文件位置向上查找
    for parent in current.parents:
        env_file = parent / ".env"
        if env_file.exists():
            return parent
    
    # 如果找不到，返回计算出的项目根目录（向上4级）
    # cursor_test/langfuse/traceId/../../../
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


# 简单的配置类，从项目根目录的 .env 文件读取
class TestSettings:
    """测试用配置类，从项目根目录的 .env 文件读取配置"""
    def __init__(self):
        # 查找项目根目录
        project_root = find_project_root()
        env_file = project_root / ".env"
        
        # 加载 .env 文件
        env_config = load_env_file(env_file)
        
        # 读取配置（优先使用 .env 文件，如果没有则使用环境变量）
        self.LANGFUSE_ENABLED = (
            env_config.get("LANGFUSE_ENABLED", os.getenv("LANGFUSE_ENABLED", "false"))
            .lower() == "true"
        )
        self.LANGFUSE_PUBLIC_KEY = env_config.get(
            "LANGFUSE_PUBLIC_KEY", os.getenv("LANGFUSE_PUBLIC_KEY")
        )
        self.LANGFUSE_SECRET_KEY = env_config.get(
            "LANGFUSE_SECRET_KEY", os.getenv("LANGFUSE_SECRET_KEY")
        )
        self.LANGFUSE_HOST = env_config.get(
            "LANGFUSE_HOST", os.getenv("LANGFUSE_HOST")
        )
        
        logger.debug(
            f"加载配置完成: project_root={project_root}, "
            f"env_file={env_file}, "
            f"LANGFUSE_ENABLED={self.LANGFUSE_ENABLED}"
        )


# 创建全局配置实例
settings = TestSettings()


def set_langfuse_trace_context(
    name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    设置Langfuse Trace上下文
    
    在API路由层调用此函数创建Trace，后续的LLM调用和节点执行会自动关联到此Trace。
    
    Args:
        name: Trace名称
        user_id: 用户ID（可选）
        session_id: 会话ID（可选）
        trace_id: 自定义Trace ID（可选，如果不提供则自动生成）
        metadata: 元数据（可选）
        
    Returns:
        str: Trace ID（用于后续关联）
    """
    # 先检查Langfuse是否可用
    if not is_langfuse_available():
        logger.debug("Langfuse不可用，跳过Trace创建")
        return trace_id
    
    langfuse_client = get_langfuse_client()
    if not langfuse_client:
        logger.warning("Langfuse客户端获取失败，跳过Trace创建")
        return trace_id
    
    try:
        # 如果提供了 trace_id，先转换为 Langfuse 要求的格式
        normalized_trace_id = None
        if trace_id:
            normalized_trace_id = normalize_langfuse_trace_id(trace_id)
        
        # 构建 trace 参数
        trace_params = {
            "name": name,
            "user_id": user_id,
            "session_id": session_id,
            "metadata": metadata or {},
        }
        
        # 使用 update_current_trace() 方法更新当前 trace
        # 注意：Langfuse SDK 的 update_current_trace 可能不支持 id 参数
        # 如果提供了 trace_id，先尝试使用 id 参数，如果失败则回退到不使用 id
        if normalized_trace_id:
            try:
                # 尝试使用 id 参数（使用转换后的 trace_id）
                langfuse_client.update_current_trace(id=normalized_trace_id, **trace_params)
                actual_trace_id = normalized_trace_id
            except (TypeError, AttributeError):
                # 如果 SDK 不支持 id 参数，记录警告但继续执行
                logger.warning(
                    f"Langfuse SDK 可能不支持 id 参数，将使用默认行为。trace_id={normalized_trace_id}"
                )
                langfuse_client.update_current_trace(**trace_params)
                actual_trace_id = normalized_trace_id
        else:
            # 由 Langfuse 生成 trace_id
            langfuse_client.update_current_trace(**trace_params)
            actual_trace_id = trace_id
        
        # 将Trace ID存储到上下文变量中
        if actual_trace_id:
            _trace_context.set(actual_trace_id)
        
        logger.info(
            f"[Langfuse] 设置Trace上下文成功: name={name}, trace_id={actual_trace_id}, "
            f"user_id={user_id}, session_id={session_id}, metadata={metadata}"
        )
        
        return actual_trace_id
    
    except Exception as e:
        # 如果设置失败，记录警告但不影响主流程
        logger.warning(f"[Langfuse] 设置Trace上下文失败: {e}，继续执行但不记录到Langfuse", exc_info=True)
        return trace_id


def get_current_trace_id() -> Optional[str]:
    """
    获取当前上下文的Trace ID
    
    Returns:
        str: Trace ID，如果未设置则返回None
    """
    return _trace_context.get()


def create_langfuse_handler(
    context: Optional[Dict[str, Any]] = None
) -> Optional["LangfuseCallbackHandler"]:
    """
    创建Langfuse CallbackHandler
    
    用于在LLM调用时自动记录到Langfuse。
    
    Args:
        context: 上下文信息（可选，用于记录元数据）
                如果包含 trace_id 键，将用于关联到已存在的 Trace
        
    Returns:
        LangfuseCallbackHandler: Langfuse回调处理器，如果Langfuse未启用或配置不完整则返回None
        
    Raises:
        ValueError: Langfuse未启用或配置不完整
    """
    # 检查是否启用（从统一配置读取）
    if not settings.LANGFUSE_ENABLED:
        logger.debug("[Langfuse] CallbackHandler: Langfuse未启用")
        return None
    
    # 从统一配置读取
    public_key = settings.LANGFUSE_PUBLIC_KEY
    secret_key = settings.LANGFUSE_SECRET_KEY
    
    if not public_key or not secret_key:
        logger.warning(
            "[Langfuse] CallbackHandler: 配置不完整，缺少PUBLIC_KEY或SECRET_KEY。"
            "请检查.env文件配置。"
        )
        return None
    
    # 确保全局 Langfuse 客户端已初始化（用于 secret_key 和 host 配置）
    # langfuse 3.x 的 CallbackHandler 会使用全局客户端配置
    _get_langfuse_client()
    
    # 构建 trace_context（用于分布式追踪）
    trace_context = None
    if context and isinstance(context, dict) and context.get("trace_id"):
        trace_context = {"trace_id": context.get("trace_id")}
    
    try:
        # 创建 Langfuse Callback Handler
        # 注意：langfuse.langchain.CallbackHandler 只需要 public_key，不需要 secret_key
        # secret_key 通过全局客户端配置传递
        handler = LangfuseCallbackHandler(
            public_key=public_key,
            update_trace=True,  # 更新 trace 信息
            trace_context=trace_context,  # 关联到已存在的 trace
        )
        
        logger.debug(
            f"[Langfuse] CallbackHandler创建成功: "
            f"trace_context={trace_context}, context={context}"
        )
        return handler
    
    except Exception as e:
        logger.error(f"[Langfuse] CallbackHandler创建失败: {e}", exc_info=True)
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
        
    Example:
        >>> normalize_langfuse_trace_id("2ae02464-a2ed-48dc-9802-ea8200e1ca6a")
        "2ae02464a2ed48dc9802ea8200e1ca6a"
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

def _get_langfuse_client() -> Optional["Langfuse"]:
    """
    获取或创建Langfuse客户端实例（单例模式）
    
    Returns:
        Langfuse: Langfuse客户端实例，如果未启用或初始化失败则返回None
    """
    global _langfuse_client
    
    # 检查是否启用Langfuse（从统一配置读取）
    if not settings.LANGFUSE_ENABLED:
        logger.debug("Langfuse未启用（settings.LANGFUSE_ENABLED=False）")
        return None
    
    # 如果已创建，直接返回
    if _langfuse_client is not None:
        return _langfuse_client
    
    if Langfuse is None:
        logger.warning("Langfuse SDK 未安装")
        return None
    
    try:
        # 从统一配置读取配置
        public_key = settings.LANGFUSE_PUBLIC_KEY
        secret_key = settings.LANGFUSE_SECRET_KEY
        host = settings.LANGFUSE_HOST
        
        if not public_key or not secret_key:
            logger.warning(
                "Langfuse配置不完整：缺少LANGFUSE_PUBLIC_KEY或LANGFUSE_SECRET_KEY，"
                "Langfuse功能将不可用。请检查环境变量配置。"
            )
            return None
        
        # 创建Langfuse客户端
        # 如果host为None，Langfuse会使用默认值，但为了明确，我们记录警告
        if host is None:
            logger.warning("LANGFUSE_HOST未设置，Langfuse将使用默认host")
        
        langfuse_kwargs = {
            "public_key": public_key,
            "secret_key": secret_key,
        }
        if host:
            langfuse_kwargs["host"] = host
        
        _langfuse_client = Langfuse(**langfuse_kwargs)
        
        logger.info(
            f"Langfuse客户端初始化成功: host={host or 'default'}, "
            f"public_key_prefix={public_key[:8] if public_key else 'None'}..."
        )
        return _langfuse_client
    
    except Exception as e:
        logger.error(f"Langfuse客户端初始化失败: {e}", exc_info=True)
        return None

def is_langfuse_available() -> bool:
    """
    检查Langfuse是否可用
    
    Returns:
        bool: 如果Langfuse可用返回True，否则返回False
    """
    # 从统一配置读取
    if not settings.LANGFUSE_ENABLED:
        return False
    
    client = get_langfuse_client()
    return client is not None

def get_langfuse_client() -> Optional["Langfuse"]:
    """
    获取Langfuse客户端实例（公共接口）
    
    Returns:
        Langfuse: Langfuse客户端实例，如果未启用或初始化失败则返回None
    """
    return _get_langfuse_client()

