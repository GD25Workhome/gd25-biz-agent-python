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
import re
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


# ---------------------------------------------------------------- 分段切分（B 代码兜底，261020）

# 行政区后缀（**长的在前**，按长度降序匹配，避免"自治区"被"区"抢先切）
_ADMIN_SUFFIXES = tuple(
    sorted(
        [
            "特别行政区",
            "维吾尔自治区",
            "回族自治区",
            "壮族自治区",
            "自治区",
            "自治州",
            "自治县",
            "经济技术开发区",
            "开发区",
            "经开区",
            "高新区",
            "新区",
            "省",
            "市",
            "区",
            "县",
            "旗",
            "盟",
            "州",
        ],
        key=len,
        reverse=True,
    )
)

# 需要提示"解析可疑"的细粒度后缀（落到继承企业时用）
_DISTRICT_TOKENS = ("区", "县", "旗", "盟")

# 需要从 place 里剥掉的噪声
_PLACE_NOISE = re.compile(r"(附近|周边|旁边|一带|所在|地址|位于|坐落于)")


def _clean_place(text: Any) -> str:
    """
        清洗 place：去括号内容、方位/道路等噪声词、首尾分隔符。

        Args:
            text: 原始地点文本

        Returns:
            清洗后的文本（可能为空）
    """
    t = str(text or "").strip()
    if not t:
        return ""
    t = re.sub(r"[（(【\[].*?[)）】\]]", "", t)
    t = _PLACE_NOISE.sub("", t)
    return t.strip(" ·、,，/｜|>-—")


def _split_place_candidates(text: Any) -> list[str]:
    """
        把地点文本按行政区后缀切成候选，**从最细到最粗**返回。

        `"北京市朝阳区"` → `["朝阳区", "北京市"]`；
        `"重庆经开区东港片区（广滨三路）"` → `["东港片区", "重庆经开区"]`；
        无后缀/国外串 → 单候选（交给整串/国家前缀兜）。

        Args:
            text: 原始地点文本

        Returns:
            候选列表（最细在前）；无有效候选时为空列表
    """
    t = _clean_place(text)
    if not t:
        return []
    segs: list[str] = []
    start = 0
    i = 0
    n = len(t)
    while i < n:
        hit = next((suf for suf in _ADMIN_SUFFIXES if t.startswith(suf, i)), None)
        if hit:
            end = i + len(hit)
            seg = t[start:end].strip()
            if len(seg) >= 2:
                segs.append(seg)
            start = end
            i = end
        else:
            i += 1
    tail = t[start:].strip()
    if len(tail) >= 2:
        segs.append(tail)
    # 扫描得到的是"从粗到细"，反转成"从细到粗"并去重
    out: list[str] = []
    for seg in reversed(segs):
        if seg not in out:
            out.append(seg)
    return out


def _filter_by_parents(
    conn: pymysql.Connection, rows: list[dict[str, Any]], parents: list[str]
) -> list[dict[str, Any]]:
    """
        同名地区消歧：保留**父级名称命中 `parents`** 的行（如"朝阳区"限定在"北京市"下）。

        Args:
            conn: 数据库连接
            rows: 同名候选行
            parents: 更粗的候选片段（如 ["北京市"]）

        Returns:
            过滤后的行；无法判定时返回空列表（由调用方决定是否放宽）
    """
    if not parents:
        return rows
    keep: list[dict[str, Any]] = []
    for row in rows:
        parent = _query_region_by_id(conn, row.get("parent_id"))
        if parent is None:
            continue
        pname = str(parent.get("name") or "")
        pfull = str(parent.get("full_name") or "")
        if any(p and (p in pname or p in pfull) for p in parents):
            keep.append(row)
    return keep


