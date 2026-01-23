# 运行命令: pytest cursor_test/test_embedding_import_history_parser.py -v
# 或: python -m pytest cursor_test/test_embedding_import_history_parser.py -v

"""测试 embedding_import history_parser：案例一 Q/A、案例二 第N轮 格式解析与格式判别。"""
import sys
from pathlib import Path

import pytest

_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from langchain_core.messages import AIMessage, HumanMessage

from scripts.embedding_import.core.history_parser import (
    _detect_format,
    _parse_history_format1,
    _parse_history_format2,
    parse_history_messages,
)


class _MockRecord:
    """模拟 BloodPressureSessionRecord，仅含 history_session / history_response。"""
    id = "mock-id"

    def __init__(self, history_session: str = "", history_response: str = ""):
        self.history_session = history_session
        self.history_response = history_response


def test_detect_format_format1():
    t = "Q：你好\nA：您好"
    assert _detect_format(t, "") == "format1"
    assert _detect_format(t, "x") == "format1"


def test_detect_format_format2():
    s = "第1轮提问--------\nmsg"
    r = "第1轮响应\ncontent=reply"
    assert _detect_format(s, r) == "format2"


def test_detect_format_unknown():
    assert _detect_format("", "") == "unknown"
    assert _detect_format("foo bar", "baz") == "unknown"


def test_parse_format1_basic():
    text = "Q：小悦您好！我想约龙医生，做造影\nA：您有和医生提前预约吗？\nQ：没有\nA：了解了"
    out = _parse_history_format1(text)
    assert len(out) == 4
    assert isinstance(out[0], HumanMessage)
    assert "约龙医生" in (out[0].content or "")
    assert isinstance(out[1], AIMessage)
    assert "提前预约" in (out[1].content or "")
    assert isinstance(out[2], HumanMessage)
    assert "没有" in (out[2].content or "")
    assert isinstance(out[3], AIMessage)


def test_parse_format1_separator():
    text = "Q：a\nA：b\n------\nQ：c\nA：d"
    out = _parse_history_format1(text)
    assert len(out) == 4


def test_parse_format2_basic():
    session = """第1轮提问-----------
messageId: c3f30444-25a0-4886-a058-86d7a1447d3f
我刚才做完检查
第2轮提问-----------
messageId: 24f7a96b-9a5f-4922-b4cc-3bc6e058d0a5
早上好，测了127/75"""
    response = """第1轮响应
content=发泡实验阳性3级提示心脏可能...
第2轮响应
content=你能主动监测并告诉我血压情况..."""
    out = _parse_history_format2(session, response)
    assert len(out) >= 2
    assert any(isinstance(m, HumanMessage) and "做完检查" in (m.content or "") for m in out)
    assert any(isinstance(m, AIMessage) and "发泡实验" in (m.content or "") for m in out)


def test_parse_history_messages_format1():
    rec = _MockRecord(history_session="Q：hi\nA：hello", history_response="")
    msgs = parse_history_messages(rec)
    assert len(msgs) == 2
    assert isinstance(msgs[0], HumanMessage)
    assert isinstance(msgs[1], AIMessage)


def test_parse_history_messages_format2():
    s = "第1轮提问---\n用户问\n第2轮提问---\n用户问2"
    r = "第1轮响应\ncontent=答1\n第2轮响应\ncontent=答2"
    rec = _MockRecord(history_session=s, history_response=r)
    msgs = parse_history_messages(rec)
    assert len(msgs) >= 2


def test_parse_history_messages_unknown():
    rec = _MockRecord(history_session="random text", history_response="other")
    msgs = parse_history_messages(rec)
    assert msgs == []
