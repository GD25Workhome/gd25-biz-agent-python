"""radar_score 认领额度、锁标识和 Java 响应解析。"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from radar_score.config import EVENT_KIND, LOCKED_BY_MAX_LEN, PROFILE_KIND, ScoreSettings, build_locked_by, claim_quota
from radar_score.scheduler import ScoreScheduler
from radar_score.java_client import (
    JavaScoreError,
    assert_java_ok,
    extract_request_body,
    unwrap_java_data,
)
from radar_score.repository import table_of


class LockedByTest(unittest.TestCase):
    """锁标识必须放得进 locked_by varchar(64)。"""

    def test_short_host_keeps_prefix_and_pid(self) -> None:
        locked = build_locked_by("agent", 42)
        self.assertEqual(locked, "python-score-agent:42")
        self.assertLessEqual(len(locked), LOCKED_BY_MAX_LEN)
        self.assertTrue(locked.startswith("python-score-"))

    def test_long_host_is_truncated(self) -> None:
        locked = build_locked_by("h" * 200, 123456)
        self.assertLessEqual(len(locked), LOCKED_BY_MAX_LEN)
        self.assertTrue(locked.endswith(":123456"))
        self.assertTrue(locked.startswith("python-score-"))


class ClaimQuotaTest(unittest.TestCase):
    """每类并发默认 2，在途占满后不再认领。"""

    def test_idle_claims_up_to_concurrency(self) -> None:
        self.assertEqual(claim_quota(2, 0), 2)

    def test_full_claims_nothing(self) -> None:
        self.assertEqual(claim_quota(2, 2), 0)

    def test_one_free_slot(self) -> None:
        self.assertEqual(claim_quota(2, 1), 1)


class TableNameTest(unittest.TestCase):
    """只允许两张任务表。"""

    def test_known_kinds(self) -> None:
        self.assertEqual(table_of("profile"), "radar_profile_job")
        self.assertEqual(table_of("event"), "radar_event_job")

    def test_unknown_kind_rejected(self) -> None:
        with self.assertRaises(ValueError):
            table_of("news")


def _score_settings() -> ScoreSettings:
    """构造不连库的调度配置，只给 _tick 分支用。"""
    return ScoreSettings(
        db_host="127.0.0.1",
        db_port=3306,
        db_user="u",
        db_password="p",
        db_name="db",
        tenant_id=None,
        locked_by="python-score-test:1",
        java_base_url="http://127.0.0.1:38080",
        java_token="token",
        profile_concurrency=2,
        event_concurrency=2,
        poll_interval_sec=15,
        stale_timeout_sec=2400,
        java_timeout_sec=60,
        java_down_backoff_sec=60,
        shutdown_wait_sec=30,
    )


class EventClaimPauseTest(unittest.IsolatedAsyncioTestCase):
    """AnySearch 当天无存活 key 时停领展厅需求，画像继续。"""

    def setUp(self) -> None:
        self.scheduler = ScoreScheduler(_score_settings())
        self.filled: list[str] = []

        async def _fill(kind: str) -> None:
            self.filled.append(kind)

        self.scheduler._fill = _fill  # type: ignore[method-assign]
        self.scheduler._reclaim = lambda: None  # type: ignore[method-assign]

    async def test_no_live_key_skips_event_and_logs_once(self) -> None:
        with patch("radar_score.scheduler.has_live_key", return_value=False), patch(
            "radar_score.scheduler.log"
        ) as mocked_log:
            await self.scheduler._tick()
            await self.scheduler._tick()
        self.assertEqual(self.filled, [PROFILE_KIND, PROFILE_KIND])
        self.assertEqual(mocked_log.warning.call_count, 1)
        self.assertEqual(mocked_log.info.call_count, 0)

    async def test_live_key_resumes_event_claim_once(self) -> None:
        live = {"ok": False}

        def _live() -> bool:
            return live["ok"]

        with patch("radar_score.scheduler.has_live_key", side_effect=_live), patch(
            "radar_score.scheduler.log"
        ) as mocked_log:
            await self.scheduler._tick()
            live["ok"] = True
            await self.scheduler._tick()
            await self.scheduler._tick()
        self.assertEqual(
            self.filled,
            [PROFILE_KIND, PROFILE_KIND, EVENT_KIND, PROFILE_KIND, EVENT_KIND],
        )
        self.assertEqual(mocked_log.info.call_count, 1)


class JavaPayloadTest(unittest.TestCase):
    """prepare 响应兼容芋道 CommonResult。"""

    def test_unwrap_common_result(self) -> None:
        data = unwrap_java_data(
            {"code": 0, "data": {"requestBody": {"query": "评分", "context": {}}}, "msg": ""}
        )
        body = extract_request_body(data)
        self.assertEqual(body["query"], "评分")

    def test_business_code_raises(self) -> None:
        with self.assertRaises(JavaScoreError):
            unwrap_java_data({"code": 500, "data": None, "msg": "任务锁不匹配"})

    def test_missing_request_body_raises(self) -> None:
        with self.assertRaises(JavaScoreError):
            extract_request_body({"jobId": 1})

    def test_complete_accepts_boolean_data(self) -> None:
        assert_java_ok({"code": 0, "data": True, "msg": ""})


if __name__ == "__main__":
    unittest.main()
