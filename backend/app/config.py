"""
应用配置管理
使用 Pydantic Settings 管理配置
"""
import os
from pathlib import Path
from typing import Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_project_root() -> Path:
    """
    查找项目根目录（包含 .env 文件的目录）
    
    Returns:
        Path: 项目根目录路径
    """
    current = Path(__file__).resolve()
    # 当前文件位于 backend/app/config.py，项目根目录应该是 current.parent.parent.parent
    project_root = current.parent.parent.parent
    
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
    
    model_config = SettingsConfigDict(
        env_file=find_project_root() / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
    
    # 数据库配置
    DATABASE_URL: str  # 数据库连接URL，格式：postgresql+psycopg://user:password@host:port/dbname
    DB_TIMEZONE: str = "Asia/Shanghai"  # 时区配置
    
    @property
    def DB_URI(self) -> str:
        """同步数据库连接 URI"""
        return self.DATABASE_URL
    
    @property
    def ASYNC_DB_URI(self) -> str:
        """异步数据库连接 URI"""
        return self.DATABASE_URL
    
    # 模型供应商API密钥配置（从环境变量读取）
    OPENAI_API_KEY: Optional[str] = None
    DOUBAO_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    
    # 默认模型配置（可选）
    LLM_MODEL: str = Field(default="doubao-seed-1-6-251015", description="默认模型名称")
    LLM_TEMPERATURE: float = Field(default=0.7, description="默认温度参数")
    
    # 配置文件路径
    MODEL_PROVIDERS_CONFIG: str = Field(
        default="config/model_providers.yaml",
        description="模型供应商配置文件路径（相对于项目根目录）"
    )
    
    # Langfuse可观测性配置
    LANGFUSE_ENABLED: bool = Field(
        default=False,
        description="是否启用Langfuse可观测性"
    )
    LANGFUSE_PUBLIC_KEY: Optional[str] = Field(
        default=None,
        description="Langfuse公钥（从.env文件读取）"
    )
    LANGFUSE_SECRET_KEY: Optional[str] = Field(
        default=None,
        description="Langfuse密钥（从.env文件读取）"
    )
    LANGFUSE_HOST: Optional[str] = Field(
        default=None,
        description="Langfuse服务器地址（可选，默认使用cloud.langfuse.com）"
    )


# 创建全局配置实例
settings = Settings()

