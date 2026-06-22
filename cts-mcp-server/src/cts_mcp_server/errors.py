"""Unified error handling.

All MCP tools must return a JSON-serializable dict of the shape:
    {"ok": True,  "data": ...}
    {"ok": False, "error": {"code": str, "message": str, ...}}
"""
from __future__ import annotations

import functools
import logging
import time
import uuid
from typing import Any, Callable, TypeVar

from huaweicloudsdkcore.exceptions import exceptions as hwc_exc
from pydantic import ValidationError

log = logging.getLogger("cts_mcp_server.tools")

F = TypeVar("F", bound=Callable[..., Any])


class ToolError(Exception):
    """Raised inside tools to signal a controlled failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        request_id: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = request_id
        self.hint = hint

    def to_dict(self) -> dict:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.request_id:
            out["request_id"] = self.request_id
        if self.hint:
            out["hint"] = self.hint
        return out


# Sensitive kwargs to redact from tool-entry logs (we never log raw
# request/response payloads — those are scrubbed inside the tool itself).
_REDACT_KWARGS = {"password", "secret", "token", "credential", "private_key"}


def _params_summary(kwargs: dict) -> dict:
    """Summarize tool kwargs for logging — drop bulky/sensitive fields."""
    summary: dict[str, Any] = {}
    for k, v in kwargs.items():
        if k.lower() in _REDACT_KWARGS:
            summary[k] = "***"
        elif isinstance(v, list):
            summary[k] = f"<list len={len(v)}>"
        elif isinstance(v, str) and len(v) > 80:
            summary[k] = v[:60] + "..."
        else:
            summary[k] = v
    return summary


def wrap_tool(func: F) -> F:
    """Decorator: standardize tool return shape, log calls, mask errors."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> dict:
        call_id = uuid.uuid4().hex[:8]
        tool_name = func.__name__
        started = time.monotonic()
        log.info(
            "tool.start name=%s call_id=%s params=%s",
            tool_name,
            call_id,
            _params_summary(kwargs),
        )
        try:
            data = func(*args, **kwargs)
            duration_ms = int((time.monotonic() - started) * 1000)
            # Best-effort returned-count for the search tool
            count = None
            if isinstance(data, dict):
                count = data.get("total_returned")
            log.info(
                "tool.ok name=%s call_id=%s duration_ms=%d total_returned=%s",
                tool_name,
                call_id,
                duration_ms,
                count,
            )
            return {"ok": True, "data": data}

        except ToolError as e:
            duration_ms = int((time.monotonic() - started) * 1000)
            log.warning(
                "tool.err name=%s call_id=%s duration_ms=%d code=%s msg=%s",
                tool_name,
                call_id,
                duration_ms,
                e.code,
                e.message,
            )
            return {"ok": False, "error": e.to_dict()}

        except ValidationError as e:
            duration_ms = int((time.monotonic() - started) * 1000)
            log.warning(
                "tool.invalid name=%s call_id=%s duration_ms=%d errors=%s",
                tool_name,
                call_id,
                duration_ms,
                e.errors(),
            )
            return {
                "ok": False,
                "error": {
                    "code": "INVALID_PARAMS",
                    "message": "parameter validation failed",
                    "details": e.errors(),
                },
            }

        except hwc_exc.ClientRequestException as e:
            duration_ms = int((time.monotonic() - started) * 1000)
            log.warning(
                "tool.huaweicloud_err name=%s call_id=%s duration_ms=%d "
                "status=%s code=%s msg=%s request_id=%s",
                tool_name,
                call_id,
                duration_ms,
                getattr(e, "status_code", None),
                getattr(e, "error_code", None),
                getattr(e, "error_msg", None),
                getattr(e, "request_id", None),
            )
            return {
                "ok": False,
                "error": {
                    "code": getattr(e, "error_code", None) or "HUAWEICLOUD_ERROR",
                    "message": getattr(e, "error_msg", None) or str(e),
                    "request_id": getattr(e, "request_id", None),
                    "status_code": getattr(e, "status_code", None),
                },
            }

        except Exception as e:  # noqa: BLE001
            duration_ms = int((time.monotonic() - started) * 1000)
            log.exception(
                "tool.unexpected name=%s call_id=%s duration_ms=%d err=%s",
                tool_name,
                call_id,
                duration_ms,
                e,
            )
            return {
                "ok": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "an unexpected error occurred; check server logs",
                },
            }

    return wrapper  # type: ignore[return-value]
