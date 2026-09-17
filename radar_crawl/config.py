"""
采集 Worker 运行配置。

通过环境变量 / .env 注入数据库与限速参数，避免把密码写进仓库。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def _load_env_files() -> None:
    """
        按优先级加载 .env：仓库根 → radar_crawl 目录（后者不覆盖已有键）。
    """
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    # 1. 仓库根 .env（与华院 API 共用本机配置文件时方便）
    load_dotenv(repo_root / ".env", override=False)
    # 2. 采集专用 .env
    load_dotenv(here / ".env", override=True)


_load_env_files()


@dataclass(frozen=True)
class Settings:
    """Worker 配置项。"""

    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    # None 表示开发期不按租户过滤；上生产多租户时再配置 RADAR_TENANT_ID
    tenant_id: Optional[int]
    poll_interval_sec: float
    request_interval_sec: float
    worker_id: str
    cninfo_fetch_pdf: bool
    cninfo_page_size: int
    cninfo_max_pages: int
    content_text_max_chars: int
    summary_max_chars: int
    # 单份 PDF 最多抽取页数，避免超大年报拖垮 worker
    pdf_max_pages: int
    # 阶段 B
    pdf_concurrency: int
    pdf_batch_size: int
    pdf_poll_interval_sec: float
    pdf_lock_timeout_sec: float


def _parse_optional_int(raw: Optional[str]) -> Optional[int]:
    """空字符串 / 未配置 → None；否则解析为 int。"""
    if raw is None:
        return None
    text = raw.strip()
    if text == "":
        return None
    return int(text)


def _parse_bool(raw: Optional[str], default: bool) -> bool:
    """
        解析开关类环境变量。

        空/未配置 → default；
        真：1/true/yes/on/y；假：0/false/no/off/n。
    """
    if raw is None:
        return default
    text = raw.strip().lower()
    if text == "":
        return default
    if text in ("1", "true", "yes", "on", "y"):
        return True
    if text in ("0", "false", "no", "off", "n"):
        return False
    return default


def load_settings() -> Settings:
    """从环境变量加载配置。"""
    # 巨潮 HTTP 节奏：与 radar_kb 共用适配器内限速（默认 5s + 0～4s 抖动）
    cninfo_interval = float(
        os.getenv(
            "RADAR_CNINFO_REQUEST_INTERVAL_SEC",
            os.getenv("RADAR_REQUEST_INTERVAL_SEC", "5"),
        )
        or "5"
    )
    cninfo_jitter = float(os.getenv("RADAR_CNINFO_REQUEST_JITTER_SEC", "4") or "4")
    from radar_crawl.adapters import cninfo as cninfo_adapter

    cninfo_adapter.configure_request_pace(cninfo_interval, cninfo_jitter)

    return Settings(
        db_host=os.getenv("RADAR_DB_HOST", "127.0.0.1"),
        db_port=int(os.getenv("RADAR_DB_PORT", "3306")),
        db_user=os.getenv("RADAR_DB_USER", "root"),
        db_password=os.getenv("RADAR_DB_PASSWORD", ""),
        db_name=os.getenv("RADAR_DB_NAME", "unidt_exhibition"),
        tenant_id=_parse_optional_int(os.getenv("RADAR_TENANT_ID")),
        poll_interval_sec=float(os.getenv("RADAR_POLL_INTERVAL_SEC", "60")),
        # 遗留 worker 任务间 sleep；真实 HTTP 间隔以 cninfo 适配器为准
        request_interval_sec=cninfo_interval,
        worker_id=os.getenv("RADAR_WORKER_ID", f"py-{os.getpid()}"),
        # 默认开启 PDF 正文抽取（由阶段 B worker 执行）
        cninfo_fetch_pdf=_parse_bool(os.getenv("RADAR_CNINFO_FETCH_PDF"), True),
        cninfo_page_size=int(os.getenv("RADAR_CNINFO_PAGE_SIZE", "30")),
        cninfo_max_pages=int(os.getenv("RADAR_CNINFO_MAX_PAGES", "3")),
        content_text_max_chars=int(os.getenv("RADAR_CONTENT_TEXT_MAX_CHARS", "500000")),
        summary_max_chars=int(os.getenv("RADAR_SUMMARY_MAX_CHARS", "500")),
        pdf_max_pages=int(os.getenv("RADAR_PDF_MAX_PAGES", "80")),
        pdf_concurrency=int(os.getenv("RADAR_PDF_CONCURRENCY", "3")),
        pdf_batch_size=int(os.getenv("RADAR_PDF_BATCH_SIZE", "20")),
        pdf_poll_interval_sec=float(os.getenv("RADAR_PDF_POLL_INTERVAL_SEC", "5")),
        pdf_lock_timeout_sec=float(os.getenv("RADAR_PDF_LOCK_TIMEOUT_SEC", "1800")),
    )
