"""radar_score 认领额度、锁标识与 event-only 调度。"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from radar_score.config import (
    EVENT_KIND,
    LOCKED_BY_MAX_LEN,
    ScoreSettings,
    build_locked_by,
    claim_quota,
)
from radar_score.scheduler import ScoreScheduler
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
    """并发上限与在途数量。"""

    def test_idle_claims_up_to_concurrency(self) -> None:
        self.assertEqual(claim_quota(2, 0), 2)

    def test_full_claims_nothing(self) -> None:
        self.assertEqual(claim_quota(2, 2), 0)

    def test_one_free_slot(self) -> None:
        self.assertEqual(claim_quota(2, 1), 1)


class TableNameTest(unittest.TestCase):
    """event-only：只允许 radar_event_job。"""

    def test_event_table(self) -> None:
        self.assertEqual(table_of(EVENT_KIND), "radar_event_job")

    def test_profile_rejected(self) -> None:
        with self.assertRaises(ValueError):
            table_of("profile")

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
        event_concurrency=2,
        poll_interval_sec=15,
        stale_timeout_sec=2400,
        shutdown_wait_sec=30,
    )


class EventClaimPauseTest(unittest.IsolatedAsyncioTestCase):
    """未配置 DeepSeek 搜索 key 时停领 event。"""

    def setUp(self) -> None:
        self.scheduler = ScoreScheduler(_score_settings())
        self.filled: list[str] = []

        async def _fill() -> None:
            self.filled.append(EVENT_KIND)

        self.scheduler._fill = _fill  # type: ignore[method-assign]
        self.scheduler._reclaim = lambda: None  # type: ignore[method-assign]

    async def test_no_key_skips_event_and_logs_once(self) -> None:
        with patch("radar_score.scheduler.resolve_deepseek_key", return_value=None), patch(
            "radar_score.scheduler.log"
        ) as mocked_log:
            await self.scheduler._tick()
            await self.scheduler._tick()
        self.assertEqual(self.filled, [])
        self.assertEqual(mocked_log.warning.call_count, 1)
        self.assertEqual(mocked_log.info.call_count, 0)

    async def test_key_resumes_event_claim_once(self) -> None:
        key = {"value": None}

        def _resolve():
            return key["value"]

        with patch(
            "radar_score.scheduler.resolve_deepseek_key", side_effect=_resolve
        ), patch("radar_score.scheduler.log") as mocked_log:
            await self.scheduler._tick()
            key["value"] = "sk-test"
            await self.scheduler._tick()
            await self.scheduler._tick()
        self.assertEqual(self.filled, [EVENT_KIND, EVENT_KIND])
        self.assertEqual(mocked_log.info.call_count, 1)


if __name__ == "__main__":
    unittest.main()
