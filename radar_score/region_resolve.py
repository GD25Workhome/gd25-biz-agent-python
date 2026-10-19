"""
规则二 v3 事件「展厅所在区域」解析（M7 补充）。

背景：端到端落库改由 Python 直写 radar_event 后，旧 Java 落库路径
``RadarEventScorePersistService#applyRegion`` 的区域解析未随之迁移，
导致 radar_event.region_* 与 is_domestic 列长期为空，需求 13
「国内/国外 + 展厅所在区域」筛选实际无数据可筛。

本模块按与 Java 相同的口径补齐：
1. ``place`` 文本命中区域 → ``AI_PARSED``；
2. 否则继承企业默认城市 → ``COMPANY_INHERITED``；
3. 都解析不到 → 区域列留空、``region_source = UNKNOWN``。

解析算法对齐 Java ``RegionServiceImpl#resolveByText``，保证同一 place 在
新旧写入路径下得到同样的区域，不引入新的业务口径。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import pymysql

log = logging.getLogger("radar_score.region_resolve")

SOURCE_AI_PARSED = "AI_PARSED"
SOURCE_COMPANY_INHERITED = "COMPANY_INHERITED"
SOURCE_MANUAL = "MANUAL"
SOURCE_UNKNOWN = "UNKNOWN"

# region 表返回列：只取落库与返回所需字段
_REGION_FIELDS = (
    "id",
    "parent_id",
    "level",
    "name",
    "name_en",
    "full_name",
    "path_ids",
    "country_id",
    "country_code",
    "is_domestic",
)


def _bit_int(value: Any) -> Optional[int]:
    """
        MySQL bit(1) → 0/1（pymysql 对 bit 列返回 bytes）。

        Args:
            value: is_domestic 原始值

        Returns:
            0 / 1；无法判定时 None
    """
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return 1 if any(value) else 0
    return 1 if value in (1, True, "1", "b'\\x01'") else 0


def _pick_best(rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """
        同名区域优先取更细粒度（城市 > 省 > 国家），对齐 Java pickBest。

        Args:
            rows: 同名区域行

        Returns:
            最细粒度的一行；空列表返回 None
    """
    if not rows:
        return None
    return sorted(rows, key=lambda r: -(int(r.get("level") or 0)))[0]


def _query_region_by_id(conn: pymysql.Connection, region_id: Any) -> Optional[dict[str, Any]]:
    """按 region.id 取一行（含祖先链），供企业区域继承使用。"""
    if region_id in (None, ""):
        return None
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(_REGION_FIELDS)} FROM region WHERE id = %s AND deleted = b'0'",
            [region_id],
        )
        return cur.fetchone()


def _query_region_by_sql(conn: pymysql.Connection, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    """执行一条 region 查询并返回全部行。"""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall() or [])


def _query_alias_region_ids(conn: pymysql.Connection, sql: str, params: list[Any]) -> list[Any]:
    """执行一条 region_alias 查询并返回 region_id 列表。"""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [r.get("region_id") for r in cur.fetchall() or []]


def resolve_region_by_text(conn: pymysql.Connection, text: Any) -> Optional[dict[str, Any]]:
    """
        文本 → 区域（名称 / 别名 / 编码），对齐 Java resolveByText 的顺序。

        Args:
            conn: 数据库连接
            text: 待解析文本，如「郑州」「美国旧金山」

        Returns:
            区域行（含 full_name / path_ids / country_id / is_domestic）；未命中 None
    """
    kw = str(text or "").strip()
    if not kw:
        return None
    # 1. 编码精确
    rows = _query_region_by_sql(
        conn,
        f"SELECT {', '.join(_REGION_FIELDS)} FROM region WHERE code = %s AND deleted = b'0'",
        [kw],
    )
    if rows:
        return rows[0]
    # 2. 名称精确（同名取更细粒度）
    rows = _query_region_by_sql(
        conn,
        f"SELECT {', '.join(_REGION_FIELDS)} FROM region WHERE name = %s AND deleted = b'0'",
        [kw],
    )
    best = _pick_best(rows)
    if best is not None:
        return best
    # 3. 别名精确
    alias_region_ids = _query_alias_region_ids(
        conn,
        "SELECT region_id FROM region_alias WHERE alias = %s AND deleted = b'0'",
        [kw],
    )
    if alias_region_ids:
        region = _query_region_by_id(conn, alias_region_ids[0])
        if region is not None:
            return region
    # 4. 名称模糊
    rows = _query_region_by_sql(
        conn,
        f"SELECT {', '.join(_REGION_FIELDS)} FROM region "
        "WHERE name LIKE %s AND deleted = b'0' LIMIT 1",
        [f"%{kw}%"],
    )
    if rows:
        return rows[0]
    # 5. 别名模糊
    alias_region_ids = _query_alias_region_ids(
        conn,
        "SELECT region_id FROM region_alias WHERE alias LIKE %s AND deleted = b'0' LIMIT 1",
        [f"%{kw}%"],
    )
    if alias_region_ids:
        return _query_region_by_id(conn, alias_region_ids[0])
    return None


def resolve_company_region(conn: pymysql.Connection, company: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
        企业默认城市：region_id 优先，其次企业地区文本，对齐 Java resolveCompanyRegion。

        Args:
            conn: 数据库连接
            company: radar_company 行

        Returns:
            区域行；企业无区域信息时 None
    """
    region = _query_region_by_id(conn, company.get("region_id"))
    if region is not None:
        return region
    return resolve_region_by_text(conn, company.get("region"))


def _to_columns(region: Optional[dict[str, Any]], source: str) -> dict[str, Any]:
    """
        区域行 → radar_event 区域列字典。

        Args:
            region: 区域行（None 表示未解析到）
            source: 区域来源枚举值

        Returns:
            region_id / region_name / region_path_ids / country_id / is_domestic / region_source
    """
    if region is None:
        return {
            "region_id": None,
            "region_name": None,
            "region_path_ids": None,
            "country_id": None,
            "is_domestic": None,
            "region_source": source,
        }
    return {
        "region_id": region.get("id"),
        "region_name": region.get("full_name"),
        "region_path_ids": region.get("path_ids"),
        "country_id": region.get("country_id"),
        "is_domestic": _bit_int(region.get("is_domestic")),
        "region_source": source,
    }


def resolve_event_region(
    conn: pymysql.Connection,
    place: Any,
    company: dict[str, Any],
    *,
    place_region_id: Any = None,
) -> dict[str, Any]:
    """
        解析事件的展厅所在区域并生成落库列。

        口径（优先级）：
        0. Agent 用区域字典工具确定的 `place_region_id` 命中 → AI_PARSED；
        1. `place` 文本命中区域 → AI_PARSED；
        2. 否则继承企业默认城市 → COMPANY_INHERITED；
        3. 都解析不到 → 区域列留空、`region_source = UNKNOWN`。

        Args:
            conn: 数据库连接
            place: 事件地点（radar_event.place）
            company: radar_company 行
            place_region_id: Agent 查字典得到的 region.id（可选，优先采用）

        Returns:
            可直接并入 radar_event 写入列的区域字典
    """
    by_id = _query_region_by_id(conn, place_region_id)
    if by_id is not None:
        return _to_columns(by_id, SOURCE_AI_PARSED)
    region = resolve_region_by_text(conn, place)
    if region is not None:
        return _to_columns(region, SOURCE_AI_PARSED)
    region = resolve_company_region(conn, company)
    if region is not None:
        return _to_columns(region, SOURCE_COMPANY_INHERITED)
    return _to_columns(None, SOURCE_UNKNOWN)