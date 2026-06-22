"""ASGI gateway: mount many FastMCP SSE apps on one uvicorn port.

Key pieces, each protecting against a documented MCP-SDK gotcha:

* :func:`_mount_one` calls ``fastmcp_instance.sse_app(mount_path=...)``.
  Passing the prefix to ``sse_app`` makes FastMCP build the SSE
  ``event: endpoint`` callback URL with ``/ecs`` (or whatever) baked in —
  the client's subsequent POST then lands at ``/ecs/messages/`` instead of
  bare ``/messages/`` and the session works. This is the documented fix
  for `mcp` <= 1.x's known mount-prefix bug; we rely on the public
  ``sse_app(mount_path=...)`` parameter rather than mutating
  ``settings.mount_path`` directly.

* :func:`_combined_lifespan` enters every mounted FastMCP's session
  manager inside one ``AsyncExitStack``. Without this, the SDK only
  initialises the first sub-app's session machinery, so the second and
  third services silently fail to handle messages.

* :class:`_ScopeBinderMiddleware` ties the per-request ASGI ``scope`` into
  the ``mcp_auth_common`` contextvar so tools running inside the
  FastMCP server can call :func:`mcp_auth_common.current_scope` to recover
  the identity the gateway injected.
"""
from __future__ import annotations

import importlib
import logging
import os
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from mcp.server.fastmcp import FastMCP
from mcp_auth_common.scope import set_request_scope
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .auth_middleware import GatewayAuthMiddleware
from .manifest_loader import Manifest, ServiceConfig, apply_overrides, load_manifest

log = logging.getLogger("mcp_gateway.gateway")

DEFAULT_MANIFEST_PATH = os.environ.get("MCP_GATEWAY_MANIFEST", "manifest.yaml")


def build_app(
    manifest_path: str | os.PathLike | None = None,
    *,
    cli_enable: list[str] | None = None,
    cli_disable: list[str] | None = None,
) -> Starlette:
    """Construct the Starlette app from manifest + overrides.

    Parameters here mirror the CLI: ``--manifest``, ``--enable``,
    ``--disable``. Env var ``MCP_GATEWAY_ENABLED_SERVICES`` is read directly.
    """
    manifest_path = Path(manifest_path or DEFAULT_MANIFEST_PATH)
    manifest = load_manifest(manifest_path)
    manifest = apply_overrides(
        manifest,
        env_enabled=os.environ.get("MCP_GATEWAY_ENABLED_SERVICES"),
        cli_enable=cli_enable,
        cli_disable=cli_disable,
    )

    mounted: list[tuple[ServiceConfig, FastMCP]] = []
    routes: list[Any] = []
    for svc in manifest.enabled_services():
        instance = _resolve_fastmcp(svc)
        sse_app = _mount_one(svc, instance)
        # Wrap each sub-app in the scope-binder so tools running inside that
        # FastMCP can recover the identity from a contextvar without needing
        # a ``ctx: Context`` parameter.
        routes.append(Mount(svc.mount_path, app=_ScopeBinderMiddleware(sse_app)))
        mounted.append((svc, instance))
        log.info(
            "service-mounted",
            extra={"event": "service-mounted", "service": svc.name, "mount_path": svc.mount_path, "svc_module": svc.module},
        )

    for skipped in manifest.skipped_services():
        log.info(
            "service-skipped",
            extra={"event": "service-skipped", "service": skipped.name, "reason": skipped.skip_reason or "manifest:disabled"},
        )

    routes.append(Route("/healthz", _make_healthz(manifest), methods=["GET"]))

    app = Starlette(
        debug=False,
        routes=routes,
        lifespan=_combined_lifespan_factory(mounted),
    )

    app.add_middleware(
        GatewayAuthMiddleware,
        public_key_spec=manifest.jwt.public_key_spec,
        issuer=manifest.jwt.issuer,
        audience=manifest.jwt.audience,
        leeway=manifest.jwt.leeway,
        path_roles=[(s.mount_path, s.required_roles) for s, _ in mounted],
        exempt_paths=("/healthz",),
    )

    log.info(
        "gateway-ready",
        extra={
            "event": "gateway-ready",
            "mounted": [s.name for s, _ in mounted],
            "skipped": [s.name for s in manifest.skipped_services()],
        },
    )
    return app


