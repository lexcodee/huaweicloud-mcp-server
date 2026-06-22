"""Structured logging formatters for the MCP gateway.

Two formats are available:

- ``text`` (default): human-readable single-line format, identical to the
  original ``logging.basicConfig`` output.
- ``json``: one JSON object per line, optimised for log shippers
  (fluentd / filebeat / Loki) and audit indexing.

Usage::

    from mcp_gateway.logfmt import setup_logging

    setup_logging(level="INFO", fmt="json")

The JSON formatter promotes any ``extra`` kwargs passed to the log call
into top-level keys, so::

    log.warning("auth-rejected", extra={"status": 403, "path": "/ecs/sse"})

emits::

    {"ts":"...","level":"WARNING","logger":"mcp_gateway.auth",
     "msg":"auth-rejected","status":403,"path":"/ecs/sse"}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


# Keys that belong to the standard LogRecord; everything else in ``extra``
# is promoted to the top-level JSON object.
_STANDARD_KEYS = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "relativeCreated",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "pathname",
        "filename",
        "module",
        "levelno",
        "levelname",
        "thread",
        "threadName",
        "process",
        "processName",
        "msecs",
        "taskName",
        "getMessage",
    }
)


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line.

    Top-level keys:
      ts      — ISO-8601 with timezone (Asia/Shanghai by default)
      level   — WARNING / ERROR / INFO / …
      logger  — logger name (e.g. ``mcp_gateway.auth``)
      msg     — the log message string

    Any ``extra`` kwargs are promoted to top-level keys alongside the
    above four.  If an extra key collides with a standard key, the extra
    value wins (this is intentional — it lets callers override ``msg``
    with a structured payload if desired).
    """

    def __init__(self, tz_key: str = "TZ", default_tz: str = "Asia/Shanghai"):
        super().__init__()
        self._tz_key = tz_key
        self._default_tz = default_tz

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        """Return ISO-8601 with timezone."""
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        try:
            import zoneinfo

            tz_name = os.environ.get(self._tz_key, self._default_tz)
            tz = zoneinfo.ZoneInfo(tz_name)
            dt = dt.astimezone(tz)
        except Exception:
            pass  # fallback to UTC
        return dt.isoformat()

    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, Any] = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Promote extra kwargs to top-level.
        for key, value in record.__dict__.items():
            if key not in _STANDARD_KEYS and key not in obj:
                try:
                    json.dumps(value)  # ensure serialisable
                    obj[key] = value
                except (TypeError, ValueError):
                    obj[key] = str(value)

        # Append exception info if present.
        if record.exc_info and record.exc_info[0] is not None:
            obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(obj, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable single-line format (backward compatible)."""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )


def setup_logging(
    level: str = "INFO",
    fmt: str = "text",
    stream: Any | None = None,
) -> None:
    """Configure the ``mcp_gateway`` logger namespace with the chosen format.

    We configure the ``mcp_gateway`` logger specifically (not the root logger)
    so that sub-service calls to ``logging.basicConfig()`` during import don't
    clobber our formatter.

    The root logger level is also set so that messages propagate correctly.

    Args:
        level: log level string (INFO, WARNING, …).
        fmt: ``"text"`` or ``"json"``.
        stream: output stream (defaults to sys.stderr).
    """
    handler = logging.StreamHandler(stream or sys.stderr)
    if fmt.strip().lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter())

    # Configure the mcp_gateway namespace logger.
    gw_logger = logging.getLogger("mcp_gateway")
    gw_logger.setLevel(level.upper())
    gw_logger.handlers.clear()
    gw_logger.addHandler(handler)
    # Prevent propagation to root to avoid double-printing when root also
    # has a handler (e.g. from sub-service basicConfig).
    gw_logger.propagate = False

    # Also set root level so non-gateway loggers (uvicorn, etc.) respect it.
    logging.getLogger().setLevel(level.upper())
