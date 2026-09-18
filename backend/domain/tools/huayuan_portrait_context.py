"""
华院画像评分请求级上下文

用 contextvars 在单次 /portrait 请求内向工具传递白名单、加载上限等。
"""
from __future__ import annotations

import contextvars
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

DEFAULT_PORTRAIT_MAX_LOAD_TIMES = 3
DEFAULT_PORTRAIT_MAX_CHARS = 12000
DEFAULT_PORTRAIT_MAX_DOCS = 20
MAX_PORTRAIT_DOCS_LIMIT = 50

_portrait_ctx: contextvars.ContextVar[Optional["HuayuanPortraitContextData"]] = (
    contextvars.ContextVar("huayuan_portrait_ctx", default=None)
)


@dataclass
class HuayuanPortraitContextData:
    """单次画像请求的可变运行时状态。"""

    company_id: Optional[int] = None
    allowed_doc_ids: Set[str] = field(default_factory=set)
    max_load_times: int = DEFAULT_PORTRAIT_MAX_LOAD_TIMES
    max_chars: int = DEFAULT_PORTRAIT_MAX_CHARS
    max_docs: int = DEFAULT_PORTRAIT_MAX_DOCS
    prefer_source_kinds: List[str] = field(default_factory=list)
    knowledge_enabled: bool = True
    profile_job_id: Optional[int] = None
    trace_id: str = ""
    load_count: int = 0
    loaded_doc_ids: Set[str] = field(default_factory=set)
    loaded_content_by_doc: Dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def register_allowed(self, doc_ids: Any) -> int:
        """写入 gather 白名单 doc_id。"""
        added = 0
        with self._lock:
            for doc_id in doc_ids or []:
                s = str(doc_id).strip()
                if not s or s in self.allowed_doc_ids:
                    continue
                self.allowed_doc_ids.add(s)
                added += 1
        return added

    def can_load(self, doc_id: str) -> tuple[bool, str]:
        """
            判断是否允许加载指定 doc_id。

            空白名单一律拒绝（防乱拉全文）。

            Args:
                doc_id: 知识库文档 ID

            Returns:
                (是否允许, 不允许时的原因文案)
        """
        did = str(doc_id).strip()
        if not did:
            return False, "doc_id 为空"
        with self._lock:
            if not self.allowed_doc_ids:
                return False, "本次 gather 白名单为空，禁止 load_news_document"
            if did not in self.allowed_doc_ids:
                return False, f"doc_id={did} 不在本次白名单内"
            if did in self.loaded_doc_ids:
                return False, f"doc_id={did} 已加载过，请复用已有要点，勿重复请求"
            if self.load_count >= self.max_load_times:
                return False, f"已达加载上限 max_load_times={self.max_load_times}"
        return True, ""

    def mark_loaded(self, doc_id: str) -> None:
        """记录一次成功发起的加载（计入次数与去重集合）。"""
        did = str(doc_id).strip()
        with self._lock:
            self.loaded_doc_ids.add(did)
            self.load_count += 1

    def remember_loaded_content(self, doc_id: str, content: str) -> None:
        """缓存截断正文，供 parser quote 软校验。"""
        did = str(doc_id).strip()
        if not did:
            return
        with self._lock:
            self.loaded_content_by_doc[did] = str(content or "")


def get_huayuan_portrait_context() -> Optional[HuayuanPortraitContextData]:
    """获取当前请求的华院画像上下文；未设置时返回 None。"""
    return _portrait_ctx.get()


class HuayuanPortraitContext:
    """
    华院画像上下文管理器。

    用法::
        with HuayuanPortraitContext(data):
            await graph.ainvoke(...)
    """

    def __init__(self, data: HuayuanPortraitContextData) -> None:
        self.data = data
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> HuayuanPortraitContextData:
        self._token = _portrait_ctx.set(self.data)
        return self.data

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._token is not None:
            _portrait_ctx.reset(self._token)
        return False


