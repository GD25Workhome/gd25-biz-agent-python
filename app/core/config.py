import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # 数据库配置
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "gd25_agent"
    
    @property
    def DB_URI(self) -> str:
        """获取同步数据库连接 URI"""
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def ASYNC_DB_URI(self) -> str:
        """获取异步数据库连接 URI"""
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # Redis 配置
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    @property
    def REDIS_URL(self) -> str:
        """获取 Redis 连接 URL"""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # 大语言模型 (LLM) 配置
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str = "https://api.deepseek.com/v1"
    # 兼容 OpenAIEmbeddings 的别名
    @property
    def OPENAI_API_BASE(self) -> str:
        return self.OPENAI_BASE_URL

    LLM_MODEL: str = "deepseek-chat"
    LLM_TEMPERATURE: float = 0.0
    EMBEDDING_MODEL: str = "moka-ai/m3e-base"
    
    # RAG / 向量嵌入配置
    HF_ENDPOINT: str = "https://hf-mirror.com"
    EMBEDDING_DIMENSION: int = 768
    USE_LOCAL_EMBEDDING: bool = True

    # 应用配置
    LOG_LEVEL: str = "INFO"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
