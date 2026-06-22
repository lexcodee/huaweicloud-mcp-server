"""Per-request ASGI scope plumbing.

Background
----------
FastMCP tool functions receive their kwargs from the JSON-RPC ``params``
field. They do *not* automatically receive the ASGI ``scope`` of the HTTP
request that delivered the message. To support tool-level RBAC we therefore
stash the current request's scope in a :class:`contextvars.ContextVar` at
the SSE/transport boundary and read it back inside the tool body.

The scope is only valid for the duration of one request — callers MUST set
and unset (or use the ``async with set_request_scope(scope)`` form) to
avoid leaking between coroutines.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

_REQUEST_SCOPE: ContextVar[dict | None] = ContextVar("mcp_request_scope", default=None)


@contextmanager
def set_request_scope(scope: dict[str, Any]) -> Iterator[None]:
    """Bind ``scope`` to the current context for the duration of the block.

    The exit branch restores the previous token so nested binds (and any
    sequencing where the same task handles multiple requests) work correctly.
    """
    token = _REQUEST_SCOPE.set(scope)
    try:
        yield
    finally:
        _REQUEST_SCOPE.reset(token)


def current_scope() -> dict[str, Any] | None:
    """Return the ASGI scope bound by the surrounding request, or ``None``.

    Returns ``None`` for tools invoked outside an HTTP context (e.g. stdio
    transport). Callers that require an identity should treat ``None`` the
    same as "no identity" and let :class:`AuthStrategy.resolve` decide.
    """
    return _REQUEST_SCOPE.get()