def resolve_portrait_knowledge_config(ctx: Any) -> Dict[str, Any]:
    """
        解析画像 knowledge 配置（缺省 enabled=true）。

        Args:
            ctx: 请求 context 对象或 dict

        Returns:
            enabled, max_docs, max_load_times, prefer_source_kinds
    """
    cfg = getattr(ctx, "knowledge", None) if ctx is not None else None
    if cfg is None and isinstance(ctx, dict):
        cfg = ctx.get("knowledge")
    if cfg is None:
        return {
            "enabled": True,
            "max_docs": DEFAULT_PORTRAIT_MAX_DOCS,
            "max_load_times": DEFAULT_PORTRAIT_MAX_LOAD_TIMES,
            "prefer_source_kinds": [],
        }
    enabled = getattr(cfg, "enabled", None)
    if enabled is None and isinstance(cfg, dict):
        enabled = cfg.get("enabled", True)
    if not bool(enabled if enabled is not None else True):
        return {
            "enabled": False,
            "max_docs": DEFAULT_PORTRAIT_MAX_DOCS,
            "max_load_times": DEFAULT_PORTRAIT_MAX_LOAD_TIMES,
            "prefer_source_kinds": [],
        }
    raw_docs = getattr(cfg, "max_docs", None)
    if raw_docs is None and isinstance(cfg, dict):
        raw_docs = cfg.get("max_docs")
    raw_loads = getattr(cfg, "max_load_times", None)
    if raw_loads is None and isinstance(cfg, dict):
        raw_loads = cfg.get("max_load_times")
    kinds = getattr(cfg, "prefer_source_kinds", None)
    if kinds is None and isinstance(cfg, dict):
        kinds = cfg.get("prefer_source_kinds")
    max_docs = int(raw_docs) if raw_docs is not None else DEFAULT_PORTRAIT_MAX_DOCS
    max_loads = int(raw_loads) if raw_loads is not None else DEFAULT_PORTRAIT_MAX_LOAD_TIMES
    prefer: List[str] = []
    if isinstance(kinds, list):
        prefer = [str(k).strip() for k in kinds if str(k).strip()]
    return {
        "enabled": True,
        "max_docs": max(1, min(MAX_PORTRAIT_DOCS_LIMIT, max_docs)),
        "max_load_times": max(0, max_loads),
        "prefer_source_kinds": prefer,
    }


def build_portrait_context_from_request(
    *,
    company_id: Optional[int],
    allowed_doc_ids: List[str],
    max_load_times: int,
    max_chars: int,
    max_docs: int,
    knowledge_enabled: bool,
    prefer_source_kinds: Optional[List[str]] = None,
    profile_job_id: Optional[int],
    trace_id: str,
) -> HuayuanPortraitContextData:
    """
        根据请求字段构造画像上下文数据。

        Args:
            company_id: 企业 ID
            allowed_doc_ids: gather 写入的白名单（可为空，此时禁止 load）
            max_load_times: 最大加载次数
            max_chars: 单次正文最大字符数
            max_docs: 召回上限（日志/排障）
            knowledge_enabled: 是否走向量召回
            prefer_source_kinds: Milvus source_kind 偏好
            profile_job_id: 画像任务 ID
            trace_id: 追踪 ID

        Returns:
            HuayuanPortraitContextData 实例
    """
    data = HuayuanPortraitContextData(
        company_id=company_id,
        allowed_doc_ids={str(x).strip() for x in allowed_doc_ids if str(x).strip()},
        max_load_times=max(0, int(max_load_times)),
        max_chars=max(1, int(max_chars)),
        max_docs=max(1, min(MAX_PORTRAIT_DOCS_LIMIT, int(max_docs))),
        knowledge_enabled=bool(knowledge_enabled),
        prefer_source_kinds=list(prefer_source_kinds or []),
        profile_job_id=profile_job_id,
        trace_id=trace_id,
    )
    return data
