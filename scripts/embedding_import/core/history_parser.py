"""
历史会话解析

将 history_session / history_response 解析为 List[BaseMessage]。
支持案例一（Q/A 交替）与案例二（第 N 轮提问/响应分块）。
见设计文档 §3.3、§8.4。
"""
import logging
import re
from typing import List, Optional, Literal, TYPE_CHECKING

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

if TYPE_CHECKING:
    from backend.infrastructure.database.models.blood_pressure_session import (
        BloodPressureSessionRecord,
    )

logger = logging.getLogger(__name__)

# 案例二：第 N 轮提问 / 响应
_RE_ROUND_QUESTION = re.compile(r"第(\d+)轮提问-*")
_RE_ROUND_RESPONSE = re.compile(r"第(\d+)轮响应")
_RE_CONTENT = re.compile(r"content\s*=\s*", re.IGNORECASE)


def _detect_format(
    session_text: Optional[str],
    response_text: Optional[str],
) -> Literal["format1", "format2", "unknown"]:
    """
    根据 3.3 节规则判别格式。

    - 优先案例二：session 含「第N轮提问」且 response 含「第N轮响应」
    - 否则案例一：session 含 Q：/A：等
    - 否则 unknown
    """
    session = (session_text or "").strip()
    response = (response_text or "").strip()

    if _RE_ROUND_QUESTION.search(session) and _RE_ROUND_RESPONSE.search(response):
        return "format2"
    if re.search(r"^[QA][：:]", session, re.MULTILINE):
        return "format1"
    return "unknown"


def _parse_history_format1(session_text: str) -> List[BaseMessage]:
    """
    案例一：Q/A 交替，仅 history_session。

    - 空白行、仅含 '-' 的分隔行忽略
    - 行首 Q：/Q: -> HumanMessage，A：/A: -> AIMessage
    - 非 Q/A 行忽略（严格模式）
    """
    out: List[BaseMessage] = []
    for line in session_text.splitlines():
        s = line.strip()
        if not s or re.match(r"^-+$", s):
            continue
        if re.match(r"^Q[：:]", s):
            content = s[2:].strip()
            if content:
                out.append(HumanMessage(content=content))
            continue
        if re.match(r"^A[：:]", s):
            content = s[2:].strip()
            if content:
                out.append(AIMessage(content=content))
            continue
        logger.debug("严格 Q/A 模式忽略非 Q/A 行: %s", line[:80])
    return out


def _parse_history_format2(
    session_text: str,
    response_text: str,
) -> List[BaseMessage]:
    """
    案例二：第 N 轮提问 / 响应分块、对齐。

    - session: 按「第N轮提问」分块，去 messageId 行，余下拼接为 user
    - response: 按「第N轮响应」分块，取 content= 后内容为 assistant
    - 按轮号对齐，依次追加 HumanMessage、AIMessage
    """
    # 解析 session：轮号 -> 用户发言
    # re.split(r'第(\d+)轮提问-*') 得 [前缀, 轮1, 块1, 轮2, 块2, ...]
    user_by_round: dict[int, str] = {}
    parts = _RE_ROUND_QUESTION.split(session_text)
    for i in range(1, len(parts) - 1):
        if i % 2 == 0:
            continue
        try:
            round_num = int(parts[i])
        except ValueError:
            continue
        block = parts[i + 1] if i + 1 < len(parts) else ""
        lines = []
        for raw in block.splitlines():
            line = raw.strip()
            if not line or re.match(r"^messageId\s*[：:]", line, re.IGNORECASE):
                continue
            lines.append(line)
        user_by_round[round_num] = "\n".join(lines)

    # 解析 response：轮号 -> 助手回复
    # re.split(r'第(\d+)轮响应') 得 [前缀, 轮1, 块1, 轮2, 块2, ...]
    resp_by_round: dict[int, str] = {}
    parts = _RE_ROUND_RESPONSE.split(response_text)
    for i in range(1, len(parts) - 1):
        if i % 2 == 0:
            continue
        try:
            round_num = int(parts[i])
        except ValueError:
            continue
        block = parts[i + 1] if i + 1 < len(parts) else ""
        m = _RE_CONTENT.search(block)
        if not m:
            resp_by_round[round_num] = ""
            continue
        rest = block[m.end() :].strip()
        # 块末的 articleId=null 等保留在 AIMessage 内，不裁剪
        resp_by_round[round_num] = rest

    # 对齐：轮号 1,2,... 依次输出 user、assistant
    all_rounds = sorted(set(user_by_round) | set(resp_by_round))
    out: List[BaseMessage] = []
    for r in all_rounds:
        u = user_by_round.get(r, "")
        a = resp_by_round.get(r, "")
        if u:
            out.append(HumanMessage(content=u))
        if a:
            out.append(AIMessage(content=a))
    return out


def parse_history_messages(
    record: "BloodPressureSessionRecord",
) -> List[BaseMessage]:
    """
    格式判别后调用 format1/format2；解析失败返回 [] 并打日志。
    """
    session_text = getattr(record, "history_session", None) or ""
    response_text = getattr(record, "history_response", None) or ""
    if isinstance(session_text, bytes):
        session_text = session_text.decode("utf-8", errors="replace")
    if isinstance(response_text, bytes):
        response_text = response_text.decode("utf-8", errors="replace")
    session_text = (session_text or "").strip()
    response_text = (response_text or "").strip()

    # 如果两个字段都为空，直接返回空列表，不记录警告
    if not session_text and not response_text:
        return []

    fmt = _detect_format(session_text, response_text)
    record_id = getattr(record, "id", "?")

    try:
        if fmt == "format2":
            return _parse_history_format2(session_text, response_text)
        if fmt == "format1":
            return _parse_history_format1(session_text)
        logger.warning("未识别的 history 格式，record_id=%s", record_id)
        return []
    except Exception as e:
        logger.warning("解析 history 失败，record_id=%s，error=%s", record_id, e)
        return []
