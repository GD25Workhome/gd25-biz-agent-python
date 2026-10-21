"""
应用配置管理（规则二最小集）

只保留规则二运行所需配置：
- 华院 LLM 网关
- DeepSeek Search / Fetch
- exhibition MySQL
- radar_score event worker
- Langfuse（可选）
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
    # backend/app/config.py -> backend -> 项目根目录
    project_root = current.parent.parent.parent

    env_file = project_root / ".env"
    if env_file.exists():
        return project_root

    for parent in current.parents:
        env_file = parent / ".env"
        if env_file.exists():
            return parent

    return project_root


# 以项目 .env 为准覆盖 shell 中残留的同名变量
_PROJECT_ROOT = find_project_root()
_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)


class Settings(BaseSettings):
    """应用配置（规则二）。"""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---------------- LLM ----------------
    HUAYUAN_API_KEY: Optional[str] = Field(
        default=None,
        description="公司统一 LLM 网关鉴权 key（provider=huayuan）",
    )
    DEEPSEEK_API_KEY: Optional[str] = Field(
        default=None,
        description="DeepSeek 平台 API Key（搜索 key 未配置时的回退）",
    )
    DEEPSEEK_SEARCH_KEY: Optional[str] = Field(
        default=None,
        description="DeepSeek Search / Fetch key；留空回退 DEEPSEEK_API_KEY",
    )
    DEEPSEEK_SEARCH_BASE_URL: str = Field(
        default="https://api.deepseek.com",
        description="DeepSeek API Base URL（Search / Fetch 同源）",
    )
    DEEPSEEK_SEARCH_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        description="DeepSeek Search / Fetch 单次请求超时（秒）",
    )
    LLM_TEMPERATURE: float = Field(default=0.7, description="默认温度参数")

    # ---------------- AnySearch（可选检索工具，DB 凭证池） ----------------
    # ANY_SEARCH_API_KEYS 非空时只用该逗号分隔池；为空才回退下面两个单 key 别名。
    ANY_SEARCH_API_KEYS: Optional[str] = Field(
        default=None,
        description="AnySearch API Key 池，逗号分隔、按顺序故障转移；非空时覆盖单 key",
    )
    ANY_SEARCH_API_KEY: Optional[str] = Field(
        default=None,
        description="AnySearch API Key（本仓库约定名；池为空时使用）",
    )
    ANYSEARCH_API_KEY: Optional[str] = Field(
        default=None,
        description="AnySearch API Key（官方文档变量名；池为空时与 ANY_SEARCH_API_KEY 一并入池）",
    )

    # ---------------- exhibition MySQL ----------------
    EXHIBITION_MYSQL_HOST: Optional[str] = Field(
        default=None, description="exhibition MySQL 主机"
    )
    EXHIBITION_MYSQL_PORT: int = Field(default=3306, description="exhibition MySQL 端口")
    EXHIBITION_MYSQL_USER: Optional[str] = Field(
        default=None, description="exhibition MySQL 用户名"
    )
    EXHIBITION_MYSQL_PASSWORD: Optional[str] = Field(
        default=None, description="exhibition MySQL 密码（只落 .env）"
    )
    EXHIBITION_MYSQL_DB: Optional[str] = Field(
        default=None, description="exhibition MySQL 库名（unidt_exhibition）"
    )
    EXHIBITION_MYSQL_CHARSET: str = Field(
        default="utf8mb4", description="连接字符集"
    )
    EXHIBITION_MYSQL_CONNECT_TIMEOUT: int = Field(
        default=10, description="建连超时（秒）"
    )

    @property
    def is_exhibition_mysql_enabled(self) -> bool:
        """exhibition MySQL 可用性：host / user / db 三项齐备。"""
        return bool(
            (self.EXHIBITION_MYSQL_HOST or "").strip()
            and (self.EXHIBITION_MYSQL_USER or "").strip()
            and (self.EXHIBITION_MYSQL_DB or "").strip()
        )

    def require_exhibition_mysql(self) -> dict:
        """
            返回 exhibition MySQL 连接参数；未配置时抛出明确错误。

            ⚠️ 返回值含密码，只允许传给建连函数，禁止打日志。

            Returns:
                dict: host / port / user / password / database / charset 等

            Raises:
                RuntimeError: 未配置 exhibition MySQL
        """
        if not self.is_exhibition_mysql_enabled:
            raise RuntimeError(
                "未配置 exhibition MySQL。请在 .env 设置 "
                "EXHIBITION_MYSQL_HOST / EXHIBITION_MYSQL_USER / "
                "EXHIBITION_MYSQL_PASSWORD / EXHIBITION_MYSQL_DB。"
            )
        return {
            "host": (self.EXHIBITION_MYSQL_HOST or "").strip(),
            "port": int(self.EXHIBITION_MYSQL_PORT),
            "user": (self.EXHIBITION_MYSQL_USER or "").strip(),
            "password": self.EXHIBITION_MYSQL_PASSWORD or "",
            "database": (self.EXHIBITION_MYSQL_DB or "").strip(),
            "charset": self.EXHIBITION_MYSQL_CHARSET,
            "connect_timeout": int(self.EXHIBITION_MYSQL_CONNECT_TIMEOUT),
        }

    # ---------------- radar_score ----------------
    RADAR_SCORE_WORKER_IN_APP: bool = Field(
        default=False,
        description=(
            "在 FastAPI lifespan 内以后台线程启动 radar_score event 调度。"
            "默认 false：也可另起 python -m radar_score。"
        ),
    )

    # ---------------- 配置文件 ----------------
    MODEL_PROVIDERS_CONFIG: str = Field(
        default="config/model_providers.yaml",
        description="模型供应商配置文件路径（相对于项目根目录）",
    )

    # ---------------- Langfuse（可选） ----------------
    LANGFUSE_ENABLED: bool = Field(
        default=False, description="是否启用 Langfuse 可观测性"
    )
    LANGFUSE_PUBLIC_KEY: Optional[str] = Field(default=None)
    LANGFUSE_SECRET_KEY: Optional[str] = Field(default=None)
    LANGFUSE_HOST: Optional[str] = Field(
        default=None, description="Langfuse 服务地址（优先）"
    )
    LANGFUSE_BASE_URL: Optional[str] = Field(
        default=None, description="Langfuse 服务地址别名"
    )

    @model_validator(mode="after")
    def resolve_langfuse_host(self) -> "Settings":
        """统一 Langfuse 地址：BASE_URL 优先于 HOST。"""
        host = (self.LANGFUSE_HOST or "").strip() or None
        base = (self.LANGFUSE_BASE_URL or "").strip() or None
        resolved = base or host
        self.LANGFUSE_HOST = resolved
        self.LANGFUSE_BASE_URL = resolved
        return self


# 创建全局配置实例
settings = Settings()
