"""区域字典查询工具（规则二 v3「展厅所在区域」用）。

目标：给「展厅需求评分」Agent 一个**查行政区划字典**的工具，让它在确定
「展厅所在区域」时逐级查询（省 → 市 → 区/县），而不是凭记忆写行政区划。

数据来源：exhibition 库 `region` / `region_alias` 两张字典表（**只读**）。
口径与 `radar_score.region_resolve`（对齐 Java `RegionServiceImpl#resolveByText`）一致，
Agent 命中的 `region.id` 可直接被落库链路复用（`place_region_id`）。

层级：1=国家、2=省/直辖市、3=市、4=区/县（`path_ids` 形如 `1/110000/110100/110105`）。

⚠️ 本模块不复用 `backend.infrastructure.database.mysql_connection`（该模块的访问边界
只允许 radar_news_content_task / radar_company_news_document / radar_news_agent_guard
三张表）；这里自建只读连接，不改库、不写库。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Sequence

import pymysql
from pymysql.cursors import DictCursor

from backend.app.config import settings
from backend.domain.tools.decorator import register_tool

logger = logging.getLogger(__name__)

# region 返回列（与 radar_score.region_resolve._REGION_FIELDS 对齐 + code）
_FIELDS = "id, parent_id, level, name, full_name, path_ids, code, country_id, is_domestic"
# JOIN 查询需要带表别名，避免 id/deleted 等列名歧义
_FIELDS_R = (
    "r.id, r.parent_id, r.level, r.name, r.full_name, r.path_ids, r.code, "
    "r.country_id, r.is_domestic"
)

_LIMIT_MAX = 50
_NOT_DELETED = "deleted = b'0'"


def _error_payload(message: str, **extra: Any) -> str:
    """将错误信息序列化为工具 Observation JSON 字符串。"""
    payload: Dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _bit_int(value: Any) -> Optional[int]:
    """MySQL bit(1) → 0/1（pymysql 对 bit 列返回 bytes）。"""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return 1 if any(value) else 0
    return 1 if value in (1, True, "1") else 0


def _fetch_all(sql: str, params: Sequence[Any] | None = None) -> List[Dict[str, Any]]:
    """
        自建只读连接执行 SELECT（同步，调用方丢线程池）。

        Args:
            sql: SELECT 语句
            params: 参数

        Returns:
            行列表（DictCursor）

        Raises:
            RuntimeError: 未配置 exhibition MySQL
    """
    cfg = settings.require_exhibition_mysql()
    conn = pymysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        charset=cfg.get("charset", "utf8mb4"),
        connect_timeout=int(cfg.get("connect_timeout", 10)),
        cursorclass=DictCursor,
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql, list(params or []))
            return list(cur.fetchall() or [])
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _norm_limit(limit: Any) -> int:
    """条数收敛到 1–50。"""
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 10
    if n <= 0:
        n = 10
    return max(1, min(_LIMIT_MAX, n))


def _to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    """region 行 → 工具输出结构。"""
    return {
        "id": int(row["id"]),
        "name": row.get("name"),
        "full_name": row.get("full_name"),
        "level": int(row.get("level") or 0),
        "parent_id": row.get("parent_id"),
        "path_ids": row.get("path_ids"),
        "code": row.get("code"),
        "country_id": row.get("country_id"),
        "is_domestic": _bit_int(row.get("is_domestic")),
    }


def _search_sync(keyword: str, parent: str, limit: int) -> List[Dict[str, Any]]:
    """
        字典检索（名称/编码/别名；可选按上级过滤）。

        顺序：编码精确 → 名称精确 → 别名精确 → 名称模糊 → 别名模糊；
        同名取更细粒度（level 大者优先）。

        Args:
            keyword: 地名关键词
            parent: 上级地名/编码（用于同名消歧，可空）
            limit: 返回条数上限

        Returns:
            region 行列表（原始 dict）
    """
    kw = keyword.strip()
    found: List[Dict[str, Any]] = []
    seen: set[int] = set()

    def _add(rows: List[Dict[str, Any]]) -> None:
        for row in rows:
            rid = int(row["id"])
            if rid not in seen:
                seen.add(rid)
                found.append(row)

    if kw.isdigit():
        _add(_fetch_all(f"SELECT {_FIELDS} FROM region WHERE code = %s AND {_NOT_DELETED}", [kw]))
    _add(
        _fetch_all(
            f"SELECT {_FIELDS} FROM region WHERE name = %s AND {_NOT_DELETED} ORDER BY level DESC",
            [kw],
        )
    )
    _add(
        _fetch_all(
            f"SELECT {_FIELDS_R} FROM region r JOIN region_alias a ON a.region_id = r.id "
            f"WHERE a.alias = %s AND a.{_NOT_DELETED} AND r.{_NOT_DELETED} ORDER BY r.level DESC",
            [kw],
        )
    )
    _add(
        _fetch_all(
            f"SELECT {_FIELDS} FROM region WHERE name LIKE %s AND {_NOT_DELETED} "
            "ORDER BY level DESC, id LIMIT %s",
            [f"%{kw}%", limit],
        )
    )
    _add(
        _fetch_all(
            f"SELECT {_FIELDS_R} FROM region r JOIN region_alias a ON a.region_id = r.id "
            f"WHERE a.alias LIKE %s AND a.{_NOT_DELETED} AND r.{_NOT_DELETED} "
            "ORDER BY r.level DESC, r.id LIMIT %s",
            [f"%{kw}%", limit],
        )
    )

    if parent and parent.strip():
        parent_rows = _search_sync(parent.strip(), "", 5)
        parent_ids = {str(int(r["id"])) for r in parent_rows}
        if parent_ids:
            filtered: List[Dict[str, Any]] = []
            for row in found:
                chain = str(row.get("path_ids") or "").split("/")
                if parent_ids & set(chain):
                    filtered.append(row)
            found = filtered
        else:
            found = []

    found.sort(key=lambda r: (-int(r.get("level") or 0), int(r["id"])))
    return found[:limit]


def _resolve_one_sync(region: str) -> List[Dict[str, Any]]:
    """把 region（编码/名称/别名）解析成候选行（用于 children 下钻）。"""
    return _search_sync(region, "", _LIMIT_MAX)


@register_tool
async def region_lookup(keyword: str, parent: str = "", limit: int = 10) -> str:
    """
    查询行政区划字典（唯一可信的区域来源）：按名称 / 行政区划编码 / 别名检索地区。

    用于确定「展厅所在区域」时逐级查询（省/直辖市 → 市 → 区/县）。**禁止凭记忆写行政区划**。
    同名地区（如"朝阳区"北京/长春各有一个）用 `parent` 传上级消歧。

    Args:
        keyword: 地名关键词，如 "北京"、"北京市"、"朝阳区"、"110105"
        parent: 上级地名或编码（可选；同名消歧用），如 parent="北京市"
        limit: 返回条数上限，1–50，默认 10

    Returns:
        JSON 字符串：{ok, query, parent, count, results:[{id,name,full_name,level,
        parent_id,path_ids,code,country_id,is_domestic}], note}
        level：1=国家、2=省/直辖市、3=市、4=区/县；is_domestic：1=国内、0=国外。
    """
    kw = str(keyword or "").strip()
    if not kw:
        return _error_payload("keyword 为空", tool_name="region_lookup")
    try:
        rows = await asyncio.to_thread(_search_sync, kw, str(parent or ""), _norm_limit(limit))
    except RuntimeError as exc:
        return _error_payload(str(exc), tool_name="region_lookup", query=kw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("region_lookup 查询失败: %s: %s", type(exc).__name__, exc)
        return _error_payload(f"区域字典查询失败：{type(exc).__name__}", tool_name="region_lookup", query=kw)

    results = [_to_dict(r) for r in rows]
    note = "同名地区请用 parent 指定上级确认；确定后把命中的 id 写入输出 place_region_id"
    if not results:
        note = "未命中；可换用全称/编码，或先查上级再 region_children 下钻。查不到请留空，禁止编造"
    return json.dumps(
        {
            "ok": True,
            "query": kw,
            "parent": str(parent or ""),
            "count": len(results),
            "results": results,
            "note": note,
        },
        ensure_ascii=False,
    )


@register_tool
async def region_children(region: str, limit: int = 50) -> str:
    """
    列出某地区的下一级行政区（用于逐级下钻：市 → 区/县）。

    Args:
        region: 地区 id 或名称/编码，如 "110100" 或 "北京市"
        limit: 返回条数上限，1–50，默认 50

    Returns:
        JSON 字符串：{ok, region:{...}, ambiguous, candidates, count, results:[...]}
        名称重名（多个候选）时 ambiguous=true 并返回 candidates，请改用 region id 再查。
    """
    key = str(region or "").strip()
    if not key:
        return _error_payload("region 为空", tool_name="region_children")
    try:
        parents = await asyncio.to_thread(_resolve_one_sync, key)
    except RuntimeError as exc:
        return _error_payload(str(exc), tool_name="region_children", region=key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("region_children 解析失败: %s: %s", type(exc).__name__, exc)
        return _error_payload(f"区域字典查询失败：{type(exc).__name__}", tool_name="region_children", region=key)

    if not parents:
        return _error_payload("未找到该地区", tool_name="region_children", region=key)

    # 同名多候选 → 先让调用方用 id 消歧
    distinct_ids = {int(r["id"]) for r in parents}
    if len(distinct_ids) > 1 and not key.isdigit():
        return json.dumps(
            {
                "ok": True,
                "region": None,
                "ambiguous": True,
                "candidates": [_to_dict(r) for r in parents],
                "count": 0,
                "note": "名称重名，请用候选 id 重新调用 region_children",
            },
            ensure_ascii=False,
        )

    parent_row = parents[0]
    pid = int(parent_row["id"])
    try:
        children = await asyncio.to_thread(
            _fetch_all,
            f"SELECT {_FIELDS} FROM region WHERE parent_id = %s AND {_NOT_DELETED} "
            "ORDER BY id LIMIT %s",
            [pid, _norm_limit(limit)],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("region_children 子级查询失败: %s: %s", type(exc).__name__, exc)
        return _error_payload(f"区域字典查询失败：{type(exc).__name__}", tool_name="region_children", region=key)

    return json.dumps(
        {
            "ok": True,
            "region": _to_dict(parent_row),
            "ambiguous": False,
            "candidates": [],
            "count": len(children),
            "results": [_to_dict(r) for r in children],
            "note": "选中区/县后把其 id 写入输出 place_region_id",
        },
        ensure_ascii=False,
    )


__all__ = ["region_lookup", "region_children"]