"""
应用配置管理
使用 Pydantic Settings 管理配置
"""
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
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


# 以项目 .env 为准覆盖 shell 中残留的同名变量（常见于 LANGFUSE_HOST=localhost:3000）
_PROJECT_ROOT = find_project_root()
_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # 数据库配置（华院最小部署可不配 DATABASE_URL / 设 ENABLE_DATABASE=false）
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description=(
            "数据库连接 URL，格式："
            "postgresql+psycopg://user:password@host:port/dbname"
        ),
    )
    ENABLE_DATABASE: Optional[bool] = Field(
        default=None,
        description=(
            "是否启用数据库。None 时根据是否配置 DATABASE_URL 自动判断；"
            "显式 false 时即使有 DATABASE_URL 也不在启动时连接"
        ),
    )
    DB_TIMEZONE: str = "Asia/Shanghai"  # 时区配置

    @model_validator(mode="after")
    def resolve_enable_database(self) -> "Settings":
        """
            解析是否启用数据库：未显式配置时，有非空 DATABASE_URL 则启用。

            Raises:
                ValueError: ENABLE_DATABASE=true 但未配置 DATABASE_URL
        """
        url = (self.DATABASE_URL or "").strip()
        if self.ENABLE_DATABASE is None:
            self.ENABLE_DATABASE = bool(url)
        elif self.ENABLE_DATABASE and not url:
            raise ValueError(
                "ENABLE_DATABASE=true 时必须配置非空的 DATABASE_URL"
            )
        return self

    @property
    def is_database_enabled(self) -> bool:
        """当前是否启用数据库（启动与连接层统一入口）。"""
        return bool(self.ENABLE_DATABASE)

    def require_database_url(self) -> str:
        """
            返回已配置的 DATABASE_URL；未启用或未配置时抛出明确错误。

            Returns:
                str: 非空数据库连接 URL

            Raises:
                RuntimeError: 数据库未启用或 DATABASE_URL 为空
        """
        url = (self.DATABASE_URL or "").strip()
        if not self.is_database_enabled or not url:
            raise RuntimeError(
                "数据库未启用或未配置 DATABASE_URL。"
                "请设置 ENABLE_DATABASE=true 并配置 DATABASE_URL，"
                "或仅在需要 DB 的功能中调用此接口。"
            )
        return url

    @property
    def DB_URI(self) -> str:
        """同步数据库连接 URI。"""
        return self.require_database_url()

    @property
    def ASYNC_DB_URI(self) -> str:
        """异步数据库连接 URI。"""
        return self.require_database_url()

    # 模型供应商API密钥配置（从环境变量读取）
    OPENAI_API_KEY: Optional[str] = None
    DOUBAO_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None

    # AnySearch 联网检索（华院规则二）；双名兼容官方 ANYSEARCH_API_KEY
    ANY_SEARCH_API_KEY: Optional[str] = Field(
        default=None,
        description="AnySearch API Key（本仓库约定名）",
    )
    ANYSEARCH_API_KEY: Optional[str] = Field(
        default=None,
        description="AnySearch API Key（官方文档变量名）",
    )
    # 博查 Web Search（展厅发觉）；环境变量名按现网 .env：BO_CHA_APIKEY
    BO_CHA_APIKEY: Optional[str] = Field(
        default=None,
        description="博查 AI Web Search API Key",
    )

    # 默认模型配置（可选）
    LLM_MODEL: str = Field(default="doubao-seed-1-6-251015", description="默认模型名称")
    LLM_TEMPERATURE: float = Field(default=0.7, description="默认温度参数")

    # 配置文件路径
    MODEL_PROVIDERS_CONFIG: str = Field(
        default="config/model_providers.yaml",
        description="模型供应商配置文件路径（相对于项目根目录）",
    )

    # Langfuse可观测性配置
    LANGFUSE_ENABLED: bool = Field(
        default=False,
        description="是否启用Langfuse可观测性",
    )
    LANGFUSE_PUBLIC_KEY: Optional[str] = Field(
        default=None,
        description="Langfuse公钥（从.env文件读取）",
    )
    LANGFUSE_SECRET_KEY: Optional[str] = Field(
        default=None,
        description="Langfuse密钥（从.env文件读取）",
    )
    LANGFUSE_HOST: Optional[str] = Field(
        default=None,
        description="Langfuse 服务地址（优先）；未设时回退 LANGFUSE_BASE_URL",
    )
    LANGFUSE_BASE_URL: Optional[str] = Field(
        default=None,
        description="Langfuse 服务地址别名（SDK 官方变量名，与 LANGFUSE_HOST 等价）",
    )

    @model_validator(mode="after")
    def resolve_langfuse_host(self) -> "Settings":
        """
            统一 Langfuse 地址：与 SDK 一致，BASE_URL 优先于 HOST。

            避免 shell 残留 LANGFUSE_HOST=localhost:3000 覆盖 .env 中的
            LANGFUSE_BASE_URL=https://cloud.langfuse.com。
        """
        host = (self.LANGFUSE_HOST or "").strip() or None
        base = (self.LANGFUSE_BASE_URL or "").strip() or None
        resolved = base or host
        self.LANGFUSE_HOST = resolved
        self.LANGFUSE_BASE_URL = resolved
        return self


# 创建全局配置实例
settings = Settings()

