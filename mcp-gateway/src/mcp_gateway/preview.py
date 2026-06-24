"""Manifest preview / dry-run.

``mcp-gateway config preview`` builds every enabled service exactly the way the
gateway would, then prints the resulting mount plan with the full tool list per
mount — including which tools were filtered out by ``include`` / ``exclude``
globs and which pattern matched. Nothing is bound, no network calls are made.

The command is read-only and exits 0 on success, 1 if a service fails to build
(e.g. unknown service id, factory raised). Non-zero exit makes it suitable for
CI pre-merge checks on manifest changes.

Two output formats:

* ``text`` (default) — human-friendly, optional ANSI colour when stdout is a TTY.
* ``json`` — stable schema for downstream tooling (linters, dashboards).
"""
from __future__ import annotations

import contextlib
import fnmatch
import io
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .manifest_loader import (
    Manifest,
    ServiceConfig,
    apply_overrides,
    load_manifest,
)

# Env vars whose absence makes huaweicloud_mcp.load_settings() exit. We stub
# them with safe placeholders for the duration of a preview build — the
# factory only inspects the values during tool registration, never at I/O time.
_PLACEHOLDER_ENV = {
    "HUAWEICLOUD_ACCESS_KEY_ID": "PREVIEW" + "X" * 17,
    "HUAWEICLOUD_SECRET_ACCESS_KEY": "PREVIEW" + "Y" * 33,
    "HUAWEICLOUD_REGION": "preview-region",
    "HUAWEICLOUD_PROJECT_ID": "00000000000000000000000000000000",
}

# Filter kwargs we know about. Anything else passed in build_kwargs is left
# untouched when computing the baseline (unfiltered) build.
_FILTER_KWARGS = ("include", "exclude")


@dataclass
class ToolReport:
    name: str
    kept: bool
    reason: str = ""  # the pattern that filtered it, when kept=False


@dataclass
class ServiceReport:
    name: str
    mount_path: str
    module: str
    attr: str
    enabled: bool
    skip_reason: str = ""
    required_roles: list[str] = field(default_factory=list)
    build_kwargs: dict[str, Any] = field(default_factory=dict)
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    tools: list[ToolReport] = field(default_factory=list)
    build_error: str = ""
    factory_form: str = "factory"  # "factory" or "singleton"

    @property
    def kept_tools(self) -> list[ToolReport]:
        return [t for t in self.tools if t.kept]

    @property
    def filtered_tools(self) -> list[ToolReport]:
        return [t for t in self.tools if not t.kept]


