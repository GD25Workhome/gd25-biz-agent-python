#!/usr/bin/env python3
"""
删除并重建雷达新闻 chunk Milvus collection（含 content_grade / source_kind 标量）。

用法（仓库根目录）：
    /opt/anaconda3/envs/py311_GD25_base/bin/python scripts/rebuild_radar_milvus_collection.py

依赖 .env 中的 MILVUS_* 与 MILVUS_COLLECTION（默认 radar_company_news_chunk）。
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
log = logging.getLogger("rebuild_milvus")


def main() -> int:
    """执行 drop + ensure_collection。"""
    from backend.infrastructure.milvus.radar_news_chunk_store import RadarNewsChunkStore

    store = RadarNewsChunkStore()
    if not store.is_configured:
        log.error("Milvus 未配置，请在 .env 设置 MILVUS_URI 与凭证")
        return 1
    try:
        created = store.rebuild_collection(drop=True)
        info = store.describe()
        log.info(
            "重建完成 collection=%s created=%s schema_ok=%s row_count=%s",
            info.get("collection"),
            created,
            info.get("schema_ok"),
            info.get("row_count"),
        )
        return 0
    except Exception as exc:
        log.exception("重建失败: %s", exc)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
