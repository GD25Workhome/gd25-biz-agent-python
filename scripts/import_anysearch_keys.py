#!/usr/bin/env python
"""把 AnySearch key 批量导入 `radar_anysearch_key`。

来源（可组合，按 key 的 sha1 去重）：
  1) JSON 账号文件（`--json` 指定；默认 `anysearch_keys.json`。原
     `华院Agent设计/261016-测试/01-邮箱和key/` 已随文档清理删除）
     —— 取 `accounts[].api_key.key`；
  2) 当前 `.env` 的 `ANY_SEARCH_API_KEYS` / `ANY_SEARCH_API_KEY` / `ANYSEARCH_API_KEY`。

行为：幂等（`uk_key_hash` 命中则跳过）。**不打印完整 key**。

用法（仓库根目录）：
    python scripts/import_anysearch_keys.py --dry-run
    python scripts/import_anysearch_keys.py
    python scripts/import_anysearch_keys.py --json <path> --no-env --pool-tag dev
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql  # noqa: E402

from backend.app.config import settings  # noqa: E402

_DEFAULT_JSON = "anysearch_keys.json"
_TABLE = "radar_anysearch_key"


def sha1_hex(text: str) -> str:
    """key 的 sha1（唯一键）。"""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def key_label(seq: int, key: str) -> str:
    """日志标识：#序号 …末4位。"""
    tail = key[-4:] if len(key) >= 4 else "****"
    return f"#{seq}…{tail}"


def load_from_json(path: str) -> List[Tuple[str, str]]:
    """
        从账号 JSON 读取 (key, source_note)。

        Args:
            path: JSON 路径

        Returns:
            列表；文件不存在返回空
    """
    p = Path(path)
    if not p.exists():
        print(f"  [warn] JSON 不存在，跳过: {path}")
        return []
    obj = json.loads(p.read_text(encoding="utf-8"))
    accounts = obj.get("accounts") if isinstance(obj, dict) else None
    if not isinstance(accounts, list):
        print("  [warn] JSON 无 accounts[]，跳过")
        return []
    out: List[Tuple[str, str]] = []
    for acc in accounts:
        if not isinstance(acc, dict) or not acc.get("ok", True):
            continue
        api = acc.get("api_key") if isinstance(acc.get("api_key"), dict) else {}
        key = str(api.get("key") or "").strip()
        if not key:
            continue
        user = ""
        as_ = acc.get("anysearch") if isinstance(acc.get("anysearch"), dict) else {}
        user = str(as_.get("username") or "").strip()
        note = f"json#{acc.get('index')} {user}"[:128]
        out.append((key, note))
    return out


def load_from_env() -> List[Tuple[str, str]]:
    """
        从 `.env`（经 settings）读取 key。

        Returns:
        (key, source_note) 列表
    """
    out: List[Tuple[str, str]] = []
    multi = getattr(settings, "ANY_SEARCH_API_KEYS", None) or ""
    for k in str(multi).split(","):
        k = k.strip()
        if k:
            out.append((k, "env:ANY_SEARCH_API_KEYS"))
    for name in ("ANY_SEARCH_API_KEY", "ANYSEARCH_API_KEY"):
        val = getattr(settings, name, None)
        if val and str(val).strip():
            out.append((str(val).strip(), f"env:{name}"))
    return out


def dedup(pairs: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """按 key 去重，保留首个 source_note。"""
    seen = set()
    out: List[Tuple[str, str]] = []
    for key, note in pairs:
        h = sha1_hex(key)
        if h in seen:
            continue
        seen.add(h)
        out.append((key, note))
    return out


def connect() -> pymysql.connections.Connection:
    """按 settings 连 exhibition MySQL。"""
    cfg = settings.require_exhibition_mysql()
    return pymysql.connect(
        host=cfg["host"], port=int(cfg["port"]), user=cfg["user"],
        password=cfg["password"], database=cfg["database"],
        charset="utf8mb4", autocommit=False,
    )


def main() -> int:
    """入口。"""
    ap = argparse.ArgumentParser(description="导入 AnySearch key 到 radar_anysearch_key")
    ap.add_argument("--json", default=_DEFAULT_JSON, help="账号 JSON 路径")
    ap.add_argument("--no-env", action="store_true", help="不导入 .env 的 key")
    ap.add_argument("--pool-tag", default="shared", help="pool_tag（默认 shared）")
    ap.add_argument("--daily-quota", type=int, default=1000, help="单 key 日额度（默认 1000）")
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    args = ap.parse_args()

    pairs: List[Tuple[str, str]] = list(load_from_json(args.json))
    if not args.no_env:
        pairs += load_from_env()
    pairs = dedup(pairs)
    print(f"待导入（去重后）: {len(pairs)} 把 "
          f"(json={len(load_from_json(args.json))}, env={'no' if args.no_env else 'yes'})")

    if args.dry_run:
        for i, (k, note) in enumerate(pairs[:3], 1):
            print(f"  sample {key_label(i, k)}  note={note}")
        print("dry-run：未写库")
        return 0

    conn = connect()
    cur = conn.cursor()
    inserted = skipped = 0
    sql = (
        f"INSERT INTO {_TABLE} "
        "(key_value, key_hash, key_label, source_note, pool_tag, enabled, health, "
        " used_today, daily_quota, creator, updater) "
        "VALUES (%s, %s, %s, %s, %s, 1, 'available', 0, %s, 'import_anysearch_keys', 'import_anysearch_keys') "
        "ON DUPLICATE KEY UPDATE update_time=NOW()"
    )
    for i, (key, note) in enumerate(pairs, 1):
        try:
            cur.execute(sql, [
                key, sha1_hex(key), key_label(i, key), note, args.pool_tag, args.daily_quota,
            ])
            # ON DUPLICATE 时 rowcount 为 0（无变化）或 2（有变化）；新插入为 1
            if cur.rowcount == 1:
                inserted += 1
            else:
                skipped += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  [err] {key_label(i, key)}: {type(exc).__name__}: {exc}")
    conn.commit()
    cur.execute(f"SELECT COUNT(*) FROM {_TABLE} WHERE deleted=b'0'")
    total = cur.fetchone()[0]
    conn.close()
    print(f"完成：新增 {inserted}，已存在/跳过 {skipped}；表内共 {total} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())