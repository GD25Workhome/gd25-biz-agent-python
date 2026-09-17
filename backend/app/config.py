"""
应用配置管理
使用 Pydantic Settings 管理配置
"""
from pathlib import Path
from typing import Dict, Mapping, Optional

from dotenv import dotenv_values, load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Claude Agent SDK 子进程环境键（凭证 / 模型）
ANTHROPIC_SDK_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
)

# 项目默认网关（与 .env.example 一致；仅 BASE_URL / MODEL 可缺省回落）
ANTHROPIC_SDK_DEFAULTS: Dict[str, str] = {
    "ANTHROPIC_BASE_URL": "https://ai-api.unidtai.com/openapi/llm/anthropic",
    "ANTHROPIC_MODEL": "deepseek/deepseek-v4.1-flash",
}

# 与本机 ~/.claude 隔离的运行时目录名（落在项目根下，应 gitignore）
CLAUDE_SDK_RUNTIME_DIRNAME = ".claude_sdk_runtime"


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
# 仅来自项目 .env 文件的键值快照（用于 SDK 与本机 shell 个人 key 隔离）
_PROJECT_DOTENV: Dict[str, Optional[str]] = {}
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)
    _PROJECT_DOTENV = dict(dotenv_values(_ENV_FILE))


def resolve_anthropic_sdk_value(
    key: str,
    settings_fallback: Optional[str] = None,
    *,
    project_dotenv: Optional[Mapping[str, Optional[str]]] = None,
    env_file: Optional[Path] = None,
) -> Optional[str]:
    """
        解析 Claude Agent SDK 用的 Anthropic 配置项（与本机 Claude / shell 隔离）。

        - 项目根存在 .env 时：只认 .env 中显式写出的键，不回退 shell / 本机个人 key
        - 不存在 .env 时（如 K8s 仅注入进程环境）：使用 settings_fallback
        - BASE_URL / MODEL 仍为空时回落到项目默认值

        Args:
            key: 环境变量名，如 ANTHROPIC_AUTH_TOKEN
            settings_fallback: 无 .env 时的 Settings / 进程环境回退值
            project_dotenv: 测试可注入的 .env 快照；默认用模块加载时的快照
            env_file: 测试可注入的 .env 路径；默认用项目根 .env

        Returns:
            解析后的非空字符串；未配置则 None
    """
    dotenv_map = (
        _PROJECT_DOTENV if project_dotenv is None else dict(project_dotenv)
    )
    file_path = _ENV_FILE if env_file is None else env_file
    raw: Optional[str] = None

    # 1. 有项目 .env：只认文件内显式键，避免本机 shell 个人 ANTHROPIC_* 渗入
    if file_path.exists():
        if key in dotenv_map:
            file_val = dotenv_map.get(key)
            raw = str(file_val).strip() if file_val else None
        else:
            raw = None
    else:
        # 2. 无 .env（容器 / K8s）：允许进程环境经 Settings 注入
        raw = (settings_fallback or "").strip() or None

    # 3. 网关与模型给项目缺省，凭证类不设缺省
    if raw is None and key in ANTHROPIC_SDK_DEFAULTS:
        return ANTHROPIC_SDK_DEFAULTS[key]
    return raw


