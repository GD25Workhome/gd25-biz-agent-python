"""
华院规则二（展厅需求评分）请求级上下文

用 contextvars 在单次 /radar-event-score 请求内向搜索工具传递
公司主体词、分工具搜索/抽取次数上限等。不依赖医疗登录 Session / Token。
"""
from __future__ import annotations

import contextvars
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Set
from urllib.parse import urlparse


_radar_event_ctx: contextvars.ContextVar[Optional["HuayuanRadarEventContextData"]] = (
    contextvars.ContextVar("huayuan_radar_event_ctx", default=None)
)

# 监管/交易所类主机后缀（启发式，可后续扩展）
_REGULATOR_HOST_SUFFIXES = (
    "cninfo.com.cn",
    "sse.com.cn",
    "szse.cn",
    "bse.cn",
)

_GOV_HOST_SUFFIXES = (".gov.cn",)

# 明显噪声/UGC 主机片段
_UGC_HOST_FRAGMENTS = (
    "facebook.com",
    "twitter.com",
    "x.com",
    "weibo.com",
    "zhihu.com",
    "tieba.baidu.com",
    "douyin.com",
    "xiaohongshu.com",
)


@dataclass
class HuayuanRadarEventContextData:
    """单次规则二评分请求的可变运行时状态（分工具配额）。"""

    company_name: str = ""
    stock_code: str = ""
    aliases: List[str] = field(default_factory=list)
    max_bocha: int = 10
    max_anysearch: int = 10
    max_extract_times: int = 8
    max_results_per_search: int = 5
    max_extract_chars: int = 12000
    trace_id: str = ""
    event_job_id: Optional[int] = None
    bocha_count: int = 0
    anysearch_count: int = 0
    extract_count: int = 0
    searched_bocha_queries: Set[str] = field(default_factory=set)
    searched_anysearch_queries: Set[str] = field(default_factory=set)
    extracted_urls: Set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @property
    def search_count(self) -> int:
        """博查 + AnySearch 已发起搜索总次数（兼容旧字段语义）。"""
        return self.bocha_count + self.anysearch_count

    @property
    def max_search_times(self) -> int:
        """两工具上限之和（兼容旧日志/回填字段）。"""
        return self.max_bocha + self.max_anysearch

    def subject_keywords(self) -> List[str]:
        """
            返回主体匹配用关键词列表（去重、去空）。

            Returns:
                公司名、证券代码、别名组成的关键词列表
        """
        words: List[str] = []
        for item in [self.company_name, self.stock_code, *self.aliases]:
            s = str(item or "").strip()
            if s and s not in words:
                words.append(s)
        return words

    def can_bocha(self, query: str) -> tuple[bool, str]:
        """
            判断是否允许发起一次博查搜索。

            Args:
                query: 检索式

            Returns:
                (是否允许, 不允许时的原因文案)
        """
        q = str(query or "").strip()
        if not q:
            return False, "query 为空"
        with self._lock:
            if q in self.searched_bocha_queries:
                return False, f"博查 query 已搜索过，勿重复请求: {q[:80]}"
            if self.bocha_count >= self.max_bocha:
                return False, f"已达博查搜索上限 max_bocha={self.max_bocha}"
        return True, ""

    def mark_bocha(self, query: str) -> None:
        """记录一次已发起的博查搜索（计入次数与去重集合）。"""
        q = str(query or "").strip()
        with self._lock:
            self.searched_bocha_queries.add(q)
            self.bocha_count += 1

    def can_anysearch(self, query: str) -> tuple[bool, str]:
        """
            判断是否允许发起一次 AnySearch 搜索。

            Args:
                query: 检索式

            Returns:
                (是否允许, 不允许时的原因文案)
        """
        q = str(query or "").strip()
        if not q:
            return False, "query 为空"
        with self._lock:
            if q in self.searched_anysearch_queries:
                return False, f"AnySearch query 已搜索过，勿重复请求: {q[:80]}"
            if self.anysearch_count >= self.max_anysearch:
                return False, f"已达 AnySearch 上限 max_anysearch={self.max_anysearch}"
        return True, ""

    def mark_anysearch(self, query: str) -> None:
        """记录一次已发起的 AnySearch 搜索。"""
        q = str(query or "").strip()
        with self._lock:
            self.searched_anysearch_queries.add(q)
            self.anysearch_count += 1

    def can_search(self, query: str) -> tuple[bool, str]:
        """
            兼容旧调用：等价于 can_anysearch。

            Args:
                query: 检索式

            Returns:
                (是否允许, 原因)
        """
        return self.can_anysearch(query)

    def mark_searched(self, query: str) -> None:
        """兼容旧调用：等价于 mark_anysearch。"""
        self.mark_anysearch(query)

    def can_extract(self, url: str) -> tuple[bool, str]:
        """
            判断是否允许对 URL 做正文抽取。

            Args:
                url: 目标页面 URL

            Returns:
                (是否允许, 不允许时的原因文案)
        """
        u = str(url or "").strip()
        if not u:
            return False, "url 为空"
        if not (u.startswith("http://") or u.startswith("https://")):
            return False, "url 必须为 http(s)"
        with self._lock:
            if u in self.extracted_urls:
                return False, f"url 已抽取过，请复用已有正文: {u[:120]}"
            if self.extract_count >= self.max_extract_times:
                return False, f"已达抽取上限 max_extract_times={self.max_extract_times}"
        return True, ""

    def mark_extracted(self, url: str) -> None:
        """记录一次已发起的页面抽取。"""
        u = str(url or "").strip()
        with self._lock:
            self.extracted_urls.add(u)
            self.extract_count += 1


