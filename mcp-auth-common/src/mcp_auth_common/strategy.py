"""AuthStrategy implementations.

Auto-detect logic
----------------
``create_auth_strategy()`` returns an :class:`AutoAuth` instance that
decides at **resolve time** (per-request), not at startup:

1. If the ASGI scope carries ``scope["mcp_identity"]`` (injected by the
   gateway middleware) → use it. This is the **gateway mode** path.
2. Otherwise → synthesise a dev Identity and emit a ``WARNING`` log.
   This covers **stdio**, **standalone SSE without JWT**, and any
   scenario where the server is not behind the gateway.

There is no ``MCP_AUTH_MODE`` environment variable. The detection is
fully automatic and zero-config:

* Behind the gateway → authenticated (gateway already verified JWT).
* Not behind the gateway → unauthenticated with a loud warning.

The warning is the safety net: it makes "no auth" visible in logs so
an operator can spot an accidentally exposed server.

``resolve()`` is synchronous because all work is in-process (dict lookup
or object construction). This lets existing synchronous tool bodies call
it without ``await``, which matters because the three MCP servers' tools
are all sync ``@wrap_tool`` callables.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable

from .errors import AuthError
from .identity import Identity

log = logging.getLogger("mcp_auth_common")


# Hierarchy used by :func:`require_role`. ``admin`` automatically satisfies
# ``operator`` and ``readonly``; ``operator`` satisfies ``readonly``.
DEFAULT_ROLE_HIERARCHY: dict[str, set[str]] = {
    "admin": {"admin", "operator", "readonly"},
    "operator": {"operator", "readonly"},
    "readonly": {"readonly"},
}


class AuthStrategy(ABC):
    """Resolve an :class:`Identity` from an ASGI ``scope``.

    The method is intentionally synchronous: the work is either a single
    dict lookup (gateway mode) or object construction (dev fallback). No
    network I/O happens here. Keeping it sync lets existing synchronous
    MCP tool bodies call it without an ``await``.
    """

    @abstractmethod
    def resolve(self, scope: dict[str, Any] | None) -> Identity:
        ...


class AutoAuth(AuthStrategy):
    """Auto-detect auth mode at resolve time.

    Per-request decision:

    1. ``scope["mcp_identity"]`` exists → gateway mode: use it.
    2. Otherwise → dev fallback: synthesise an Identity with a WARNING.

    The dev subject and roles are configurable via ``MCP_DEV_SUBJECT``
    and ``MCP_DEV_ROLES`` environment variables (defaults: ``dev-local``
    and ``admin``).
    """

    def __init__(
        self,
        dev_subject: str = "dev-local",
        dev_roles: Iterable[str] = ("admin",),
    ) -> None:
        self._dev_subject = dev_subject
        self._dev_roles = list(dev_roles)
        self._warned = False  # emit startup-style warning once

    def resolve(self, scope: dict[str, Any] | None) -> Identity:
        # 1. Gateway mode: scope carries an identity from the middleware.
        if scope and "mcp_identity" in scope:
            identity = scope["mcp_identity"]
            if isinstance(identity, Identity):
                return identity
            # Defensive: someone wrote a dict instead of the model.
            try:
                return Identity.model_validate(identity)
            except Exception as exc:  # noqa: BLE001
                raise AuthError(
                    401, f"invalid-identity:{exc.__class__.__name__}"
                ) from exc

        # 2. Dev fallback: no gateway identity → synthesise + warn.
        if not self._warned:
            log.warning(
                "⚠ No gateway identity found. Synthesising dev identity "
                "sub=%s roles=%s. This means the server is NOT behind the "
                "MCP gateway with JWT auth. If this is a production server, "
                "it is running WITHOUT authentication. If this is local "
                "development, this is expected and safe.",
                self._dev_subject,
                self._dev_roles,
            )
            self._warned = True
        else:
            log.debug(
                "dev-identity: sub=%s roles=%s",
                self._dev_subject,
                self._dev_roles,
            )
        return Identity(sub=self._dev_subject, roles=list(self._dev_roles))


# ---------------------------------------------------------------------------
# Legacy strategy classes — kept for backward compatibility and for the
# gateway middleware which uses StandaloneAuth internally.
# ---------------------------------------------------------------------------

class GatewayAuth(AuthStrategy):
    """Read identity from scope["mcp_identity"]. Used by gateway middleware tests."""

    def resolve(self, scope: dict[str, Any] | None) -> Identity:
        if not scope:
            raise AuthError(401, "missing-asgi-scope")
        identity = scope.get("mcp_identity")
        if identity is None:
            raise AuthError(401, "missing-identity-gateway-mode")
        if isinstance(identity, Identity):
            return identity
        try:
            return Identity.model_validate(identity)
        except Exception as exc:  # noqa: BLE001
            raise AuthError(401, f"invalid-identity:{exc.__class__.__name__}") from exc


class StandaloneAuth(AuthStrategy):
    """Verify JWT with RS256 public key. Used by gateway middleware internally."""

    def __init__(
        self,
        public_key: str,
        issuer: str = "mcp-gateway",
        audience: str | None = None,
        leeway: int = 30,
    ) -> None:
        import jwt as _jwt
        self._jwt = _jwt
        self._public_key = public_key
        self._issuer = issuer
        self._audience = audience
        self._leeway = leeway

    def resolve(self, scope: dict[str, Any] | None) -> Identity:
        if not scope:
            raise AuthError(401, "missing-asgi-scope")
        token = _extract_bearer(scope)
        if not token:
            raise AuthError(401, "missing-bearer-token")
        try:
            payload = self._jwt.decode(
                token,
                self._public_key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway,
            )
        except Exception as exc:  # noqa: BLE001
            raise AuthError(401, f"jwt-invalid:{exc.__class__.__name__}") from exc
        return _identity_from_claims(payload)


def require_role(
    identity: Identity,
    required: str,
    hierarchy: dict[str, set[str]] | None = None,
) -> None:
    """Raise :class:`AuthError` (403) when ``identity`` does not satisfy ``required``.

    Each role the caller holds is expanded through ``hierarchy`` (default
    admin ⊃ operator ⊃ readonly) — i.e. an ``admin`` caller satisfies
    ``required="readonly"`` without needing the ``readonly`` role explicitly.
    Unknown role names in ``identity.roles`` are simply ignored.
    """
    table = hierarchy or DEFAULT_ROLE_HIERARCHY
    satisfied: set[str] = set()
    for role in identity.roles:
        satisfied.update(table.get(role, {role}))
    if required not in satisfied:
        raise AuthError(
            403,
            f"role-required:{required};caller-has:{sorted(identity.roles)}",
        )


def create_auth_strategy() -> AuthStrategy:
    """Create the auto-detect auth strategy.

    Returns an :class:`AutoAuth` instance that resolves identity
    automatically:

    - Behind gateway → reads ``scope["mcp_identity"]`` (authenticated).
    - Not behind gateway → synthesises dev identity with WARNING.

    No environment variables required. Configurable via:

    - ``MCP_DEV_SUBJECT``: subject for synthesised identity (default: dev-local).
    - ``MCP_DEV_ROLES``: comma-separated roles (default: admin).
    """
    return AutoAuth(
        dev_subject=os.environ.get("MCP_DEV_SUBJECT", "dev-local"),
        dev_roles=tuple(
            r.strip()
            for r in os.environ.get("MCP_DEV_ROLES", "admin").split(",")
            if r.strip()
        ),
    )


# ---------------------------------------------------------------------------
# Internal helpers used by the gateway middleware
# ---------------------------------------------------------------------------

def _extract_bearer(scope: dict[str, Any]) -> str | None:
    headers = scope.get("headers") or []
    for name, value in headers:
        if name == b"authorization":
            text = value.decode("latin-1") if isinstance(value, (bytes, bytearray)) else str(value)
            parts = text.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1].strip()
            return None
    return None


def _identity_from_claims(payload: dict[str, Any]) -> Identity:
    roles = payload.get("roles") or []
    if isinstance(roles, str):
        roles = [r for r in roles.replace(",", " ").split() if r]
    return Identity(
        sub=str(payload.get("sub", "")),
        roles=list(roles),
        tenant=str(payload.get("tenant", "") or payload.get("tid", "")),
        iat=payload.get("iat"),
        exp=payload.get("exp"),
    )


def _load_public_key(spec: str | None) -> str | None:
    """Resolve a key spec to PEM text.

    Three accepted forms:
      * ``file:/abs/path.pem`` or ``file:///abs/path.pem`` — read from disk.
      * ``env:VAR_NAME`` — read the named environment variable.
      * Anything else — taken verbatim as the PEM body.
    """
    if not spec:
        return None
    if spec.startswith("file:"):
        path = spec[len("file:") :]
        if path.startswith("//"):
            path = path[2:]
        return Path(path).read_text(encoding="utf-8")
    if spec.startswith("env:"):
        var = spec[len("env:") :]
        value = os.environ.get(var)
        if value is None:
            raise RuntimeError(f"Public key env var {var!r} is not set")
        return value
    return spec