def build_claude_sdk_env(
    settings_obj: "Settings",
    *,
    project_dotenv: Optional[Mapping[str, Optional[str]]] = None,
    env_file: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> Dict[str, str]:
    """
        组装传给 Claude Agent SDK / CLI 子进程的环境变量。

        要点：
        - 凭证只来自 resolve_anthropic_sdk_value（本地不读 shell 个人 key）
        - 对未配置的 ANTHROPIC_* 显式写空串，覆盖 Python SDK「merge 父进程环境」带来的串扰
        - CLAUDE_CONFIG_DIR 指向项目内目录，避免加载 ~/.claude

        Args:
            settings_obj: 应用 Settings
            project_dotenv: 测试可注入的 .env 快照
            env_file: 测试可注入的 .env 路径
            project_root: 测试可注入的项目根

        Returns:
            可直接传给 ClaudeAgentOptions(env=...) 的字典
    """
    root = _PROJECT_ROOT if project_root is None else project_root
    env: Dict[str, str] = {}

    # 1. Anthropic 凭证与模型（空串用于冲掉父进程个人 key）
    for key in ANTHROPIC_SDK_ENV_KEYS:
        fallback = getattr(settings_obj, key, None)
        value = resolve_anthropic_sdk_value(
            key,
            fallback if isinstance(fallback, str) else None,
            project_dotenv=project_dotenv,
            env_file=env_file,
        )
        env[key] = value if value else ""

    # 2. 隔离本机 Claude Code 用户配置
    configured_dir = (getattr(settings_obj, "CLAUDE_SDK_CONFIG_DIR", None) or "").strip()
    config_dir = Path(configured_dir) if configured_dir else (root / CLAUDE_SDK_RUNTIME_DIRNAME)
    config_dir.mkdir(parents=True, exist_ok=True)
    env["CLAUDE_CONFIG_DIR"] = str(config_dir.resolve())
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    return env


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
            新闻 URL 抓取可用性：显式开启 + 有项目 Anthropic 凭证。

            凭证解析走 resolve_anthropic_sdk_value：本地只认项目 .env，
            不把本机 shell / Claude 个人 key 算作已配置。
            不依赖 is_database_enabled —— ENABLE_DATABASE=false 下也能工作。
        """
        has_credential = bool(
            resolve_anthropic_sdk_value(
                "ANTHROPIC_AUTH_TOKEN", self.ANTHROPIC_AUTH_TOKEN
            )
            or resolve_anthropic_sdk_value(
                "ANTHROPIC_API_KEY", self.ANTHROPIC_API_KEY
            )
        )
        return bool(self.NEWS_CRAWL_ENABLED and has_credential)

    def build_claude_sdk_env(self) -> Dict[str, str]:
        """组装 Claude Agent SDK 子进程环境（与本机 Claude 配置隔离）。"""
        return build_claude_sdk_env(self)

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
    # 本地请写在项目 .env；勿与本机 ~/.claude 个人 key 混用（见 build_claude_sdk_env）
    ANTHROPIC_BASE_URL: Optional[str] = Field(
        default=None,
        description="Anthropic 兼容网关地址；未配时用项目默认 unidtai anthropic 入口",
    )
    ANTHROPIC_AUTH_TOKEN: Optional[str] = Field(
        default=None, description="网关鉴权 token（与 ANTHROPIC_API_KEY 二选一）"
    )
    ANTHROPIC_API_KEY: Optional[str] = Field(
        default=None, description="Anthropic 官方 key（一般不走官方，留空即可）"
    )
    ANTHROPIC_MODEL: Optional[str] = Field(
        default=None,
        description="Agent 使用的模型；未配时默认 deepseek/deepseek-v4.1-flash",
    )
    ANTHROPIC_SMALL_FAST_MODEL: Optional[str] = Field(default=None)
    ANTHROPIC_DEFAULT_HAIKU_MODEL: Optional[str] = Field(default=None)
    ANTHROPIC_DEFAULT_SONNET_MODEL: Optional[str] = Field(default=None)
    ANTHROPIC_DEFAULT_OPUS_MODEL: Optional[str] = Field(default=None)
    CLAUDE_SDK_CONFIG_DIR: Optional[str] = Field(
        default=None,
        description=(
            "Claude CLI 配置目录（CLAUDE_CONFIG_DIR）；"
            "默认项目根下 .claude_sdk_runtime，与本机 ~/.claude 隔离"
        ),
    )

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
        default="radar_company_news_chunk",
        description=(
            "新闻知识库 collection 名（V2 一行一 chunk；"
            "建在 MILVUS_DB_NAME 库内，不与库内其它项目 collection 混用）"
        ),
    )

    @property
    def is_milvus_enabled(self) -> bool:
        """Milvus 可用性：有地址 + 有 user/password 或 token。"""
        return bool(self.MILVUS_URI and (self.MILVUS_TOKEN or (self.MILVUS_USER and self.MILVUS_PASSWORD)))

    # ---------------- 雷达新闻知识库（exhibition MySQL，三张表） ----------------
    # 设计文档：exhibition projectDocs/技术设计-260915/02-知识库的构建/01-Claude的思考.md
    #          §3.1（两段式 worker）/ §4.1、§4.2；闸门见 ai_docs/26091605
    #
    # ⚠️ 访问边界（硬性）：gd25 对 exhibition MySQL 只碰三张表
    #    - radar_news_content_task        SELECT / UPDATE（抢锁、回写状态）
    #    - radar_company_news_document    INSERT / UPDATE / SELECT（写正文、补跑扫描）
    #    - radar_news_agent_guard         Agent 兜底闸门按日计数（DDL: scripts/sql/18_...）
    #    其余 exhibition 表零接触；DDL 归 exhibition Java SQL 脚本
    #    （projectDocs/.../17_radar_news_content_schema.sql + 18_radar_news_agent_guard.sql）。
    #
    # ⚠️ 与 gd25 主库（PostgreSQL，DATABASE_URL）完全独立。
    #    默认由 scripts/news_content_worker.py 常驻；也可设 NEWS_CONTENT_WORKER_IN_APP=true
    #    在 FastAPI lifespan 内拉起同一主循环（方案 A′，仍扫表抢锁，非 Rewritten 内存队列）。
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
    NEWS_CONTENT_WORKER_IN_APP: bool = Field(
        default=False,
        description=(
            "【遗留】仅启动旧 news_content_worker 应用内循环。"
            "L2 请用 RADAR_KB_WORKER_IN_APP；二者同时开启时会跳过本项，避免双扫 content_task。"
        ),
    )
    RADAR_KB_WORKER_IN_APP: bool = Field(
        default=True,
        description=(
            "L2：在 FastAPI lifespan 内以后台线程启动 radar_kb 发现+正文调度器；"
            "默认 true。设 false 可退回独立进程 python -m radar_kb。"
            "需配置 EXHIBITION_MYSQL_* 或 RADAR_DB_*。"
        ),
    )
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
        default=2000,
        description="【已废弃】V1 单向量截断；V2 请用 CHUNK_*，本字段读入后忽略",
    )
    NEWS_CONTENT_CHUNK_SIZE: int = Field(
        default=1000, description="V2 正文切分窗口字符数（不含 title 前缀）"
    )
    NEWS_CONTENT_CHUNK_OVERLAP: int = Field(
        default=200, description="V2 相邻 chunk 重叠字符数"
    )
    NEWS_CONTENT_CHUNK_MAX_PER_DOC: int = Field(
        default=50, description="V2 单篇最大 chunk 数；超出截断并打日志"
    )
    NEWS_CONTENT_EMBED_BATCH_SIZE: int = Field(
        default=16, description="V2 单次调用 embedding 网关的文本条数上限"
    )
    KNOWLEDGE_SEARCH_CHUNK_TOP_K_FACTOR: int = Field(
        default=8,
        description="召回候选 chunk 数 ≈ min(128, max(max_docs*factor, max_docs+8))",
    )
    KNOWLEDGE_BRIEF_QUOTE_MAX_CHARS: int = Field(
        default=500, description="知识库 brief.quote 最大字符数"
    )
    KNOWLEDGE_BRIEF_SECOND_CHUNK_ENABLED: bool = Field(
        default=True,
        description="策略 C：是否在 quote 中附非近邻第二高分 chunk（index 间隔≥2）",
    )
    NEWS_CONTENT_AGENT_FALLBACK_ENABLED: bool = Field(
        default=True, description="规则失败时是否启用 Agent 兜底"
    )
    NEWS_CONTENT_AGENT_DAILY_QUOTA: int = Field(
        default=30,
        description="Agent 兜底日配额（硬约束，落库原子扣减，多实例共享）；对齐 news-url-crawl 成本纪律",
    )
    NEWS_CONTENT_AGENT_MAX_CONSECUTIVE_FAILURES: int = Field(
        default=5,
        description="Agent 兜底连续系统失败（system）N 次后全局熔断（当日不再兜底）；内容失败不计入",
    )
    NEWS_CONTENT_AGENT_MAX_CONTENT_FAILURES_PER_SITE: int = Field(
        default=1,
        description=(
            "同一 source_url_id 下，可计入跳过的内容失败连续 N 次后，"
            "当日跳过该信息源 Agent 兜底（默认 1，更省配额）"
        ),
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