def get_huayuan_radar_event_context() -> Optional[HuayuanRadarEventContextData]:
    """获取当前请求的规则二上下文；未设置时返回 None。"""
    return _radar_event_ctx.get()


class HuayuanRadarEventContext:
    """
    华院规则二上下文管理器。

    用法::

        with HuayuanRadarEventContext(data):
            await graph.ainvoke(...)
    """

    def __init__(self, data: HuayuanRadarEventContextData) -> None:
        self.data = data
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> HuayuanRadarEventContextData:
        self._token = _radar_event_ctx.set(self.data)
        return self.data

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._token is not None:
            _radar_event_ctx.reset(self._token)
        return False


def build_radar_event_context_from_request(
    *,
    company_name: str,
    stock_code: str,
    aliases: List[str],
    max_bocha: int,
    max_anysearch: int,
    max_extract_times: int,
    max_results_per_search: int,
    max_extract_chars: int,
    event_job_id: Optional[int],
    trace_id: str,
) -> HuayuanRadarEventContextData:
    """
        根据请求字段构造规则二上下文数据。

        Args:
            company_name: 企业标准名
            stock_code: 证券代码
            aliases: 别名列表
            max_bocha: 博查最大搜索次数
            max_anysearch: AnySearch 最大搜索次数
            max_extract_times: 最大页面抽取次数
            max_results_per_search: 每次搜索最大结果数
            max_extract_chars: 抽取正文最大字符数
            event_job_id: 业务任务 ID（可选）
            trace_id: 追踪 ID

        Returns:
            HuayuanRadarEventContextData 实例
    """
    return HuayuanRadarEventContextData(
        company_name=(company_name or "").strip(),
        stock_code=(stock_code or "").strip(),
        aliases=[str(a).strip() for a in (aliases or []) if str(a).strip()],
        max_bocha=max(0, int(max_bocha)),
        max_anysearch=max(0, int(max_anysearch)),
        max_extract_times=max(0, int(max_extract_times)),
        max_results_per_search=max(1, min(10, int(max_results_per_search))),
        max_extract_chars=max(1, int(max_extract_chars)),
        event_job_id=event_job_id,
        trace_id=trace_id,
    )


def extract_source_host(url: str) -> str:
    """
        从 URL 解析主机名。

        Args:
            url: 页面 URL

        Returns:
            小写 host；解析失败返回空串
    """
    try:
        host = urlparse(str(url or "").strip()).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def classify_authority_tier(url: str) -> str:
    """
        按主机名启发式划分来源权威档（非法律效力分级）。

        Args:
            url: 页面 URL

        Returns:
            authority_tier 枚举字符串
    """
    host = extract_source_host(url)
    if not host:
        return "unknown"
    for suffix in _REGULATOR_HOST_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            return "regulator_or_exchange"
    for suffix in _GOV_HOST_SUFFIXES:
        if host.endswith(suffix):
            return "gov"
    for frag in _UGC_HOST_FRAGMENTS:
        if frag in host:
            return "ugc_or_noise"
    return "unknown"


def text_mentions_subject(text: str, keywords: List[str]) -> bool:
    """
        判断文本是否包含任一主体关键词。

        Args:
            text: 待检查文本
            keywords: 主体关键词

        Returns:
            是否命中至少一个关键词
    """
    if not keywords:
        return True
    blob = str(text or "")
    return any(k and k in blob for k in keywords)
