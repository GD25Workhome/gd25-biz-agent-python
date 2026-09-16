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

    @property
    def is_news_crawl_enabled(self) -> bool:
        """
        新闻 URL 抓取可用性：显式开启 + 有 Anthropic 凭证。

        ⚠️ 不依赖 is_database_enabled —— 本功能无状态、不碰数据库，
        ENABLE_DATABASE=false 下也能正常工作。
        """
        has_credential = bool(self.ANTHROPIC_AUTH_TOKEN or self.ANTHROPIC_API_KEY)
        return bool(self.NEWS_CRAWL_ENABLED and has_credential)

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

    # ---------------- Claude Agent SDK（新闻 URL 抓取） ----------------
    # 设计文档：华院Agent设计/260914-整体重构/02-gd25侧详细设计.md §5.1
    ANTHROPIC_BASE_URL: Optional[str] = Field(
        default=None, description="Anthropic 兼容网关地址"
    )
    ANTHROPIC_AUTH_TOKEN: Optional[str] = Field(
        default=None, description="网关鉴权 token（与 ANTHROPIC_API_KEY 二选一）"
    )
    ANTHROPIC_API_KEY: Optional[str] = Field(
        default=None, description="Anthropic 官方 key"
    )
    ANTHROPIC_MODEL: Optional[str] = Field(
        default=None, description="Agent 使用的模型"
    )
    ANTHROPIC_SMALL_FAST_MODEL: Optional[str] = Field(default=None)

    # ---------------- 新闻 URL 抓取 ----------------
    NEWS_CRAWL_ENABLED: bool = Field(
        default=False, description="是否启用新闻 URL 抓取（未配置凭证时应关闭）"
    )
    NEWS_CRAWL_MAX_TURNS: int = Field(default=50, description="Agent 最大轮次")
    NEWS_CRAWL_TIMEOUT_SECONDS: int = Field(
        default=600, description="单次抓取墙钟超时（秒），超时返回 504"
    )
    NEWS_CRAWL_MAX_CONCURRENCY: int = Field(
        default=2, description="同时运行的 Agent 数上限；超出者排队"
    )
    NEWS_CRAWL_REQUEST_INTERVAL: float = Field(
        default=0.4, description="同站抓取最小请求间隔（秒），礼貌爬取"
    )

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

    # ---------------- 新闻知识库 embedding（公司统一 LLM 网关，OpenAI 兼容模式） ----------------
    # 设计文档：exhibition projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md
    # .env 键名按现网：HUAYUAN_API_KEY / HUAYUAN_API_URL_embeddings
    HUAYUAN_API_KEY: Optional[str] = Field(
        default=None,
        description="公司统一 LLM 网关鉴权 key（embedding 等 OpenAI 兼容接口共用）",
    )
    HUAYUAN_API_URL_embeddings: Optional[str] = Field(
        default=None,
        description="公司网关 embedding 完整端点（以 /embeddings 结尾）",
    )
    EMBEDDING_MODEL: str = Field(
        default="unidt/embedding-bge-m3",
        description="embedding 模型：unidt/embedding-bge-m3 / unidt/embedding-qwen3",
    )
    EMBEDDING_DIM: Optional[int] = Field(
        default=None,
        description="embedding 维度；None 时以接口返回为准（建 Milvus collection 前必须确认）",
    )
    EMBEDDING_TIMEOUT_SECONDS: int = Field(
        default=60, description="单次 embedding 请求超时（秒）"
    )
    EMBEDDING_BATCH_SIZE: int = Field(
        default=16, description="批量 embedding 单请求条数"
    )

    @property
    def is_embedding_enabled(self) -> bool:
        """知识库 embedding 可用性：显式配置端点 + 有鉴权 key。"""
        return bool(self.HUAYUAN_API_URL_embeddings and self.HUAYUAN_API_KEY)

    # ---------------- 新闻知识库 Milvus 向量库 ----------------
    MILVUS_URI: Optional[str] = Field(
        default=None, description="Milvus 连接地址，如 http://host:port"
    )
    MILVUS_USER: Optional[str] = Field(
        default=None, description="Milvus 用户名（与 TOKEN 二选一）"
    )
    MILVUS_PASSWORD: Optional[str] = Field(
        default=None, description="Milvus 密码"
    )
    MILVUS_TOKEN: Optional[str] = Field(
        default=None, description="Milvus token（与 USER/PASSWORD 二选一）"
    )
    MILVUS_DB_NAME: str = Field(
        default="exhibition_test", description="Milvus 数据库名（现网 exhibition_test 是库名，非 collection 名）"
    )
    MILVUS_COLLECTION: str = Field(
        default="radar_company_news_doc",
        description="新闻知识库 collection 名（建在 MILVUS_DB_NAME 库内，不与库内其它项目 collection 混用）",
    )

    @property
    def is_milvus_enabled(self) -> bool:
        """Milvus 可用性：有地址 + 有 user/password 或 token。"""
        return bool(self.MILVUS_URI and (self.MILVUS_TOKEN or (self.MILVUS_USER and self.MILVUS_PASSWORD)))

    # ---------------- 雷达新闻知识库（exhibition MySQL，仅两张表） ----------------
    # 设计文档：exhibition projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md
    #          §3.1（两段式 worker）/ §4.1、§4.2（两表定义）
    #
    # ⚠️ 访问边界（硬性）：gd25 对 exhibition MySQL 只碰两张表
    #    - radar_news_content_task        SELECT / UPDATE（抢锁、回写状态）
    #    - radar_company_news_document    INSERT / UPDATE / SELECT（写正文、补跑扫描）
    #    其余 exhibition 表零接触；DDL 归 exhibition Java SQL 脚本
    #    （projectDocs/技术设计文档-0905/SQL脚本/17_radar_news_content_schema.sql）。
    #
    # ⚠️ 与 gd25 主库（PostgreSQL，DATABASE_URL）完全独立：本组配置只服务
    #    news_content_worker 常驻进程，不参与 FastAPI 请求链路。
    EXHIBITION_MYSQL_HOST: Optional[str] = Field(
        default=None, description="exhibition MySQL 主机（雷达新闻知识库写链路）"
    )
    EXHIBITION_MYSQL_PORT: int = Field(default=3306, description="exhibition MySQL 端口")
    EXHIBITION_MYSQL_USER: Optional[str] = Field(
        default=None, description="exhibition MySQL 用户名"
    )
    EXHIBITION_MYSQL_PASSWORD: Optional[str] = Field(
        default=None, description="exhibition MySQL 密码（只落 .env，禁止入库/入库代码）"
    )
    EXHIBITION_MYSQL_DB: Optional[str] = Field(
        default=None, description="exhibition MySQL 库名（unidt_exhibition）"
    )
    EXHIBITION_MYSQL_CHARSET: str = Field(
        default="utf8mb4", description="连接字符集（表为 utf8mb4，勿改）"
    )
    EXHIBITION_MYSQL_CONNECT_TIMEOUT: int = Field(
        default=10, description="建连超时（秒）"
    )
    EXHIBITION_MYSQL_POOL_SIZE: int = Field(
        default=4, description="worker 侧连接池大小（单进程串行处理，无需很大）"
    )

    @property
    def is_exhibition_mysql_enabled(self) -> bool:
        """exhibition MySQL 可用性：host / user / db 三项齐备即可判定。"""
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
                "未配置 exhibition MySQL（雷达新闻知识库写链路）。"
                "请在 .env 设置 EXHIBITION_MYSQL_HOST / EXHIBITION_MYSQL_USER / "
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

    # ---------------- 雷达新闻知识库 worker 调参 ----------------
    # 与 NEWS_CRAWL_* 同风格：全部可用环境变量覆盖，默认值面向「常驻单实例」。
    NEWS_CONTENT_WORKER_ID: Optional[str] = Field(
        default=None,
        description="worker 实例标识；None 时用 hostname:pid 自动生成（写入 task.locked_by）",
    )
    NEWS_CONTENT_BATCH_SIZE: int = Field(
        default=5, description="每轮领取任务数上限（N）"
    )
    NEWS_CONTENT_POLL_INTERVAL_SECONDS: float = Field(
        default=15.0, description="无任务时的轮询间隔（秒）"
    )
    NEWS_CONTENT_LOCK_TIMEOUT_SECONDS: int = Field(
        default=1800, description="RUNNING 超时（秒）；超时未回写视为 worker 挂死，重置回 PENDING"
    )
    NEWS_CONTENT_SITE_MIN_INTERVAL_SECONDS: float = Field(
        default=2.0,
        description="同站（source_url_id 维度）最小抓取间隔（秒），网站礼貌抓取",
    )
    NEWS_CONTENT_HTTP_TIMEOUT_SECONDS: float = Field(
        default=25.0, description="详情页单次抓取超时（秒）"
    )
    NEWS_CONTENT_HTTP_MAX_RETRIES: int = Field(
        default=1, description="详情页规则抓取重试次数（总尝试 = 1 + 本值）"
    )
    NEWS_CONTENT_FETCH_MIN_CHARS: int = Field(
        default=120, description="正文最短字符数；低于此值视为规则抓取失败（走 Agent 兜底）"
    )
    NEWS_CONTENT_SUMMARY_MAX_LENGTH: int = Field(
        default=200, description="content_summary 摘要字数"
    )
    NEWS_CONTENT_EMBED_TEXT_MAX_CHARS: int = Field(
        default=2000, description="实际嵌入文本 = title + 正文前 N 字（V1 不分 chunk）"
    )
    NEWS_CONTENT_AGENT_FALLBACK_ENABLED: bool = Field(
        default=True, description="规则失败时是否启用 Agent 兜底"
    )
    NEWS_CONTENT_AGENT_DAILY_QUOTA: int = Field(
        default=30,
        description="Agent 兜底日配额（硬约束，按进程内自然日计数）；对齐 news-url-crawl 成本纪律",
    )
    NEWS_CONTENT_AGENT_MAX_CONSECUTIVE_FAILURES: int = Field(
        default=5, description="Agent 兜底连续失败 N 次后熔断（当日不再兜底）"
    )
    NEWS_CONTENT_AGENT_TIMEOUT_SECONDS: int = Field(
        default=180, description="单次 Agent 兜底墙钟超时（秒）"
    )
    NEWS_CONTENT_EMBED_BACKFILL_BATCH_SIZE: int = Field(
        default=10, description="补跑循环每轮扫描的 document 条数"
    )
    NEWS_CONTENT_EMBED_BACKFILL_INTERVAL_SECONDS: float = Field(
        default=120.0, description="补跑循环触发间隔（秒）"
    )
    NEWS_CONTENT_EMBED_MAX_ATTEMPTS: int = Field(
        default=3, description="单篇 embedding 最大尝试次数；超过后保持 embed_status=2 不再重试"
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

