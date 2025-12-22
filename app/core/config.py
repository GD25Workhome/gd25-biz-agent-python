"""
应用配置管理
使用 Pydantic Settings 管理配置
"""
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


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
    
    # 数据库配置
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "langgraphflow"
    DB_TIMEZONE: str = "Asia/Shanghai"
    
    @property
    def DB_URI(self) -> str:
        """同步数据库连接 URI"""
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def ASYNC_DB_URI(self) -> str:
        """异步数据库连接 URI"""
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def CHECKPOINTER_DB_URI(self) -> str:
        """
        Checkpointer 专用连接 URI
        
        注意：psycopg_pool.AsyncConnectionPool 需要标准的 PostgreSQL URI 格式（postgresql://），
        不能使用 SQLAlchemy 格式（postgresql+psycopg://）
        """
        uri = f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        # 确保返回标准格式，移除任何 SQLAlchemy 驱动前缀
        if uri.startswith("postgresql+psycopg://"):
            uri = uri.replace("postgresql+psycopg://", "postgresql://", 1)
        elif uri.startswith("postgresql+asyncpg://"):
            uri = uri.replace("postgresql+asyncpg://", "postgresql://", 1)
        return uri
    
    # LLM 配置
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"
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
    # 支持两种环境变量名：LANGFUSE_BASE_URL（优先）和 LANGFUSE_HOST（向后兼容）
    LANGFUSE_BASE_URL: Optional[str] = None
    LANGFUSE_HOST: Optional[str] = None
    
    @model_validator(mode='after')
    def resolve_langfuse_host(self):
        """
        解析 Langfuse Host 配置
        优先使用 LANGFUSE_BASE_URL，如果未设置则使用 LANGFUSE_HOST
        """
        if not self.LANGFUSE_HOST and self.LANGFUSE_BASE_URL:
            self.LANGFUSE_HOST = self.LANGFUSE_BASE_URL
        return self
    
    # 提示词配置
    PROMPT_USE_LANGFUSE: bool = True  # 是否优先使用Langfuse（默认true）
    PROMPT_CACHE_TTL: int = 300  # 提示词缓存TTL（秒）
    
    model_config = SettingsConfigDict(
        env_file=str(find_project_root() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

