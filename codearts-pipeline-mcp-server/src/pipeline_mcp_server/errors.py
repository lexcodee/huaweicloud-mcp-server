"""Tool-level error type, ``@wrap_tool`` decorator, and PendingActions store.

Every tool returns one of:
    {"ok": True,  "data": {...}}
    {"ok": False, "error": {"code": "...", "message": "...", ...}}
"""
from __future__ import annotations

import functools
import logging
import time
import uuid
from typing import Any, Callable, TypeVar

from pydantic import ValidationError

try:
    from huaweicloudsdkcore.exceptions import exceptions as hwc_exc
except Exception:  # pragma: no cover — only happens when SDK absent
    hwc_exc = None  # type: ignore

log = logging.getLogger("pipeline_mcp_server.tools")
F = TypeVar("F", bound=Callable[..., Any])


class ToolError(Exception):
    """Raised inside tool bodies. Convertible to the MCP error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        request_id: str | None = None,
        hint: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = request_id
        self.hint = hint
        self.status_code = status_code

    def to_dict(self) -> dict:
        out: dict = {"code": self.code, "message": self.message}
        if self.request_id:
            out["request_id"] = self.request_id
        if self.hint:
            out["hint"] = self.hint
        if self.status_code is not None:
            out["status_code"] = self.status_code
        return out


def _params_summary(kwargs: dict) -> dict:
    """Compact, secret-free summary of a tool's keyword args."""
    summary: dict = {}
    for k, v in kwargs.items():
        if k in {"password", "secret", "ak", "sk", "access_key", "secret_key"}:
            summary[k] = "***"
        elif isinstance(v, list):
            summary[k] = f"<list len={len(v)}>"
        elif isinstance(v, dict):
            summary[k] = f"<dict keys={len(v)}>"
        elif isinstance(v, str) and len(v) > 80:
            summary[k] = v[:60] + "..."
        else:
            summary[k] = v
    return summary


def wrap_tool(func: F) -> F:
    """Standardise return shape, log lifecycle, and translate exceptions."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        call_id = uuid.uuid4().hex[:8]
        tool_name = func.__name__
        started = time.monotonic()
        log.info(
            "tool.start name=%s call_id=%s params=%s",
            tool_name, call_id, _params_summary(kwargs),
        )
        try:
            data = func(*args, **kwargs)
            ms = int((time.monotonic() - started) * 1000)
            log.info("tool.ok name=%s call_id=%s duration_ms=%d", tool_name, call_id, ms)
            return {"ok": True, "data": data}

        except ToolError as e:
            ms = int((time.monotonic() - started) * 1000)
            log.warning(
                "tool.err name=%s call_id=%s duration_ms=%d code=%s",
                tool_name, call_id, ms, e.code,
            )
            return {"ok": False, "error": e.to_dict()}

        except ValidationError as e:
            ms = int((time.monotonic() - started) * 1000)
            log.warning("tool.invalid name=%s call_id=%s duration_ms=%d", tool_name, call_id, ms)
            return {
                "ok": False,
                "error": {
                    "code": "INVALID_PARAMS",
                    "message": "parameter validation failed",
                    "details": e.errors(),
                },
            }

        except Exception as e:  # noqa: BLE001
            # Inspect for SDK-native exception by attribute shape — avoids hard
            # dependency on the SDK's exception module if it's ever absent.
            if hwc_exc is not None and isinstance(e, hwc_exc.ClientRequestException):
                ms = int((time.monotonic() - started) * 1000)
                log.warning(
                    "tool.sdk_err name=%s call_id=%s duration_ms=%d "
                    "status=%s code=%s request_id=%s",
                    tool_name, call_id, ms,
                    getattr(e, "status_code", None),
                    getattr(e, "error_code", None),
                    getattr(e, "request_id", None),
                )
                return {
                    "ok": False,
                    "error": {
                        "code": getattr(e, "error_code", None) or "SDK_ERROR",
                        "message": getattr(e, "error_msg", None) or str(e),
                        "request_id": getattr(e, "request_id", None),
                        "status_code": getattr(e, "status_code", None),
                    },
                }

            ms = int((time.monotonic() - started) * 1000)
            log.exception(
                "tool.unexpected name=%s call_id=%s duration_ms=%d",
                tool_name, call_id, ms,
            )
            return {
                "ok": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "an unexpected error occurred; check server logs",
                },
            }

    return wrapper  # type: ignore[return-value]


# ============================================================
# Two-phase destructive operation approval
# ============================================================

_APPROVAL_TTL_SECONDS = 120


class PendingActions:
    """Thread-safe store for pending destructive operations awaiting approval."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def put(
        self,
        action_label: str,
        preview: dict[str, Any],
        execute_fn: Callable[[], dict],
    ) -> str:
        """Store a pending action and return its approval_id."""
        approval_id = f"apr-{uuid.uuid4().hex[:12]}"
        self._store[approval_id] = {
            "action": action_label,
            "preview": preview,
            "execute_fn": execute_fn,
            "created_at": time.monotonic(),
        }
        log.info("pending_action.put approval_id=%s action=%s", approval_id, action_label)
        return approval_id

    def pop(self, approval_id: str) -> dict[str, Any]:
        """Retrieve and remove a pending action. Raises ToolError if not found/expired."""
        self._expire()
        entry = self._store.pop(approval_id, None)
        if entry is None:
            raise ToolError(
                code="APPROVAL_NOT_FOUND",
                message=(
                    f"No pending action with approval_id={approval_id!r}. "
                    "It may have expired (TTL=120s) or already been consumed."
                ),
                hint="Re-issue the original destructive operation to get a new approval_id.",
            )
        age = time.monotonic() - entry["created_at"]
        if age > _APPROVAL_TTL_SECONDS:
            raise ToolError(
                code="APPROVAL_EXPIRED",
                message=(
                    f"Approval {approval_id!r} has expired ({age:.0f}s > {_APPROVAL_TTL_SECONDS}s TTL)."
                ),
                hint="Re-issue the original destructive operation to get a new approval_id.",
            )
        log.info("pending_action.pop approval_id=%s action=%s age=%.1fs", approval_id, entry["action"], age)
        return entry

    def _expire(self) -> None:
        """Remove entries older than TTL."""
        now = time.monotonic()
        expired = [
            k for k, v in self._store.items()
            if now - v["created_at"] > _APPROVAL_TTL_SECONDS
        ]
        for k in expired:
            log.info("pending_action.expire approval_id=%s action=%s", k, self._store[k]["action"])
            del self._store[k]


# Module-level singleton
pending_actions = PendingActions()
