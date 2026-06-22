"""Shared MCP authentication primitives.

Public surface:

* :class:`Identity` — the subject + roles + tenant carried through the system.
* :class:`AuthStrategy` / :class:`AutoAuth` — auto-detect strategy that
  reads gateway identity from scope or synthesises a dev identity with WARN.
* :func:`create_auth_strategy` — zero-config factory, returns AutoAuth.
* :func:`require_role` — raise :class:`AuthError` when an identity lacks a role.
* :func:`set_request_scope` / :func:`current_scope` — contextvar plumbing the
  MCP tool body uses to recover the per-request ASGI scope without changing
  the tool signature.
"""
from __future__ import annotations

from .errors import AuthError
from .identity import Identity
from .scope import current_scope, set_request_scope
from .strategy import (
    DEFAULT_ROLE_HIERARCHY,
    AutoAuth,
    AuthStrategy,
    create_auth_strategy,
    require_role,
)

__all__ = [
    "AuthError",
    "AuthStrategy",
    "AutoAuth",
    "DEFAULT_ROLE_HIERARCHY",
    "Identity",
    "create_auth_strategy",
    "current_scope",
    "require_role",
    "set_request_scope",
]