@dataclass
class PreviewReport:
    manifest_path: str
    jwt_issuer: str
    services: list[ServiceReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(not s.build_error for s in self.services)


# --- env stub helper -----------------------------------------------------


@contextlib.contextmanager
def _stub_env():
    """Temporarily set placeholder credential env vars without leaking state.

    Only sets the var if it isn't already present — real env wins.
    """
    saved: dict[str, str | None] = {}
    for key, value in _PLACEHOLDER_ENV.items():
        if os.environ.get(key):
            continue
        saved[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# --- factory introspection ----------------------------------------------


def _fastmcp_tool_names(instance: Any) -> list[str]:
    """Best-effort introspection of a FastMCP instance's registered tool names.

    FastMCP keeps tools in ``_tool_manager._tools`` (dict). We treat this as
    a stable enough internal API — the gateway's own integration tests rely
    on it. Falls back to an empty list if neither path exists, so older /
    newer SDK shapes don't crash the preview.
    """
    tm = getattr(instance, "_tool_manager", None)
    if tm is None:
        return []
    tools = getattr(tm, "_tools", None)
    if isinstance(tools, dict):
        return sorted(tools.keys())
    # Some versions expose list_tools()
    lister = getattr(tm, "list_tools", None)
    if callable(lister):
        try:
            listed = lister() or []
            return sorted(getattr(t, "name", str(t)) for t in listed)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            return []
    return []


def _attribute_drop(name: str, include: list[str], exclude: list[str]) -> str:
    """Return a human-readable reason explaining why ``name`` was filtered.

    Mirrors the precedence used by ``huaweicloud_mcp.server._filter_tools``:
    include is checked first (a non-empty include that doesn't match is the
    reason), then exclude.
    """
    if include and not any(fnmatch.fnmatchcase(name, p) for p in include):
        return f"not matched by include={include}"
    for pat in exclude:
        if fnmatch.fnmatchcase(name, pat):
            return f"excluded by '{pat}'"
    return "filtered"


# --- per-service build --------------------------------------------------


def _build_service_report(svc: ServiceConfig) -> ServiceReport:
    """Run the factory twice (no-filter baseline + declared) and diff the tools."""
    report = ServiceReport(
        name=svc.name,
        mount_path=svc.mount_path,
        module=svc.module,
        attr=svc.attr,
        enabled=svc.enabled,
        skip_reason=svc.skip_reason,
        required_roles=list(svc.required_roles),
        build_kwargs=dict(svc.build_kwargs),
    )

    # Normalise declared filter patterns for diff attribution.
    raw_include = svc.build_kwargs.get("include")
    raw_exclude = svc.build_kwargs.get("exclude")
    report.include_patterns = _coerce_patterns(raw_include)
    report.exclude_patterns = _coerce_patterns(raw_exclude)

    if not svc.enabled:
        return report  # skipped services don't get a tool list

    try:
        import importlib

        module = importlib.import_module(svc.module)
        attr = getattr(module, svc.attr, None)
        if attr is None:
            report.build_error = (
                f"module {svc.module!r} has no attribute {svc.attr!r}"
            )
            return report

        # Singleton form (legacy) — no filter introspection possible because
        # there's no way to opt out of whatever the module did at import time.
        if not callable(attr):
            report.factory_form = "singleton"
            report.tools = [
                ToolReport(name=n, kept=True) for n in _fastmcp_tool_names(attr)
            ]
            return report

        report.factory_form = "factory"

        # Baseline build: same kwargs but with filter args stripped, to get
        # the full unfiltered tool list.
        baseline_kwargs = {
            k: v for k, v in svc.build_kwargs.items() if k not in _FILTER_KWARGS
        }
        with _stub_env(), _silence_logs():
            try:
                baseline_inst = attr(**baseline_kwargs)
            except TypeError as exc:
                report.build_error = (
                    f"factory rejected baseline kwargs={baseline_kwargs!r}: {exc}"
                )
                return report
            baseline_names = _fastmcp_tool_names(baseline_inst)

            # Declared build: full kwargs as written in manifest.
            try:
                declared_inst = attr(**svc.build_kwargs)
            except TypeError as exc:
                report.build_error = (
                    f"factory rejected declared kwargs={svc.build_kwargs!r}: {exc}"
                )
                return report
            declared_names = set(_fastmcp_tool_names(declared_inst))

        tools: list[ToolReport] = []
        for name in baseline_names:
            if name in declared_names:
                tools.append(ToolReport(name=name, kept=True))
            else:
                tools.append(
                    ToolReport(
                        name=name,
                        kept=False,
                        reason=_attribute_drop(
                            name, report.include_patterns, report.exclude_patterns
                        ),
                    )
                )
        # Any tool in declared but missing from baseline would be surprising —
        # surface it as kept with a marker so the operator notices.
        for name in sorted(declared_names - set(baseline_names)):
            tools.append(
                ToolReport(name=name, kept=True, reason="not seen in baseline build")
            )
        report.tools = tools
        return report

    except Exception as exc:  # noqa: BLE001
        report.build_error = f"{type(exc).__name__}: {exc}"
        return report


def _coerce_patterns(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    return [str(value)]


@contextlib.contextmanager
def _silence_logs():
    """Suppress factory log noise during the preview build.

    Factories install their own logging handlers inside the call (the
    huaweicloud_mcp factory calls ``setup_logging`` which replaces any
    handler we attached pre-emptively). The reliable cross-factory fix is
    to redirect both stderr (where StreamHandler writes by default) and
    stdout to a throwaway buffer for the duration of the build. The preview
    itself writes to the original stdout, which we save before redirection.
    """
    sink = io.StringIO()
    with contextlib.redirect_stderr(sink), contextlib.redirect_stdout(sink):
        yield


# --- top-level entry ----------------------------------------------------


def build_preview(
    manifest_path: str | Path,
    *,
    env_enabled: str | None = None,
    cli_enable: list[str] | None = None,
    cli_disable: list[str] | None = None,
) -> PreviewReport:
    """Load + override the manifest and produce a :class:`PreviewReport`."""
    manifest = load_manifest(manifest_path)
    manifest = apply_overrides(
        manifest,
        env_enabled=env_enabled,
        cli_enable=cli_enable,
        cli_disable=cli_disable,
    )
    report = PreviewReport(
        manifest_path=str(manifest_path),
        jwt_issuer=manifest.jwt.issuer,
    )
    for svc in manifest.services:
        report.services.append(_build_service_report(svc))
    return report


# --- rendering ----------------------------------------------------------


# ANSI colour codes; gated on isatty + NO_COLOR per the convention.
_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_GREEN = "\x1b[32m"
_RED = "\x1b[31m"
_YELLOW = "\x1b[33m"
_CYAN = "\x1b[36m"


def _use_colour(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("MCP_GATEWAY_FORCE_COLOR"):
        return True
    return getattr(stream, "isatty", lambda: False)()


def render_text(report: PreviewReport, *, show_filtered: bool, stream) -> None:
    colour = _use_colour(stream)

    def c(code: str, text: str) -> str:
        return f"{code}{text}{_RESET}" if colour else text

    write = stream.write
    write(f"Manifest: {report.manifest_path}\n")
    write(f"JWT issuer: {report.jwt_issuer}\n\n")

    total_kept = 0
    total_filtered = 0
    enabled_mounts = 0
    for svc in report.services:
        if not svc.enabled:
            write(
                c(_DIM, f"× skipped: {svc.name}  ({svc.skip_reason or 'manifest:disabled'})")
                + "\n\n"
            )
            continue
        enabled_mounts += 1
        header = f"Mount {svc.mount_path}  ({svc.name})"
        write(c(_BOLD, header) + "\n")
        if svc.required_roles:
            write(f"  Roles:   {', '.join(svc.required_roles)}\n")
        write(f"  Module:  {svc.module}.{svc.attr}  [{svc.factory_form}]\n")
        if svc.build_kwargs:
            write(f"  Kwargs:  {_compact_kwargs(svc.build_kwargs)}\n")
        if svc.include_patterns:
            write(f"  Include: {svc.include_patterns}\n")
        if svc.exclude_patterns:
            write(f"  Exclude: {svc.exclude_patterns}\n")

        if svc.build_error:
            write("  " + c(_RED, f"BUILD ERROR: {svc.build_error}") + "\n\n")
            continue

        kept = svc.kept_tools
        filtered = svc.filtered_tools
        total_kept += len(kept)
        total_filtered += len(filtered)
        write(
            f"  Tools:   {c(_GREEN, str(len(kept)) + ' active')}, "
            f"{c(_YELLOW, str(len(filtered)) + ' filtered')}\n"
        )
        for t in kept:
            marker = c(_GREEN, "  ✓")
            extra = c(_DIM, f"   ({t.reason})") if t.reason else ""
            write(f"  {marker} {t.name}{extra}\n")
        if filtered and show_filtered:
            for t in filtered:
                marker = c(_YELLOW, "  ✗")
                write(f"  {marker} {t.name}  " + c(_DIM, f"({t.reason})") + "\n")
        elif filtered:
            hint = c(_DIM, f"  (use --show-filtered to list the {len(filtered)} dropped tools)")
            write(hint + "\n")
        write("\n")

    summary = (
        f"Summary: {enabled_mounts} mount(s), "
        f"{total_kept} active tools"
        + (f", {total_filtered} filtered" if total_filtered else "")
    )
    if not report.ok:
        write(c(_RED, summary + "  [BUILD FAILED — see errors above]") + "\n")
    else:
        write(c(_BOLD, summary) + "\n")


def _compact_kwargs(kwargs: dict) -> str:
    """One-line JSON-ish render of build_kwargs (lists kept short)."""
    parts: list[str] = []
    for k, v in kwargs.items():
        if isinstance(v, list) and len(v) > 6:
            parts.append(f"{k}=[{len(v)} items]")
        else:
            parts.append(f"{k}={json.dumps(v, default=str, ensure_ascii=False)}")
    return ", ".join(parts)


def render_json(report: PreviewReport, *, stream) -> None:
    payload = {
        "manifest_path": report.manifest_path,
        "jwt_issuer": report.jwt_issuer,
        "ok": report.ok,
        "services": [
            {
                "name": s.name,
                "mount_path": s.mount_path,
                "module": s.module,
                "attr": s.attr,
                "enabled": s.enabled,
                "skip_reason": s.skip_reason,
                "required_roles": s.required_roles,
                "factory_form": s.factory_form,
                "build_kwargs": s.build_kwargs,
                "include": s.include_patterns,
                "exclude": s.exclude_patterns,
                "build_error": s.build_error,
                "tools": [
                    {"name": t.name, "kept": t.kept, "reason": t.reason}
                    for t in s.tools
                ],
                "active_count": len(s.kept_tools),
                "filtered_count": len(s.filtered_tools),
            }
            for s in report.services
        ],
    }
    json.dump(payload, stream, indent=2, ensure_ascii=False)
    stream.write("\n")


# --- CLI glue -----------------------------------------------------------


def run_preview(
    manifest_path: str,
    *,
    env_enabled: str | None,
    cli_enable: Iterable[str] | None,
    cli_disable: Iterable[str] | None,
    fmt: str,
    show_filtered: bool,
    stream=None,
) -> int:
    stream = stream if stream is not None else sys.stdout
    report = build_preview(
        manifest_path,
        env_enabled=env_enabled,
        cli_enable=list(cli_enable) if cli_enable else None,
        cli_disable=list(cli_disable) if cli_disable else None,
    )
    if fmt == "json":
        render_json(report, stream=stream)
    else:
        render_text(report, show_filtered=show_filtered, stream=stream)
    return 0 if report.ok else 1
