"""
应用配置管理
使用 Pydantic Settings 管理配置
"""
from pathlib import Path
from typing import Optional, Union
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_project_root() -> Path:
    """
    查找项目根目录（包含 .env 文件的目录）
    
    Returns:
        Path: 项目根目录路径
    """
    current = Path(__file__).resolve()
    # 当前文件位于 app/core/config.py，项目根目录应该是 current.parent.parent
    project_root = current.parent.parent
    
    # 验证项目根目录是否存在 .env 文件
    env_file = project_root / ".env"
    if env_file.exists():
        return project_root
    
    # 如果项目根目录没有 .env，向上查找
    for parent in current.parents:
        env_file = parent / ".env"
        if env_file.exists():
            return parent
    
    # 如果都找不到，返回计算出的项目根目录（可能 .env 文件不存在）
    return project_root


class Settings(BaseSettings):
    """应用配置"""
    
    # 数据库配置（必须从 .env 读取，无默认值）
    DB_HOST: Optional[str] = None
    DB_PORT: Optional[int] = None
    DB_USER: Optional[str] = None
    DB_PASSWORD: Optional[str] = None
    DB_NAME: Optional[str] = None
    DB_TIMEZONE: str = "Asia/Shanghai"  # 时区配置保留默认值
    
    @property
    def DB_URI(self) -> str:
        """同步数据库连接 URI"""
        if not all([self.DB_HOST, self.DB_PORT, self.DB_USER, self.DB_PASSWORD, self.DB_NAME]):
            raise ValueError("数据库配置不完整，请设置 DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME")
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def ASYNC_DB_URI(self) -> str:
        """异步数据库连接 URI"""
        if not all([self.DB_HOST, self.DB_PORT, self.DB_USER, self.DB_PASSWORD, self.DB_NAME]):
            raise ValueError("数据库配置不完整，请设置 DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME")
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def CHECKPOINTER_DB_URI(self) -> str:
        """
        Checkpointer 专用连接 URI
        
        注意：psycopg_pool.AsyncConnectionPool 需要标准的 PostgreSQL URI 格式（postgresql://），
        不能使用 SQLAlchemy 格式（postgresql+psycopg://）
        """
        if not all([self.DB_HOST, self.DB_PORT, self.DB_USER, self.DB_PASSWORD, self.DB_NAME]):
            raise ValueError("数据库配置不完整，请设置 DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME")
        uri = f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        # 确保返回标准格式，移除任何 SQLAlchemy 驱动前缀
        if uri.startswith("postgresql+psycopg://"):
            uri = uri.replace("postgresql+psycopg://", "postgresql://", 1)
        elif uri.startswith("postgresql+asyncpg://"):
            uri = uri.replace("postgresql+asyncpg://", "postgresql://", 1)
        return uri
    
    # LLM 配置（必须从 .env 读取，无默认值）
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    LLM_MODEL: Optional[str] = None
    # 兼容旧参数，同时新增可配置默认/场景温度
    LLM_TEMPERATURE: float = 0.0
    LLM_TEMPERATURE_DEFAULT: float = 0.0
    LLM_TEMPERATURE_INTENT: float = 0.0
    LLM_TEMPERATURE_CLARIFY: float = 0.3
    LLM_TOP_P_DEFAULT: float = 1.0
    LLM_MAX_TOKENS_DEFAULT: Optional[int] = None
    LLM_LOG_ENABLE: bool = False
    LLM_LOG_SAMPLE_RATE: float = 1.0
    LLM_LOG_MAX_TEXT_LENGTH: int = 400000
    
    # 路由配置
    INTENT_CONFIDENCE_THRESHOLD: float = 0.8
    
    # Java 微服务配置
    JAVA_SERVICE_BASE_URL: Optional[str] = None
    JAVA_SERVICE_TIMEOUT: int = 30
    
    # 应用配置
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    
    # Langfuse 配置（仅从 .env 文件读取，无默认值）
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: Optional[str] = None
    
    # Langfuse 性能配置（可从 .env 文件读取，如果未配置或值为空则使用默认值）
    LANGFUSE_FLUSH_AT: int = Field(
        default=20,
        description="批量发送阈值（每 N 条记录批量发送一次），可从 .env 文件中的 LANGFUSE_FLUSH_AT 配置"
    )
    LANGFUSE_FLUSH_INTERVAL: float = Field(
        default=5.0,
        description="自动发送间隔（秒），可从 .env 文件中的 LANGFUSE_FLUSH_INTERVAL 配置"
    )
    LANGFUSE_TIMEOUT: int = Field(
        default=2,
        description="HTTP 请求超时（秒），可从 .env 文件中的 LANGFUSE_TIMEOUT 配置"
    )
    LANGFUSE_DEBUG: bool = Field(
        default=False,
        description="是否启用调试模式，可从 .env 文件中的 LANGFUSE_DEBUG 配置"
    )
    LANGFUSE_TRACING_ENABLED: bool = Field(
        default=True,
        description="是否启用追踪（默认启用），可从 .env 文件中的 LANGFUSE_TRACING_ENABLED 配置"
    )
    LANGFUSE_ENABLE_SPANS: bool = Field(
        default=True,
        description="是否启用 Span 追踪（默认启用），可从 .env 文件中的 LANGFUSE_ENABLE_SPANS 配置"
    )
    
    @field_validator('LANGFUSE_FLUSH_AT', mode='before')
    @classmethod
    def _validate_flush_at(cls, v: Union[int, str, None]) -> int:
        """验证 LANGFUSE_FLUSH_AT，空值时使用默认值"""
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return 20
        return int(v)
    
    @field_validator('LANGFUSE_FLUSH_INTERVAL', mode='before')
    @classmethod
    def _validate_flush_interval(cls, v: Union[float, str, None]) -> float:
        """验证 LANGFUSE_FLUSH_INTERVAL，空值时使用默认值"""
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return 5.0
        return float(v)
    
    @field_validator('LANGFUSE_TIMEOUT', mode='before')
    @classmethod
    def _validate_timeout(cls, v: Union[int, str, None]) -> int:
        """验证 LANGFUSE_TIMEOUT，空值时使用默认值"""
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return 2
        return int(v)
    
    @field_validator('LANGFUSE_DEBUG', mode='before')
    @classmethod
    def _validate_debug(cls, v: Union[bool, str, None]) -> bool:
        """验证 LANGFUSE_DEBUG，空值时使用默认值"""
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return False
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)
    
    @field_validator('LANGFUSE_TRACING_ENABLED', mode='before')
    @classmethod
    def _validate_tracing_enabled(cls, v: Union[bool, str, None]) -> bool:
        """验证 LANGFUSE_TRACING_ENABLED，空值时使用默认值"""
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return True
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)
    
    @field_validator('LANGFUSE_ENABLE_SPANS', mode='before')
    @classmethod
    def _validate_enable_spans(cls, v: Union[bool, str, None]) -> bool:
        """验证 LANGFUSE_ENABLE_SPANS，空值时使用默认值"""
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return True
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)
    
    @field_validator('PROMPT_SOURCE_MODE', mode='before')
    @classmethod
    def _validate_prompt_source_mode(cls, v: Union[str, None]) -> str:
        """验证提示词读取模式"""
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return "auto"
        v = v.strip().lower()
        if v not in ("langfuse", "local", "auto"):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"无效的PROMPT_SOURCE_MODE值: {v}，使用默认值auto")
            return "auto"
        return v
    
    # 提示词配置
    PROMPT_USE_LANGFUSE: bool = True  # 是否使用Langfuse（默认true，但Langfuse是唯一数据源）
    PROMPT_SOURCE_MODE: str = Field(
        default="auto",
        description="提示词读取模式: langfuse(仅Langfuse) | local(仅本地) | auto(自动降级)"
    )
    PROMPT_CACHE_TTL: int = 300  # 提示词缓存TTL（秒）
    
    model_config = SettingsConfigDict(
        env_file=str(find_project_root() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

