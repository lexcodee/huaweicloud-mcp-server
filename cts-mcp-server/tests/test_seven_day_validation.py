"""Tests for 7-day time-range validation in resolve_time_range.

The CTS ListTraces API only retains 7 days of data. Our tool must reject
requests whose start_time falls outside that window BEFORE issuing any
SDK call.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cts_mcp_server.models import resolve_time_range
from cts_mcp_server.time_utils import SEVEN_DAY_TOLERANCE_MS, SEVEN_DAYS_MS, now_ms


def _ms_to_iso(ms: int) -> str:
    """Convert ms epoch to an ISO8601 string the parser accepts.

    We truncate to second precision (the ISO format doesn't carry ms),
    so round-trip assertions must allow up to 1s slop.
    """
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


# Maximum round-trip error from truncating ms → ISO(seconds) → ms.
_SLOP_MS = 1000  # 1 second


class TestSevenDayValidation:
    """Boundary tests for the 7-day window."""

    def test_exactly_7_days_ago_plus_tolerance_is_ok(self):
        """start_time = now - 7d + tolerance → should pass (just inside)."""
        now = now_ms()
        start_ms = now - SEVEN_DAYS_MS + SEVEN_DAY_TOLERANCE_MS + 60_000  # 1 min inside
        end_ms = now
        from_ms, to_ms = resolve_time_range(
            _ms_to_iso(start_ms), _ms_to_iso(end_ms), "UTC"
        )
        # Allow ISO round-trip slop
        assert abs(from_ms - start_ms) <= _SLOP_MS

    def test_7_days_ago_minus_1_min_is_rejected(self):
        """start_time = now - 7d - 1min → should be rejected.

        Note: the 5-minute tolerance means the floor is at
        now - 7d - 5min. So 1 min before 7d is still within
        tolerance. We need to go past the tolerance to trigger
        rejection.
        """
        now = now_ms()
        # 6 minutes before the 7d mark — past the 5min tolerance
        start_ms = now - SEVEN_DAYS_MS - 6 * 60_000
        end_ms = now
        with pytest.raises(ValueError, match="last 7 days"):
            resolve_time_range(_ms_to_iso(start_ms), _ms_to_iso(end_ms), "UTC")

    def test_8_days_ago_is_rejected(self):
        """start_time = now - 8d → clearly outside the window."""
        now = now_ms()
        start_ms = now - 8 * 86400_000
        end_ms = now
        with pytest.raises(ValueError, match="last 7 days"):
            resolve_time_range(_ms_to_iso(start_ms), _ms_to_iso(end_ms), "UTC")

    def test_6_days_ago_is_ok(self):
        """start_time = now - 6d → well within the window."""
        now = now_ms()
        start_ms = now - 6 * 86400_000
        end_ms = now
        from_ms, to_ms = resolve_time_range(
            _ms_to_iso(start_ms), _ms_to_iso(end_ms), "UTC"
        )
        assert abs(from_ms - start_ms) <= _SLOP_MS

    def test_start_after_end_is_rejected(self):
        """start_time > end_time → invalid range."""
        now = now_ms()
        with pytest.raises(ValueError, match="strictly earlier"):
            resolve_time_range(
                _ms_to_iso(now), _ms_to_iso(now - 3600_000), "UTC"
            )

    def test_start_equals_end_is_rejected(self):
        """start_time == end_time → half-open interval would be empty."""
        now = now_ms()
        with pytest.raises(ValueError, match="strictly earlier"):
            resolve_time_range(_ms_to_iso(now), _ms_to_iso(now), "UTC")

    def test_no_start_defaults_to_one_hour_ago(self):
        """If start_time is None, defaults to now - 1h."""
        now = now_ms()
        end_ms = now
        from_ms, to_ms = resolve_time_range(None, _ms_to_iso(end_ms), "UTC")
        # Allow 2s slop for the time it takes to execute
        assert abs((now - 3600_000) - from_ms) < 2000

    def test_no_end_defaults_to_now(self):
        """If end_time is None, defaults to now."""
        now = now_ms()
        start_ms = now - 3600_000
        from_ms, to_ms = resolve_time_range(_ms_to_iso(start_ms), None, "UTC")
        assert abs(now - to_ms) < 2000

    def test_relative_start_within_window(self):
        """'-2d' is within 7d → should pass."""
        from_ms, to_ms = resolve_time_range("-2d", None, "UTC")
        assert from_ms > 0

    def test_relative_start_outside_window(self):
        """'-8d' is outside 7d → should fail."""
        with pytest.raises(ValueError, match="last 7 days"):
            resolve_time_range("-8d", None, "UTC")

    def test_within_tolerance_but_past_7d_is_accepted(self):
        """now - 7d - 3min is within the 5min tolerance → accepted."""
        now = now_ms()
        start_ms = now - SEVEN_DAYS_MS - 3 * 60_000  # 3 min before 7d, within 5min tolerance
        end_ms = now
        from_ms, to_ms = resolve_time_range(
            _ms_to_iso(start_ms), _ms_to_iso(end_ms), "UTC"
        )
        assert abs(from_ms - start_ms) <= _SLOP_MS
