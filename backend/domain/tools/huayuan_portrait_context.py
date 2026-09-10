"""
华院画像评分请求级上下文

用 contextvars 在单次 /portrait 请求内向工具传递白名单、加载上限、工具基址等。
不依赖医疗登录 Session / Token。
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from typing import Dict, Optional, Set


_portrait_ctx: contextvars.ContextVar[Optional["HuayuanPortraitContextData"]] = (
    contextvars.ContextVar("huayuan_portrait_ctx", default=None)
)


@dataclass
class HuayuanPortraitContextData:
    """单次画像请求的可变运行时状态。"""

    allowed_file_ids: Set[str] = field(default_factory=set)
    max_load_times: int = 3
    max_chars: int = 12000
    document_tool_base_url: str = ""
    profile_job_id: Optional[int] = None
    trace_id: str = ""
    load_count: int = 0
    loaded_file_ids: Set[str] = field(default_factory=set)

    def can_load(self, file_id: str) -> tuple[bool, str]:
        """
            判断是否允许加载指定 file_id。

            Args:
                file_id: 证据文档 ID（字符串）

            Returns:
                (是否允许, 不允许时的原因文案)
        """
        fid = str(file_id).strip()
        if not fid:
            return False, "file_id 为空"
        if self.allowed_file_ids and fid not in self.allowed_file_ids:
            return False, f"file_id={fid} 不在本次白名单内"
        if fid in self.loaded_file_ids:
            return False, f"file_id={fid} 已加载过，请复用已有要点，勿重复请求"
        if self.load_count >= self.max_load_times:
            return False, f"已达加载上限 max_load_times={self.max_load_times}"
        return True, ""

    def mark_loaded(self, file_id: str) -> None:
        """记录一次成功发起的加载（计入次数与去重集合）。"""
        fid = str(file_id).strip()
        self.loaded_file_ids.add(fid)
        self.load_count += 1


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


def build_portrait_context_from_request(
    *,
    file_ids: list[str],
    max_load_times: int,
    max_chars: int,
    document_tool_base_url: str,
    profile_job_id: Optional[int],
    trace_id: str,
) -> HuayuanPortraitContextData:
    """
        根据请求字段构造画像上下文数据。

        Args:
            file_ids: 允许加载的证据 ID 列表
            max_load_times: 最大加载次数
            max_chars: 单次正文最大字符数
            document_tool_base_url: 工具 API 基址
            profile_job_id: 画像任务 ID（可选）
            trace_id: 追踪 ID

        Returns:
            HuayuanPortraitContextData 实例
    """
    return HuayuanPortraitContextData(
        allowed_file_ids={str(x).strip() for x in file_ids if str(x).strip()},
        max_load_times=max(0, int(max_load_times)),
        max_chars=max(1, int(max_chars)),
        document_tool_base_url=(document_tool_base_url or "").rstrip("/"),
        profile_job_id=profile_job_id,
        trace_id=trace_id,
    )