def _resolve_fastmcp(svc: ServiceConfig) -> FastMCP:
    """Dynamic ``module.attr`` lookup that gives a useful error if the symbol is missing."""
    module = importlib.import_module(svc.module)
    instance = getattr(module, svc.attr, None)
    if instance is None:
        raise RuntimeError(
            f"service {svc.name!r}: module {svc.module!r} has no attribute {svc.attr!r}. "
            f"Make sure the server module exposes the FastMCP instance — e.g. "
            f"`from .server import mcp` in __init__.py."
        )
    if not isinstance(instance, FastMCP):
        raise RuntimeError(
            f"service {svc.name!r}: attribute {svc.attr!r} is not a FastMCP instance "
            f"(got {type(instance).__name__})."
        )
    return instance


def _mount_one(svc: ServiceConfig, instance: FastMCP) -> ASGIApp:
    """Build the sub-app with the prefix baked into the SSE endpoint callback.

    ``sse_app(mount_path=...)`` is the supported public API as of
    ``mcp`` 1.x. Internally it stores the prefix on
    ``settings.mount_path`` and uses it when emitting the SSE
    ``event: endpoint`` URI. Without it the URI would be bare
    ``/messages/?session_id=...`` and POST traffic from the client would
    miss the Mount prefix entirely.
    """
    return instance.sse_app(mount_path=svc.mount_path)


def _combined_lifespan_factory(
    mounted: list[tuple[ServiceConfig, FastMCP]],
):
    """Enter every mounted FastMCP's session manager inside one ExitStack.

    FastMCP exposes ``session_manager`` for the Streamable-HTTP transport.
    The SSE transport does not strictly require entering it for messages
    to flow, but the same instance is also the place where lifespan
    context (``settings.lifespan``) is run, so iterating all of them under
    one ``AsyncExitStack`` is the safe pattern recommended for multi-server
    Starlette mounts. Errors during entry abort startup with a clear log
    rather than letting the process come up half-initialised.
    """

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[dict]:
        async with AsyncExitStack() as stack:
            for svc, instance in mounted:
                try:
                    mgr = instance.session_manager  # noqa: F841 - touch only
                except RuntimeError:
                    # SSE-only servers never construct a StreamableHTTPSessionManager,
                    # which is fine — nothing to enter for that service.
                    log.debug("service=%s has no streamable session manager (sse-only)", svc.name)
                    continue
                else:
                    try:
                        await stack.enter_async_context(mgr.run())
                        log.debug("service=%s session manager entered", svc.name)
                    except Exception:  # noqa: BLE001
                        log.exception("service=%s lifespan entry failed", svc.name)
                        raise
            yield {}

    return lifespan


def _make_healthz(manifest: Manifest):
    async def healthz(_request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "mounted": [
                    {"name": s.name, "mount_path": s.mount_path, "required_roles": s.required_roles}
                    for s in manifest.enabled_services()
                ],
                "skipped": [
                    {"name": s.name, "reason": s.skip_reason or "manifest:disabled"}
                    for s in manifest.skipped_services()
                ],
            }
        )

    return healthz


class _ScopeBinderMiddleware:
    """Bind the per-request ASGI scope into ``mcp_auth_common``'s contextvar.

    Without this, tool functions running inside the FastMCP sub-app would
    have to thread the scope through their signatures (FastMCP's tool
    signature is determined by the user's function — we can't slip in
    a hidden parameter). The contextvar pattern keeps the tool body free
    of plumbing while still giving it access to the gateway-injected
    identity.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with set_request_scope(dict(scope)):
            await self.app(scope, receive, send)


# Module-level app for ``uvicorn mcp_gateway.gateway:app``.
def _lazy_app() -> Starlette:
    return build_app()


# We deliberately avoid evaluating the app at import time so test code can
# call ``build_app(path)`` with a custom manifest. uvicorn's app loader
# resolves the symbol on first request when ``--factory`` is used, or
# imports it eagerly when used as ``mcp_gateway.gateway:app`` — the cli.py
# entrypoint uses ``--factory`` to keep behaviour predictable.
app = _lazy_app  # callable factory; uvicorn picks it up with --factory
