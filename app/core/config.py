"""
应用配置管理
使用 Pydantic Settings 管理配置
"""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    
    # Langfuse 配置
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"  # 或自托管地址
    
    # 提示词配置
    PROMPT_USE_LANGFUSE: bool = True  # 是否优先使用Langfuse（默认true）
    PROMPT_CACHE_TTL: int = 300  # 提示词缓存TTL（秒）
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

