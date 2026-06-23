"""Manifest loader with three-layer override.

Precedence, lowest to highest:

1. ``enabled`` field on each service entry in ``manifest.yaml``.
2. ``MCP_GATEWAY_ENABLED_SERVICES`` env var — when present, only services
   named in the comma-separated list are enabled; everything else is forced
   off (regardless of the file's ``enabled`` field).
3. CLI ``--enable`` / ``--disable`` flags. ``--enable`` is treated like the
   env var (an explicit allow-list); ``--disable`` subtracts after the other
   two layers.

Each override layer records a ``reason`` on the service so the startup log
can explain why a service was skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class JwtConfig:
    issuer: str = "mcp-gateway"
    public_key_spec: str = ""
    audience: str | None = None
    leeway: int = 30


@dataclass
class ServiceConfig:
    name: str
    module: str
    attr: str = "mcp"
    # When set, ``attr`` is treated as a callable (factory) and invoked with
    # ``**build_kwargs`` to construct the FastMCP instance. When unset, ``attr``
    # is treated as a module-level FastMCP singleton (legacy form).
    build_kwargs: dict[str, Any] = field(default_factory=dict)
    mount_path: str = ""
    required_roles: list[str] = field(default_factory=list)
    enabled: bool = True
    skip_reason: str = ""

    def __post_init__(self) -> None:
        if not self.mount_path:
            self.mount_path = f"/{self.name}"
        if not self.mount_path.startswith("/"):
            self.mount_path = "/" + self.mount_path
        if self.mount_path.endswith("/") and self.mount_path != "/":
            self.mount_path = self.mount_path.rstrip("/")


@dataclass
class Manifest:
    jwt: JwtConfig
    services: list[ServiceConfig]

    def enabled_services(self) -> list[ServiceConfig]:
        return [s for s in self.services if s.enabled]

    def skipped_services(self) -> list[ServiceConfig]:
        return [s for s in self.services if not s.enabled]


def load_manifest(path: str | Path) -> Manifest:
    """Parse ``manifest.yaml``. Does not apply overrides — call :func:`apply_overrides` next."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"manifest at {path} must be a mapping at the top level")
    jwt_raw = raw.get("jwt") or {}
    jwt = JwtConfig(
        issuer=jwt_raw.get("issuer", "mcp-gateway"),
        public_key_spec=jwt_raw.get("public_key", ""),
        audience=jwt_raw.get("audience"),
        leeway=int(jwt_raw.get("leeway", 30)),
    )
    services_raw = raw.get("services") or []
    if not isinstance(services_raw, list):
        raise ValueError("manifest.services must be a list")
    services = [_parse_service(item) for item in services_raw]
    _ensure_unique(services)
    return Manifest(jwt=jwt, services=services)


def apply_overrides(
    manifest: Manifest,
    env_enabled: str | None,
    cli_enable: list[str] | None,
    cli_disable: list[str] | None,
) -> Manifest:
    """Return a new :class:`Manifest` with override layers applied.

    Does not mutate the input. Each disabled service records a
    human-readable ``skip_reason`` so the gateway can print why it was
    excluded at startup.
    """

    def _split(values: list[str] | None) -> set[str]:
        if not values:
            return set()
        out: set[str] = set()
        for v in values:
            for part in v.split(","):
                p = part.strip()
                if p:
                    out.add(p)
        return out

    env_allow = _split([env_enabled]) if env_enabled else None
    cli_allow = _split(cli_enable)
    cli_deny = _split(cli_disable)

    resolved: list[ServiceConfig] = []
    for original in manifest.services:
        svc = ServiceConfig(
            name=original.name,
            module=original.module,
            attr=original.attr,
            build_kwargs=dict(original.build_kwargs),
            mount_path=original.mount_path,
            required_roles=list(original.required_roles),
            enabled=original.enabled,
            skip_reason="" if original.enabled else "manifest:disabled",
        )
        if env_allow is not None:
            if svc.name in env_allow:
                if not svc.enabled:
                    svc.enabled = True
                    svc.skip_reason = ""
            else:
                svc.enabled = False
                svc.skip_reason = "env:MCP_GATEWAY_ENABLED_SERVICES"
        if cli_allow:
            if svc.name in cli_allow:
                svc.enabled = True
                svc.skip_reason = ""
            else:
                svc.enabled = False
                svc.skip_reason = "cli:--enable"
        if svc.name in cli_deny:
            svc.enabled = False
            svc.skip_reason = "cli:--disable"
        resolved.append(svc)
    return Manifest(jwt=manifest.jwt, services=resolved)


def _parse_service(item: Any) -> ServiceConfig:
    if not isinstance(item, dict):
        raise ValueError(f"each service entry must be a mapping, got {type(item).__name__}")
    if "name" not in item or "module" not in item:
        raise ValueError(f"service entry missing 'name' or 'module': {item!r}")
    return ServiceConfig(
        name=str(item["name"]),
        module=str(item["module"]),
        attr=str(item.get("attr", "mcp")),
        build_kwargs=dict(item.get("build_kwargs", {}) or {}),
        mount_path=str(item.get("mount_path", "")),
        required_roles=list(item.get("required_roles", []) or []),
        enabled=bool(item.get("enabled", True)),
    )


def _ensure_unique(services: list[ServiceConfig]) -> None:
    seen: set[str] = set()
    for svc in services:
        if svc.name in seen:
            raise ValueError(f"duplicate service name in manifest: {svc.name}")
        seen.add(svc.name)
    mounts: set[str] = set()
    for svc in services:
        if svc.mount_path in mounts:
            raise ValueError(f"duplicate mount_path in manifest: {svc.mount_path}")
        mounts.add(svc.mount_path)
