"""Time conversion utilities for CES tools.

Reuses the CTS time_utils module for human_to_epoch_ms / now_ms.
Provides a convenience wrapper for resolving time windows.
"""
from __future__ import annotations

from typing import Optional

from huaweicloud_mcp.services.cts.time_utils import human_to_epoch_ms, now_ms
from huaweicloud_mcp.config import Settings
from huaweicloud_mcp.errors import ToolError


def resolve_time_window(
    from_time: Optional[str],
    to_time: Optional[str],
    *,
    default_from: str = "-5m",
    settings: Optional[Settings] = None,
) -> tuple[int, int]:
    """Resolve a (from_ms, to_ms) pair from human-readable inputs.

    Args:
        from_time: Human-readable start time, or None for default_from.
        to_time: Human-readable end time, or None for 'now'.
        default_from: Default relative start when from_time is None.
        settings: Settings for timezone resolution.

    Returns:
        (from_ms, to_ms) — 13-digit epoch milliseconds.
    """
    tz = settings.default_timezone if settings else "Asia/Shanghai"

    to_ms_val = (
        human_to_epoch_ms(to_time, tz) if to_time else now_ms()
    )
    from_ms_val = (
        human_to_epoch_ms(from_time, tz) if from_time
        else human_to_epoch_ms(default_from, tz)
    )

    if from_ms_val >= to_ms_val:
        raise ToolError(
            code="TIME_RANGE_INVALID",
            message=f"from_time ({from_ms_val}) must be < to_time ({to_ms_val})",
        )

    return from_ms_val, to_ms_val
