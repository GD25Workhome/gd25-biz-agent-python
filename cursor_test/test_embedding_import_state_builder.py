# 运行命令: pytest cursor_test/test_embedding_import_state_builder.py -v
# 或: python -m pytest cursor_test/test_embedding_import_state_builder.py -v

"""测试 embedding_import state_builder：build_prompt_vars_from_record、build_initial_state_from_record。"""
import sys
from pathlib import Path

import pytest

_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.embedding_import.core.state_builder import (
    build_initial_state_from_record,
    build_prompt_vars_from_record,
)


class _MockRecord:
    """模拟 BloodPressureSessionRecord。"""
    id = "mock-rec-1"
    age = 50
    disease = "高血压"
    blood_pressure = "130/80"
    symptom = "无"
    medication = "苯磺酸氨氯地平"
    medication_status = "规律服药"
    habit = "低盐"
    history_session = "Q：今天测了130/80\nA：已记录"
    history_response = ""
    new_session = "我早上测的血压"
    new_session_response = "已帮你记录，请继续保持监测。"
    ext = ""


def test_build_prompt_vars_from_record():
    rec = _MockRecord()
    pv = build_prompt_vars_from_record(rec)
    assert "current_date" in pv
    assert "user_info" in pv
    assert pv["user_info"] is not None
    assert "高血压" in str(pv["user_info"])
    assert "ai_response" in pv
    assert "已帮你记录" in (pv["ai_response"] or "")
    assert pv["manual_ext"] == ""
    assert "current_message" in pv
    assert "我早上测的血压" in (pv["current_message"] or "")
    assert "history_messages" in pv


def test_build_initial_state_from_record():
    rec = _MockRecord()
    state = build_initial_state_from_record(rec, "sess-1", "trace-abc")
    assert state["session_id"] == "sess-1"
    assert state["trace_id"] == "trace-abc"
    assert state["token_id"] == "embedding_import"
    assert state["flow_msgs"] == []
    assert "current_message" in state
    assert "history_messages" in state
    assert "prompt_vars" in state
    assert state["current_message"].content == "我早上测的血压"
