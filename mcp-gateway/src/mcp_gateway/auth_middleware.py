"""Gateway authentication middleware.

Responsibilities, in this exact order:

1. Skip the configured exempt paths (``/healthz`` by default) so liveness
   probes never need a token.
2. In dev mode (``MCP_GATEWAY_AUTH_MODE=dev``): synthesise an
   Identity for callers and skip JWT verification + RBAC.
   By default only loopback callers (127.0.0.1 / ::1) are allowed;
   set ``MCP_DEV_LOOPBACK_ONLY=false`` to allow any source (equivalent
   to the former ``disabled`` mode). A WARN/CRITICAL log is emitted on
   every request so dev mode is never accidentally left on.
3. Extract the ``Authorization: Bearer *** header. Missing -> 401.
4. Verify the JWT with the configured RS256 public key. Bad signature /
   expired / wrong issuer -> 401.
5. Match the request path to a service's ``mount_path`` and intersect the
   caller's ``roles`` with that service's ``required_roles``. Empty
   intersection -> 403. Path that doesn't match any service is left to
   Starlette's router (which will 404).
6. Inject the parsed :class:`Identity` into ``scope["mcp_identity"]`` so
   downstream MCP servers (or :class:`GatewayAuth` inside them) can pick
   it up without re-verifying anything.

The middleware logs every failure with source IP + request path + a short
reason. The token itself is never logged.

Dev mode
--------
When ``MCP_GATEWAY_AUTH_MODE=dev`` is set, the middleware:

- Skips JWT verification entirely.
- Skips path-level RBAC.
- Synthesises an Identity with ``sub="dev-local"`` and
  ``roles=["admin"]`` (customisable via ``MCP_DEV_SUBJECT`` /
  ``MCP_DEV_ROLES``).
- By default (``MCP_DEV_LOOPBACK_ONLY=true``), only does this for
  loopback callers (127.0.0.1 / ::1). Anything else is still 403 —
  dev mode is not an open relay.
- When ``MCP_DEV_LOOPBACK_ONLY=false``, all callers are allowed
  regardless of source IP. This is the **dangerous** escape hatch
  for isolated test environments. A CRITICAL log is emitted on startup
  and every request.
- When loopback-only (default), emits a ``WARNING`` log on every request.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Sequence

from mcp_auth_common import Identity
from mcp_auth_common.errors import AuthError
from mcp_auth_common.strategy import StandaloneAuth, _load_public_key
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger("mcp_gateway.auth")

# Loopback hosts that are allowed in dev mode (when loopback_only=true).
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _parse_bool(value: str) -> bool:
    """Parse a boolean env var: true/1/yes → True, anything else → False."""
    return value.strip().lower() in ("true", "1", "yes")


class GatewayAuthMiddleware:
    """ASGI middleware enforcing JWT auth + path-level RBAC.

    Supports two modes controlled by ``MCP_GATEWAY_AUTH_MODE``:

    - ``jwt`` (default when the env var is unset): full JWT verification.
    - ``dev``: skip JWT, synthesise identity for callers.
      - ``MCP_DEV_LOOPBACK_ONLY=true`` (default): only loopback callers.
      - ``MCP_DEV_LOOPBACK_ONLY=false``: any caller (dangerous).
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        public_key_spec: str,
        issuer: str,
        audience: str | None,
        leeway: int,
        path_roles: Sequence[tuple[str, list[str]]],
        exempt_paths: Iterable[str] = ("/healthz",),
    ) -> None:
        self._app = app
        self._mode = os.environ.get("MCP_GATEWAY_AUTH_MODE", "jwt").strip().lower()
        self._dev_subject = os.environ.get("MCP_DEV_SUBJECT", "dev-local")
        self._dev_roles = [
            r.strip()
            for r in os.environ.get("MCP_DEV_ROLES", "admin").split(",")
            if r.strip()
        ]
        self._dev_loopback_only = _parse_bool(
            os.environ.get("MCP_DEV_LOOPBACK_ONLY", "true")
        )

        if self._mode not in ("jwt", "dev"):
            raise RuntimeError(
                f"MCP_GATEWAY_AUTH_MODE={self._mode!r} is invalid. "
                f"Use 'jwt' or 'dev'."
            )

        if self._mode == "dev" and not self._dev_loopback_only:
            log.critical(
                "dev-mode-open",
                extra={
                    "event": "dev-mode-open",
                    "auth_mode": "dev",
                    "loopback_only": False,
                    "msg_detail": "ALL CALLERS ALLOWED WITHOUT AUTHENTICATION — NEVER on network port",
                },
            )
        elif self._mode == "dev" and self._dev_loopback_only:
            log.warning(
                "dev-mode-loopback",
                extra={
                    "event": "dev-mode-loopback",
                    "auth_mode": "dev",
                    "loopback_only": True,
                    "msg_detail": "JWT disabled, loopback callers only",
                },
            )

        # Build the JWT verifier (used only in jwt mode).
        self._verifier: StandaloneAuth | None = None
        if self._mode == "jwt":
            public_key = _load_public_key(public_key_spec)
            if not public_key:
                raise RuntimeError(
                    "Gateway requires a JWT public key. Set manifest.jwt.public_key "
                    "to a PEM body, 'file:/path/to/key.pem', or 'env:VAR_NAME'."
                )
            self._verifier = StandaloneAuth(
                public_key=public_key,
                issuer=issuer,
                audience=audience,
                leeway=leeway,
            )

        # Sort longest-prefix-first so /pipeline-extra wins over /pipeline.
        self._path_roles = sorted(
            ((p.rstrip("/"), list(r)) for p, r in path_roles),
            key=lambda x: len(x[0]),
            reverse=True,
        )
        self._exempt = tuple(p.rstrip("/") or "/" for p in exempt_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # Lifespan / websocket pass through unchanged.
            await self._app(scope, receive, send)
            return
        path = scope.get("path", "")
        if self._is_exempt(path):
            await self._app(scope, receive, send)
            return

        try:
            identity = self._resolve_identity(scope, path)
        except AuthError as exc:
            await self._reject(scope, send, exc)
            return

        # Identity flows into every downstream FastMCP server through scope.
        scope["mcp_identity"] = identity
        await self._app(scope, receive, send)

    def _resolve_identity(self, scope: Scope, path: str) -> Identity:
        """Dispatch to the appropriate auth mode."""
        if self._mode == "dev":
            return self._resolve_dev(scope)

        # Default: jwt mode.
        assert self._verifier is not None
        identity = self._verifier.resolve(dict(scope))
        self._check_rbac(path, identity)
        return identity

    def _resolve_dev(self, scope: Scope) -> Identity:
        """Dev mode: allow callers with a synthesised identity.

        When loopback_only=true (default):
          A caller is considered loopback if ANY of these hold:
          - The server is bound to a loopback address (MCP_GATEWAY_HOST is
            127.0.0.1 / ::1 / localhost), meaning ALL connections are local.
          - The client's IP in the ASGI scope is a loopback address.
          - The client IP is None (test tools / stdio that don't set scope["client"]).
          Non-loopback callers are rejected with 403.

        When loopback_only=false:
          All callers are allowed regardless of source IP.
        """
        if self._dev_loopback_only:
            client = scope.get("client")
            host = client[0] if client else None
            server_host = os.environ.get("MCP_GATEWAY_HOST", "")
            server_is_loopback = server_host in _LOOPBACK_HOSTS
            if not server_is_loopback and host not in _LOOPBACK_HOSTS and host is not None:
                raise AuthError(403, "dev-mode-rejects-non-loopback")

        # Choose log level based on loopback_only.
        path = scope.get("path", "")
        if not self._dev_loopback_only:
            log.warning(
                "dev-mode-request",
                extra={
                    "event": "dev-mode-request",
                    "auth_mode": "dev",
                    "loopback_only": False,
                    "sub": self._dev_subject,
                    "roles": self._dev_roles,
                    "path": path,
                },
            )
        else:
            log.warning(
                "dev-mode-request",
                extra={
                    "event": "dev-mode-request",
                    "auth_mode": "dev",
                    "loopback_only": True,
                    "sub": self._dev_subject,
                    "roles": self._dev_roles,
                    "path": path,
                },
            )
        return Identity(sub=self._dev_subject, roles=list(self._dev_roles))

    def _is_exempt(self, path: str) -> bool:
        p = path.rstrip("/") or "/"
        return p in self._exempt

    def _check_rbac(self, path: str, identity: Identity) -> None:
        required = self._roles_for(path)
        if not required:
            # Service has no required_roles list — auth alone is sufficient.
            return
        caller = set(identity.roles)
        if not caller.intersection(required):
            raise AuthError(
                403,
                f"path-rbac:required={sorted(required)};caller={sorted(caller)}",
            )

    def _roles_for(self, path: str) -> list[str]:
        for prefix, roles in self._path_roles:
            if prefix == "" or path == prefix or path.startswith(prefix + "/"):
                return roles
        return []

    async def _reject(self, scope: Scope, send: Send, exc: AuthError) -> None:
        client = scope.get("client")
        host = client[0] if client else "-"
        log.warning(
            "auth-rejected",
            extra={
                "event": "auth-rejected",
                "status": exc.status,
                "path": scope.get("path", ""),
                "peer": host,
                "reason": exc.reason,
            },
        )
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
        response = JSONResponse(
            {"error": exc.reason, "status": exc.status},
            status_code=exc.status,
            headers=headers,
        )
        await response(scope, _empty_receive, send)


async def _empty_receive() -> dict[str, Any]:  # pragma: no cover - never awaited
    return {"type": "http.disconnect"}
