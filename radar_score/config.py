"""
radar_score 运行配置。

数据库优先 RADAR_DB_*，否则回退 exhibition MySQL。
默认不随 FastAPI 启动，由 RADAR_SCORE_WORKER_IN_APP 打开。
"""
from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env", override=False)

# locked_by / updater 列宽
LOCKED_BY_MAX_LEN = 64
PROFILE_KIND = "profile"
EVENT_KIND = "event"
JOB_KINDS = (PROFILE_KIND, EVENT_KIND)


def _parse_bool(raw: Optional[str], default: bool) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    text = str(raw).strip().lower()
    if text in ("1", "true", "yes", "on", "y"):
        return True
    if text in ("0", "false", "no", "off", "n"):
        return False
    return default


def _parse_optional_int(raw: Optional[str]) -> Optional[int]:
    if raw is None or str(raw).strip() == "":
        return None
    return int(str(raw).strip())


def build_locked_by(hostname: str, pid: int) -> str:
    """
        生成不超过 64 字符的自动调度锁标识。

        Args:
            hostname: 机器名
            pid: 进程号

        Returns:
            形如 python-score-{host}:{pid} 的字符串
    """
    prefix = "python-score-"
    suffix = f":{int(pid)}"
    room = LOCKED_BY_MAX_LEN - len(prefix) - len(suffix)
    host = (hostname or "host").strip() or "host"
    if room < 1:
        return f"{prefix}{suffix}"[:LOCKED_BY_MAX_LEN]
    return f"{prefix}{host[:room]}{suffix}"


def claim_quota(max_concurrency: int, in_flight: int) -> int:
    """
        本轮还能再领几条。

        Args:
            max_concurrency: 该类并发上限
            in_flight: 已经在跑的条数

        Returns:
            非负可领条数
    """
    return max(0, int(max_concurrency) - int(in_flight))


@dataclass(frozen=True)
class ScoreSettings:
    """评分自动调度配置。"""

    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    tenant_id: Optional[int]
    locked_by: str
    java_base_url: str
    java_token: str
    profile_concurrency: int
    event_concurrency: int
    poll_interval_sec: float
    stale_timeout_sec: int
    java_timeout_sec: float
    java_down_backoff_sec: float
    shutdown_wait_sec: float


def is_radar_score_in_app_enabled() -> bool:
    """
        是否在 FastAPI 内挂载评分调度。

        环境变量 RADAR_SCORE_WORKER_IN_APP，默认 false。
    """
    return _parse_bool(os.getenv("RADAR_SCORE_WORKER_IN_APP"), False)


def _load_mysql() -> tuple[str, int, str, str, str]:
    """
        读取 MySQL 连接参数。

        Returns:
            host, port, user, password, database

        Raises:
            RuntimeError: 未配置数据库
    """
    host = os.getenv("RADAR_DB_HOST", "").strip()
    port = int(os.getenv("RADAR_DB_PORT", "0") or "0")
    user = os.getenv("RADAR_DB_USER", "").strip()
    password = os.getenv("RADAR_DB_PASSWORD", "")
    db_name = os.getenv("RADAR_DB_NAME", "").strip()

    if not (host and user and db_name):
        from backend.app.config import settings

        if settings.is_exhibition_mysql_enabled:
            cfg = settings.require_exhibition_mysql()
            host = cfg["host"]
            port = int(cfg["port"])
            user = cfg["user"]
            password = cfg["password"]
            db_name = cfg["database"]

    if not (host and user and db_name):
        raise RuntimeError(
            "未配置 MySQL：请设置 RADAR_DB_* 或 EXHIBITION_MYSQL_HOST/USER/DB"
        )
    if port <= 0:
        port = 3306
    return host, port, user, password, db_name


def load_score_settings() -> ScoreSettings:
    """
        加载评分调度配置。

        Returns:
            已校验的配置

        Raises:
            RuntimeError: 缺少数据库或 Java 基址
    """
    host, port, user, password, db_name = _load_mysql()
    java_base = os.getenv("RADAR_SCORE_JAVA_BASE_URL", "").strip().rstrip("/")
    if not java_base:
        raise RuntimeError(
            "未配置 RADAR_SCORE_JAVA_BASE_URL（Java 服务根地址，"
            "用于 /admin-api/radar/*/score-prepare 与 score-complete）"
        )
    hostname = os.getenv("RADAR_SCORE_WORKER_HOST", "").strip() or socket.gethostname()
    pid = os.getpid()
    profile_concurrency = max(1, int(os.getenv("RADAR_SCORE_PROFILE_CONCURRENCY", "2") or "2"))
    event_concurrency = max(1, int(os.getenv("RADAR_SCORE_EVENT_CONCURRENCY", "2") or "2"))
    return ScoreSettings(
        db_host=host,
        db_port=port,
        db_user=user,
        db_password=password,
        db_name=db_name,
        tenant_id=_parse_optional_int(os.getenv("RADAR_TENANT_ID")),
        locked_by=build_locked_by(hostname, pid),
        java_base_url=java_base,
        java_token=os.getenv("RADAR_SCORE_JAVA_TOKEN", "").strip(),
        profile_concurrency=profile_concurrency,
        event_concurrency=event_concurrency,
        poll_interval_sec=float(os.getenv("RADAR_SCORE_POLL_INTERVAL_SEC", "15") or "15"),
        stale_timeout_sec=int(os.getenv("RADAR_SCORE_STALE_TIMEOUT_SEC", "2400") or "2400"),
        java_timeout_sec=float(os.getenv("RADAR_SCORE_JAVA_TIMEOUT_SEC", "60") or "60"),
        java_down_backoff_sec=float(os.getenv("RADAR_SCORE_JAVA_DOWN_BACKOFF_SEC", "60") or "60"),
        shutdown_wait_sec=float(os.getenv("RADAR_SCORE_SHUTDOWN_WAIT_SEC", "30") or "30"),
    )
