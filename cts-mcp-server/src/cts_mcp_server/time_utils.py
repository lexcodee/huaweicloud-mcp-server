"""Time conversion utilities for CTS.

CTS ``from``/``to`` parameters are 13-digit millisecond UTC timestamps and
form a HALF-OPEN interval ``[from, to)``. Humans, however, want to write
``"2026-06-20 22:00:00"``, ``"-1h"``, or ISO8601 with offset. This module
isolates that translation so the rest of the codebase only ever sees
integer epoch-ms.

The default timezone applied to NAIVE datetime strings is configurable via
the ``CTS_DEFAULT_TIMEZONE`` env var (default ``Asia/Shanghai``).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python <3.9
    ZoneInfo = None  # type: ignore[assignment]


_RELATIVE_RE = re.compile(r"^\s*-\s*(\d+)\s*([smhdw])\s*$", re.IGNORECASE)

# Accepted absolute formats (order matters — most specific first)
_ABSOLUTE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def _resolve_tz(name: str) -> timezone:
    """Return a tzinfo. Falls back to UTC offset map if zoneinfo missing."""
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)  # type: ignore[return-value]
        except Exception:  # noqa: BLE001 - bad name, treat as UTC
            return timezone.utc
    if name.upper() == "UTC":
        return timezone.utc
    # Conservative fallback — most ops folks setting CTS_DEFAULT_TIMEZONE
    # will be on a modern Python with zoneinfo.
    return timezone(timedelta(hours=8)) if name == "Asia/Shanghai" else timezone.utc


def now_ms() -> int:
    """Current UTC time in milliseconds since epoch."""
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def human_to_epoch_ms(text: str, default_tz: str = "Asia/Shanghai") -> int:
    """Parse a human-written time and return 13-digit ms epoch.

    Accepts:
      * ``"-1h"``, ``"-30m"``, ``"-2d"`` — relative to *now*
      * ``"2026-06-20T22:00:00+08:00"`` — ISO8601 with offset (recommended)
      * ``"2026-06-20T22:00:00Z"``      — ISO8601 UTC
      * ``"2026-06-20 22:00:00"``       — naive, interpreted in ``default_tz``
      * ``"2026-06-20"``                — naive date, midnight in ``default_tz``
      * Plain int/str of digits         — already an epoch (10 or 13 digits)

    Raises ``ValueError`` on unrecognized input.
    """
    if text is None:
        raise ValueError("time value is None")
    s = str(text).strip()
    if not s:
        raise ValueError("time value is empty")

    # 1) "now" literal
    if s.lower() == "now":
        return now_ms()

    # 2) Relative time: -<N><unit>
    m = _RELATIVE_RE.match(s)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit] * n
        target = datetime.now(tz=timezone.utc) - timedelta(seconds=seconds)
        return int(target.timestamp() * 1000)

    # 2) Pure-digit epoch (sec or ms)
    if s.isdigit():
        v = int(s)
        if v >= 10**12:  # already ms
            return v
        if v >= 10**9:  # seconds
            return v * 1000
        raise ValueError(f"epoch value {v!r} too small to be a sane timestamp")

    # 3) ISO8601 with 'Z' suffix → normalize to '+00:00' so fromisoformat works
    iso_candidate = s
    if iso_candidate.endswith("Z"):
        iso_candidate = iso_candidate[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(iso_candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_resolve_tz(default_tz))
        return int(dt.timestamp() * 1000)
    except ValueError:
        pass

    # 4) Try each strftime format in turn
    for fmt in _ABSOLUTE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_resolve_tz(default_tz))
        return int(dt.timestamp() * 1000)

    raise ValueError(
        f"cannot parse time value {text!r}; expected ISO8601 "
        f"(e.g. '2026-06-20T22:00:00+08:00'), 'YYYY-MM-DD HH:MM:SS', "
        f"or relative form like '-1h' / '-2d'."
    )


def epoch_ms_to_human(ms: Optional[int], tz_name: str = "Asia/Shanghai") -> Optional[str]:
    """Render an epoch-ms timestamp in the given timezone.

    Returns ``None`` if the input is None — CTS occasionally omits the
    ``time`` field on partial trace entries.
    """
    if ms is None:
        return None
    tz = _resolve_tz(tz_name)
    dt = datetime.fromtimestamp(ms / 1000.0, tz=tz)
    return dt.strftime("%Y-%m-%d %H:%M:%S %z")


SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000
# Allow a small tolerance so that a request issued ~6d 23h 59m 30s ago
# doesn't get rejected by clock drift between client and our server.
SEVEN_DAY_TOLERANCE_MS = 5 * 60 * 1000  # 5 minutes
