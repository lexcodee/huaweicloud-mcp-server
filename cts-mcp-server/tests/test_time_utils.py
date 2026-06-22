"""Tests for time_utils — human-readable ↔ 13-digit ms conversion."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cts_mcp_server.time_utils import (
    SEVEN_DAYS_MS,
    SEVEN_DAY_TOLERANCE_MS,
    epoch_ms_to_human,
    human_to_epoch_ms,
    now_ms,
)


class TestHumanToEpochMs:
    """Parsing human time strings into 13-digit ms."""

    def test_iso8601_with_offset(self):
        ms = human_to_epoch_ms("2026-06-20T22:00:00+08:00")
        # 2026-06-20T14:00:00Z
        dt = datetime(2026, 6, 20, 14, 0, 0, tzinfo=timezone.utc)
        assert ms == int(dt.timestamp() * 1000)

    def test_iso8601_utc_z(self):
        ms = human_to_epoch_ms("2026-06-20T14:00:00Z")
        dt = datetime(2026, 6, 20, 14, 0, 0, tzinfo=timezone.utc)
        assert ms == int(dt.timestamp() * 1000)

    def test_naive_string_default_tz(self):
        ms = human_to_epoch_ms("2026-06-20 22:00:00", default_tz="Asia/Shanghai")
        # Same instant as the ISO8601 +08:00 test above
        dt = datetime(2026, 6, 20, 14, 0, 0, tzinfo=timezone.utc)
        assert ms == int(dt.timestamp() * 1000)

    def test_naive_string_utc(self):
        ms = human_to_epoch_ms("2026-06-20 14:00:00", default_tz="UTC")
        dt = datetime(2026, 6, 20, 14, 0, 0, tzinfo=timezone.utc)
        assert ms == int(dt.timestamp() * 1000)

    def test_relative_minus_1h(self):
        before = now_ms()
        ms = human_to_epoch_ms("-1h")
        after = now_ms()
        # Should be roughly 1 hour ago (3600000 ms)
        expected = before - 3600_000
        assert expected - 2000 <= ms <= after - 3600_000 + 2000

    def test_relative_minus_2d(self):
        before = now_ms()
        ms = human_to_epoch_ms("-2d")
        after = now_ms()
        expected = before - 2 * 86400_000
        assert expected - 2000 <= ms <= after - 2 * 86400_000 + 2000

    def test_relative_minus_30m(self):
        before = now_ms()
        ms = human_to_epoch_ms("-30m")
        after = now_ms()
        expected = before - 30 * 60_000
        assert expected - 2000 <= ms <= after - 30 * 60_000 + 2000

    def test_epoch_ms_passthrough(self):
        ms = 1718900000000
        assert human_to_epoch_ms(str(ms)) == ms

    def test_epoch_s_uplift(self):
        s = 1718900000
        assert human_to_epoch_ms(str(s)) == s * 1000

    def test_unparseable_raises(self):
        with pytest.raises(ValueError, match="cannot parse"):
            human_to_epoch_ms("yesterday")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            human_to_epoch_ms("")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            human_to_epoch_ms(None)


class TestEpochMsToHuman:
    """Rendering ms back to human-readable in a given timezone."""

    def test_shanghai(self):
        # 2026-06-20 22:00:00 CST = 2026-06-20 14:00:00 UTC
        dt = datetime(2026, 6, 20, 14, 0, 0, tzinfo=timezone.utc)
        ms = int(dt.timestamp() * 1000)
        result = epoch_ms_to_human(ms, "Asia/Shanghai")
        assert "2026-06-20" in result
        assert "22:00:00" in result

    def test_utc(self):
        dt = datetime(2026, 6, 20, 14, 0, 0, tzinfo=timezone.utc)
        ms = int(dt.timestamp() * 1000)
        result = epoch_ms_to_human(ms, "UTC")
        assert "14:00:00" in result

    def test_none_returns_none(self):
        assert epoch_ms_to_human(None) is None


class TestSevenDayConstants:
    """Verify the 7-day window constants are sane."""

    def test_seven_days_ms(self):
        assert SEVEN_DAYS_MS == 7 * 24 * 60 * 60 * 1000

    def test_tolerance(self):
        assert SEVEN_DAY_TOLERANCE_MS == 5 * 60 * 1000