def _resolve_candidate(
    conn: pymysql.Connection, cand: str, parents: list[str]
) -> Optional[dict[str, Any]]:
    """
        解析单个候选片段：名称精确（可消歧）→ 复用整串解析（编码/别名/模糊）。

        Args:
            conn: 数据库连接
            cand: 候选片段（如"朝阳区"）
            parents: 更粗的候选（用于同名消歧）

        Returns:
            区域行；未命中或异常时 None
    """
    try:
        rows = _query_region_by_sql(
            conn,
            f"SELECT {', '.join(_REGION_FIELDS)} FROM region WHERE name = %s AND deleted = b'0'",
            [cand],
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("候选名称查询失败（降级）: cand=%s err=%s", cand, type(exc).__name__)
        return None
    if rows:
        filtered = _filter_by_parents(conn, rows, parents)
        return _pick_best(filtered) if filtered else _pick_best(rows)
    try:
        return resolve_region_by_text(conn, cand)
    except Exception as exc:  # noqa: BLE001
        log.debug("候选整串解析失败（降级）: cand=%s err=%s", cand, type(exc).__name__)
        return None


def _resolve_country_prefix(
    conn: pymysql.Connection, text: Any
) -> Optional[dict[str, Any]]:
    """
        国外兜底：国家名是文本前缀（如"美国旧金山"→"美国"），取该国家行。

        Args:
            conn: 数据库连接
            text: 清洗后的地点文本

        Returns:
            国家区域行；无则 None
    """
    t = _clean_place(text)
    if not t:
        return None
    try:
        rows = _query_region_by_sql(
            conn,
            f"SELECT {', '.join(_REGION_FIELDS)} FROM region "
            "WHERE level = 1 AND deleted = b'0' AND %s LIKE CONCAT(name, '%%') "
            "ORDER BY CHAR_LENGTH(name) DESC LIMIT 1",
            [t],
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("国家前缀查询失败（降级）: err=%s", type(exc).__name__)
        return None
    return rows[0] if rows else None


def _has_district_token(text: Any) -> bool:
    """place 是否含细粒度行政区词（用于"解析可疑"告警）。"""
    t = str(text or "")
    return any(tok in t for tok in _DISTRICT_TOKENS)


def _resolve_by_splitting(
    conn: pymysql.Connection, place: Any
) -> Optional[dict[str, Any]]:
    """
        分段切分兜底：候选**从最细到最粗**逐个解析，取第一个命中（最细）。

        Args:
            conn: 数据库连接
            place: 事件地点

        Returns:
            区域行；未命中 None
    """
    candidates = _split_place_candidates(place)
    for idx, cand in enumerate(candidates):
        # 更粗的候选（在 cand 之后）作为同名消歧的父级线索
        parents = candidates[idx + 1 :]
        row = _resolve_candidate(conn, cand, parents)
        if row is not None:
            return row
    return None


def _resolve_leading_admin(
    conn: pymysql.Connection, text: Any
) -> Optional[dict[str, Any]]:
    """
        领先行政区兜底：文本以「省/市名」（去后缀）开头时取该市（如"重庆经开区东港片区"→重庆市）。

        Args:
            conn: 数据库连接
            text: 事件地点

        Returns:
            区域行；无则 None
    """
    t = _clean_place(text)
    if len(t) < 2:
        return None
    try:
        rows = _query_region_by_sql(
            conn,
            f"SELECT {', '.join(_REGION_FIELDS)} FROM region "
            "WHERE deleted = b'0' AND level IN (2, 3) AND name LIKE CONCAT(LEFT(%s, 2), '%%') "
            "ORDER BY CHAR_LENGTH(name) DESC, level DESC LIMIT 30",
            [t],
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("领先行政区查询失败（降级）: err=%s", type(exc).__name__)
        return None
    hits: list[dict[str, Any]] = []
    for row in rows:
        name = str(row.get("name") or "")
        stems = {name}
        for suf in ("特别行政区", "维吾尔自治区", "回族自治区", "壮族自治区", "自治区", "自治州", "省", "市"):
            if name.endswith(suf):
                stems.add(name[: -len(suf)])
        if any(stem and t.startswith(stem) for stem in stems):
            hits.append(row)
    return _pick_best(hits) if hits else None


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

        兜底链（261020，B 代码兜底为主）：
        0. Agent 用区域字典工具确定的 `place_region_id` 命中 → AI_PARSED；
        1. `place` **整串**命中（编码/名称/精确/别名/模糊，现状口径）→ AI_PARSED；
        2. **分段切分**（最细优先 + 同名消歧，新增）命中 → AI_PARSED；
        3. **国外**：国家名是 `place` 前缀 → AI_PARSED；
        4. 继承企业默认城市 → COMPANY_INHERITED（含区名时打"解析可疑"告警）；
        5. 都解析不到 → 区域列留空、`region_source = UNKNOWN`。

        Args:
            conn: 数据库连接
            place: 事件地点（radar_event.place）
            company: radar_company 行
            place_region_id: Agent 查字典得到的 region.id（可选，最优先）

        Returns:
            可直接并入 radar_event 写入列的区域字典
    """
    # 0. Agent 字典结果（最可信）
    by_id = _query_region_by_id(conn, place_region_id)
    if by_id is not None:
        return _to_columns(by_id, SOURCE_AI_PARSED)

    # 1. 整串（现状口径，保持新旧一致）
    region = resolve_region_by_text(conn, place)
    if region is not None:
        return _to_columns(region, SOURCE_AI_PARSED)

    # 2. 分段切分（B：代码兜底，如"北京市朝阳区"→朝阳区）
    region = _resolve_by_splitting(conn, place)
    if region is not None:
        return _to_columns(region, SOURCE_AI_PARSED)

    # 2.5 领先行政区（如"重庆经开区东港片区"→重庆市）
    region = _resolve_leading_admin(conn, place)
    if region is not None:
        return _to_columns(region, SOURCE_AI_PARSED)

    # 3. 国外：国家名是前缀（如"美国旧金山"→美国）
    region = _resolve_country_prefix(conn, place)
    if region is not None:
        return _to_columns(region, SOURCE_AI_PARSED)

    # 4. 继承企业城市
    region = resolve_company_region(conn, company)
    if region is not None:
        if _has_district_token(place):
            log.warning(
                "区域解析可疑：place 含区/县但未命中字典，已退化继承企业 place=%s", place
            )
        return _to_columns(region, SOURCE_COMPANY_INHERITED)

    # 5. 都失败
    return _to_columns(None, SOURCE_UNKNOWN)