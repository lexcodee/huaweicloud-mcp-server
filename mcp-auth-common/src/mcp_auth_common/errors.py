"""Typed authentication errors.

These are raised by AuthStrategy implementations and by the gateway
middleware. Each carries an HTTP-style status code so the middleware can
translate it into a 401/403 response, and a short reason that is safe to log
(token contents must never appear here).
"""
from __future__ import annotations


class AuthError(Exception):
    """Authentication / authorization failure.

    ``status`` is intentionally an HTTP-style code (401 unauthenticated,
    403 forbidden) so the gateway middleware does not need a separate
    mapping table — it forwards ``status`` verbatim. The ``reason`` is
    short, free of secrets, and safe to emit in audit logs.
    """

    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"AuthError(status={self.status}, reason={self.reason!r})"
