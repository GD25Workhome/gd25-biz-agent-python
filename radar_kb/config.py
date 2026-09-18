"""
radar_kb 运行配置：数据库优先 RADAR_DB_*，否则回退 exhibition MySQL（settings）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env", override=False)


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


@dataclass(frozen=True)
class KbSettings:
    """知识库调度器配置。"""

    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    tenant_id: Optional[int]
    worker_id: str
    poll_interval_sec: float
    # 统一单 loop：发现后短休 / 正文后长休 / 空闲休（秒）
    poll_after_discover_sec: float
    poll_after_content_sec: float
    poll_idle_sec: float
    # 某类任务查表为空后，至少间隔这么久再查该类（秒）
    empty_backoff_sec: float
    # 正文 Frontier：批量认领与同站间隔
    content_claim_batch: int
    content_claim_per_key: int
    content_polite_key: str
    content_same_key_gap_min_sec: float
    content_same_key_gap_max_sec: float
    content_site_min_interval_sec: float
    crawl_stale_timeout_sec: int
    content_text_max_chars: int
    summary_max_chars: int
    pdf_max_pages: int
    cninfo_page_size: int
    cninfo_max_pages: int
    request_interval_sec: float
    cninfo_request_interval_sec: float
    cninfo_request_jitter_sec: float


def load_kb_settings() -> KbSettings:
    """
    加载 MySQL 与 worker 参数。

    优先环境变量 RADAR_DB_*；未配置时读取 backend.app.settings 的 EXHIBITION_MYSQL_*。
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

    # 巨潮节奏：独立环境变量优先；未设时回退旧 RADAR_REQUEST_INTERVAL_SEC，再默认 5
    cninfo_interval_raw = os.getenv("RADAR_CNINFO_REQUEST_INTERVAL_SEC")
    if cninfo_interval_raw is None or str(cninfo_interval_raw).strip() == "":
        cninfo_interval_raw = os.getenv("RADAR_REQUEST_INTERVAL_SEC", "5")
    cninfo_request_interval_sec = float(cninfo_interval_raw or "5")
    cninfo_request_jitter_sec = float(
        os.getenv("RADAR_CNINFO_REQUEST_JITTER_SEC", "4") or "4"
    )

    # 同步到适配器（进程级限速 + Session 锁）
    from radar_crawl.adapters import cninfo as cninfo_adapter

    cninfo_adapter.configure_request_pace(
        cninfo_request_interval_sec,
        cninfo_request_jitter_sec,
    )

    # 空闲/兼容旧配置：RADAR_KB_POLL_INTERVAL_SEC 仍作默认空闲与正文后休息
    poll_interval_sec = float(os.getenv("RADAR_KB_POLL_INTERVAL_SEC", "10"))
    poll_after_discover_sec = float(
        os.getenv("RADAR_KB_POLL_AFTER_DISCOVER_SEC", "2") or "2"
    )
    poll_after_content_sec = float(
        os.getenv("RADAR_KB_POLL_AFTER_CONTENT_SEC", str(poll_interval_sec))
        or str(poll_interval_sec)
    )
    poll_idle_sec = float(
        os.getenv("RADAR_KB_POLL_IDLE_SEC", str(poll_interval_sec))
        or str(poll_interval_sec)
    )
    empty_backoff_sec = float(
        os.getenv("RADAR_KB_EMPTY_BACKOFF_SEC", "60") or "60"
    )
    content_claim_batch = int(os.getenv("RADAR_KB_CONTENT_CLAIM_BATCH", "200") or "200")
    content_claim_per_key = int(
        os.getenv("RADAR_KB_CONTENT_CLAIM_PER_KEY", "3") or "3"
    )
    content_polite_key = (
        os.getenv("RADAR_KB_CONTENT_POLITE_KEY", "source_url_id") or "source_url_id"
    ).strip().lower()
    if content_polite_key not in ("source_url_id", "host", "company_id"):
        content_polite_key = "source_url_id"
    content_same_key_gap_min_sec = float(
        os.getenv("RADAR_KB_CONTENT_SAME_KEY_GAP_MIN_SEC", "5") or "5"
    )
    content_same_key_gap_max_sec = float(
        os.getenv("RADAR_KB_CONTENT_SAME_KEY_GAP_MAX_SEC", "10") or "10"
    )
    # 与 NEWS_CONTENT 同站间隔对齐；未设时读 backend settings
    site_min_raw = os.getenv("RADAR_KB_CONTENT_SITE_MIN_INTERVAL_SEC")
    if site_min_raw is None or str(site_min_raw).strip() == "":
        try:
            from backend.app.config import settings as app_settings

            content_site_min_interval_sec = float(
                app_settings.NEWS_CONTENT_SITE_MIN_INTERVAL_SECONDS
            )
        except Exception:
            content_site_min_interval_sec = 2.0
    else:
        content_site_min_interval_sec = float(site_min_raw)
    crawl_stale_timeout_sec = int(
        os.getenv("RADAR_KB_CRAWL_STALE_TIMEOUT_SEC", "1800") or "1800"
    )

    return KbSettings(
        db_host=host,
        db_port=port,
        db_user=user,
        db_password=password,
        db_name=db_name,
        tenant_id=_parse_optional_int(os.getenv("RADAR_TENANT_ID")),
        worker_id=os.getenv("RADAR_KB_WORKER_ID", f"py-kb-{os.getpid()}"),
        poll_interval_sec=poll_interval_sec,
        poll_after_discover_sec=poll_after_discover_sec,
        poll_after_content_sec=poll_after_content_sec,
        poll_idle_sec=poll_idle_sec,
        empty_backoff_sec=empty_backoff_sec,
        content_claim_batch=content_claim_batch,
        content_claim_per_key=content_claim_per_key,
        content_polite_key=content_polite_key,
        content_same_key_gap_min_sec=content_same_key_gap_min_sec,
        content_same_key_gap_max_sec=content_same_key_gap_max_sec,
        content_site_min_interval_sec=content_site_min_interval_sec,
        crawl_stale_timeout_sec=crawl_stale_timeout_sec,
        content_text_max_chars=int(os.getenv("RADAR_CONTENT_TEXT_MAX_CHARS", "500000")),
        summary_max_chars=int(os.getenv("RADAR_SUMMARY_MAX_CHARS", "500")),
        pdf_max_pages=int(os.getenv("RADAR_PDF_MAX_PAGES", "80")),
        cninfo_page_size=int(os.getenv("RADAR_CNINFO_PAGE_SIZE", "30")),
        cninfo_max_pages=int(os.getenv("RADAR_CNINFO_MAX_PAGES", "3")),
        request_interval_sec=cninfo_request_interval_sec,
        cninfo_request_interval_sec=cninfo_request_interval_sec,
        cninfo_request_jitter_sec=cninfo_request_jitter_sec,
    )


def is_legacy_crawl_disabled() -> bool:
    """RADAR_KB_UNIFIED=1（默认）时 legacy radar_crawl worker 应退出。"""
    return _parse_bool(os.getenv("RADAR_KB_UNIFIED"), True)


def is_radar_kb_in_app_enabled() -> bool:
    """
    是否在 FastAPI 内挂载 radar_kb（L2）。

    环境变量 RADAR_KB_WORKER_IN_APP，默认 true。
    """
    return _parse_bool(os.getenv("RADAR_KB_WORKER_IN_APP"), True)
