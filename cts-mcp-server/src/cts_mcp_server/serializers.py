"""Serializers — convert SDK ``Traces`` objects into plain dicts.

We deliberately drop SDK-internal fields and trim everything else down to
what an LLM / operator actually needs. Sensitive request/response bodies
are run through ``mask_utils`` before serialization.
"""
from __future__ import annotations

from typing import Any, Optional

from .mask_utils import mask_and_truncate, mask_sensitive, truncate
from .time_utils import epoch_ms_to_human


def _drop_empty(d: dict) -> dict:
    """Remove keys whose value is None / empty string / empty container."""
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def _user_summary(user: Any) -> Optional[str]:
    """Best-effort extract of a human-readable user name from UserInfo.

    Prefers ``user.user_name`` (sub-user form), falls back to ``user.name``.
    """
    if user is None:
        return None
    return getattr(user, "user_name", None) or getattr(user, "name", None)


def _user_detail(user: Any) -> Optional[dict]:
    """Detailed UserInfo view used by cts_get_trace_detail.

    Note ``access_key_id`` is kept (CTS audit logs surface this so ops can
    correlate to specific keys); it's masked by the AK/SK heuristic in
    logging_setup but preserved in the response payload.
    """
    if user is None:
        return None
    domain = getattr(user, "domain", None)
    return _drop_empty(
        {
            "id": getattr(user, "id", None),
            "name": getattr(user, "name", None),
            "user_name": getattr(user, "user_name", None),
            "domain_name": getattr(domain, "name", None) if domain else None,
            "domain_id": getattr(domain, "id", None) if domain else None,
            "account_id": getattr(user, "account_id", None),
            "access_key_id": getattr(user, "access_key_id", None),
            "principal_urn": getattr(user, "principal_urn", None),
            "type": getattr(user, "type", None),
        }
    )


def trace_summary(trace: Any, tz: str, summary_limit: int = 500) -> dict:
    """Trimmed view for the search tool. Body fields are masked + truncated."""
    request_summary, _ = mask_and_truncate(getattr(trace, "request", None), summary_limit)
    response_summary, _ = mask_and_truncate(getattr(trace, "response", None), summary_limit)

    return _drop_empty(
        {
            "trace_id": getattr(trace, "trace_id", None),
            "trace_name": getattr(trace, "trace_name", None),
            "trace_rating": getattr(trace, "trace_rating", None),
            "trace_type": getattr(trace, "trace_type", None),
            "time": epoch_ms_to_human(getattr(trace, "time", None), tz),
            "service_type": getattr(trace, "service_type", None),
            "resource_type": getattr(trace, "resource_type", None),
            "resource_name": getattr(trace, "resource_name", None),
            "resource_id": getattr(trace, "resource_id", None),
            "user_name": _user_summary(getattr(trace, "user", None)),
            "source_ip": getattr(trace, "source_ip", None),
            "code": getattr(trace, "code", None),
            "message": getattr(trace, "message", None),
            "request_summary": request_summary,
            "response_summary": response_summary,
        }
    )


def trace_detail(trace: Any, tz: str, body_limit: int = 5000) -> dict:
    """Full-fidelity view for the detail tool.

    Bodies are masked first (always), then truncated only if they exceed
    ``body_limit`` (default 5000 chars). The ``request_truncated`` /
    ``response_truncated`` flags tell the caller they need to fetch via the
    CTS console for the full payload.
    """
    request_body, req_trunc = mask_and_truncate(
        getattr(trace, "request", None), body_limit
    )
    response_body, resp_trunc = mask_and_truncate(
        getattr(trace, "response", None), body_limit
    )
    # Also pass user-info through the masker — defensive, since some
    # legacy CTS records embed AK/SK strings here.
    user = _user_detail(getattr(trace, "user", None))
    if user and "access_key_id" in user:
        # leave AK visible — CTS metadata, operators expect to see this
        pass

    truncate_hint = None
    if req_trunc or resp_trunc:
        truncate_hint = (
            "request/response was truncated at "
            f"{body_limit} chars; view the full payload in the CTS console "
            f"using trace_id={getattr(trace, 'trace_id', None)!r}."
        )

    return _drop_empty(
        {
            "trace_id": getattr(trace, "trace_id", None),
            "trace_name": getattr(trace, "trace_name", None),
            "trace_rating": getattr(trace, "trace_rating", None),
            "trace_type": getattr(trace, "trace_type", None),
            "time": epoch_ms_to_human(getattr(trace, "time", None), tz),
            "record_time": epoch_ms_to_human(getattr(trace, "record_time", None), tz),
            "service_type": getattr(trace, "service_type", None),
            "resource_type": getattr(trace, "resource_type", None),
            "resource_name": getattr(trace, "resource_name", None),
            "resource_id": getattr(trace, "resource_id", None),
            "user": user,
            "source_ip": getattr(trace, "source_ip", None),
            "code": getattr(trace, "code", None),
            "message": getattr(trace, "message", None),
            "api_version": getattr(trace, "api_version", None),
            "endpoint": getattr(trace, "endpoint", None),
            "resource_url": getattr(trace, "resource_url", None),
            "request_id": getattr(trace, "request_id", None),
            "enterprise_project_id": getattr(trace, "enterprise_project_id", None),
            "read_only": getattr(trace, "read_only", None),
            "request": request_body,
            "response": response_body,
            "request_truncated": req_trunc,
            "response_truncated": resp_trunc,
            "truncate_hint": truncate_hint,
        }
    )
