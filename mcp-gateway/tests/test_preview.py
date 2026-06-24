"""Tests for ``mcp-gateway config preview`` and its underlying ``preview`` module.

Covers:
    - text rendering: header, mount block, active vs filtered counts
    - JSON rendering: stable schema fields downstream tools rely on
    - attribution: each dropped tool names the pattern that excluded it
    - build error path: exit 1, error message rendered, BUILD FAILED banner
    - CLI overrides (--enable / --disable) propagate through to the preview
    - skipped services render as a single-line entry, no tools listed
    - factory log noise does NOT leak onto stdout/stderr
    - --show-filtered toggles the dropped-tool listing
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from mcp_gateway.cli import main as cli_main
from mcp_gateway.preview import build_preview, render_json, render_text, run_preview


@pytest.fixture
def rbac_manifest(tmp_path: Path) -> Path:
    """Two mounts: a filtered read-only one and the full one. Real factory."""
    p = tmp_path / "manifest.yaml"
    p.write_text(
        """
jwt:
  issuer: mcp-gateway
  public_key: env:MCP_JWT_PUBLIC_KEY
services:
  - name: huaweicloud-readonly
    enabled: true
    module: huaweicloud_mcp
    attr: build_server
    build_kwargs:
      enabled: [ecs, cts]
      exclude:
        - "*_confirm_destructive"
        - "*_delete_*"
        - "*_resize_*"
        - "*_power_action"
    mount_path: /hwc/ro
    required_roles: [readonly, operator]
  - name: huaweicloud
    enabled: true
    module: huaweicloud_mcp
    attr: build_server
    build_kwargs:
      enabled: [ecs, cts]
    mount_path: /hwc
    required_roles: [operator, admin]
""".strip(),
        encoding="utf-8",
    )
    return p


@pytest.fixture
def disabled_manifest(tmp_path: Path) -> Path:
    p = tmp_path / "manifest.yaml"
    p.write_text(
        """
jwt:
  issuer: mcp-gateway
  public_key: env:MCP_JWT_PUBLIC_KEY
services:
  - name: huaweicloud
    enabled: false
    module: huaweicloud_mcp
    attr: build_server
    build_kwargs:
      enabled: [ecs]
    mount_path: /hwc
""".strip(),
        encoding="utf-8",
    )
    return p


@pytest.fixture
def bad_manifest(tmp_path: Path) -> Path:
    p = tmp_path / "manifest.yaml"
    p.write_text(
        """
jwt:
  issuer: mcp-gateway
  public_key: env:MCP_JWT_PUBLIC_KEY
services:
  - name: huaweicloud-bad
    enabled: true
    module: huaweicloud_mcp
    attr: build_server
    build_kwargs:
      enabled: [definitely_not_a_real_service]
    mount_path: /hwc
""".strip(),
        encoding="utf-8",
    )
    return p


# --- core build_preview --------------------------------------------------


def test_build_preview_factory_diff_attribution(rbac_manifest):
    report = build_preview(rbac_manifest)
    assert report.ok
    assert len(report.services) == 2

    ro = report.services[0]
    assert ro.name == "huaweicloud-readonly"
    assert ro.mount_path == "/hwc/ro"
    assert ro.factory_form == "factory"
    assert ro.exclude_patterns
    # Filtered tools have a non-empty reason naming the matching pattern.
    filtered = ro.filtered_tools
    assert filtered, "expected at least one filtered tool"
    for t in filtered:
        assert "excluded by '" in t.reason

    full = report.services[1]
    assert full.name == "huaweicloud"
    assert full.filtered_tools == []
    assert full.kept_tools, "full mount must register tools"


def test_build_preview_skipped_service(disabled_manifest):
    report = build_preview(disabled_manifest)
    assert report.ok  # disabled is not an error
    [svc] = report.services
    assert not svc.enabled
    assert svc.tools == []
    assert svc.skip_reason == "manifest:disabled"


def test_build_preview_build_error(bad_manifest):
    report = build_preview(bad_manifest)
    assert not report.ok
    [svc] = report.services
    assert "Unknown services" in svc.build_error
    assert svc.tools == []


def test_build_preview_module_not_found_hint(tmp_path):
    """ModuleNotFoundError should be enriched with an interpreter hint so the
    operator can spot the most common cause — wrong Python interpreter
    (forgotten venv activation)."""
    p = tmp_path / "manifest.yaml"
    p.write_text(
        """
jwt:
  issuer: mcp-gateway
  public_key: env:MCP_JWT_PUBLIC_KEY
services:
  - name: ghost
    enabled: true
    module: definitely_not_installed_module_xyz
    attr: build_server
    mount_path: /ghost
""".strip(),
        encoding="utf-8",
    )
    report = build_preview(p)
    assert not report.ok
    [svc] = report.services
    assert "ModuleNotFoundError" in svc.build_error
    assert "HINT:" in svc.build_error
    assert "python=" in svc.build_error
    assert "venv=" in svc.build_error
    # The hint must reference the actual missing module name.
    assert "definitely_not_installed_module_xyz" in svc.build_error


def test_build_preview_cli_override_disables(rbac_manifest):
    report = build_preview(rbac_manifest, cli_disable=["huaweicloud"])
    enabled = [s for s in report.services if s.enabled]
    skipped = [s for s in report.services if not s.enabled]
    assert [s.name for s in enabled] == ["huaweicloud-readonly"]
    assert [s.name for s in skipped] == ["huaweicloud"]
    assert skipped[0].skip_reason == "cli:--disable"


# --- text rendering ------------------------------------------------------


def test_render_text_contains_mount_and_summary(rbac_manifest):
    report = build_preview(rbac_manifest)
    buf = io.StringIO()
    render_text(report, show_filtered=True, stream=buf)
    out = buf.getvalue()
    assert "Mount /hwc/ro" in out
    assert "Mount /hwc" in out
    assert "Summary:" in out
    assert "active tools" in out
    # show_filtered=True must include attribution lines.
    assert "excluded by '" in out


def test_render_text_show_filtered_off_hides_drop_list(rbac_manifest):
    report = build_preview(rbac_manifest)
    buf = io.StringIO()
    render_text(report, show_filtered=False, stream=buf)
    out = buf.getvalue()
    # The hint must appear instead of per-tool drop lines.
    assert "use --show-filtered" in out
    assert "excluded by '" not in out


def test_render_text_skipped_service_one_line(disabled_manifest):
    report = build_preview(disabled_manifest)
    buf = io.StringIO()
    render_text(report, show_filtered=False, stream=buf)
    out = buf.getvalue()
    assert "× skipped: huaweicloud" in out
    assert "Tools:" not in out  # skipped entries don't list tools


def test_render_text_build_error_banner(bad_manifest):
    report = build_preview(bad_manifest)
    buf = io.StringIO()
    render_text(report, show_filtered=False, stream=buf)
    out = buf.getvalue()
    assert "BUILD ERROR" in out
    assert "BUILD FAILED" in out


# --- JSON rendering ------------------------------------------------------


def test_render_json_schema(rbac_manifest):
    report = build_preview(rbac_manifest)
    buf = io.StringIO()
    render_json(report, stream=buf)
    payload = json.loads(buf.getvalue())

    assert payload["ok"] is True
    assert payload["jwt_issuer"] == "mcp-gateway"
    assert len(payload["services"]) == 2

    svc = payload["services"][0]
    expected_keys = {
        "name", "mount_path", "module", "attr", "enabled", "skip_reason",
        "required_roles", "factory_form", "build_kwargs", "include", "exclude",
        "build_error", "tools", "active_count", "filtered_count",
    }
    assert expected_keys <= set(svc.keys())
    assert svc["active_count"] == len([t for t in svc["tools"] if t["kept"]])
    assert svc["filtered_count"] == len([t for t in svc["tools"] if not t["kept"]])
    # At least one dropped tool carries a non-empty reason.
    dropped = [t for t in svc["tools"] if not t["kept"]]
    assert dropped and all(d["reason"] for d in dropped)


def test_render_json_build_error_ok_false(bad_manifest):
    report = build_preview(bad_manifest)
    buf = io.StringIO()
    render_json(report, stream=buf)
    payload = json.loads(buf.getvalue())
    assert payload["ok"] is False
    assert "Unknown services" in payload["services"][0]["build_error"]


# --- run_preview (exit codes) -------------------------------------------


def test_run_preview_ok_returns_zero(rbac_manifest, capsys):
    rc = run_preview(
        str(rbac_manifest),
        env_enabled=None, cli_enable=None, cli_disable=None,
        fmt="text", show_filtered=False,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Summary:" in out


def test_run_preview_build_error_returns_one(bad_manifest, capsys):
    rc = run_preview(
        str(bad_manifest),
        env_enabled=None, cli_enable=None, cli_disable=None,
        fmt="text", show_filtered=False,
    )
    assert rc == 1


# --- log noise containment ----------------------------------------------


def test_factory_log_noise_does_not_leak_to_stdout(rbac_manifest, capsys):
    """The huaweicloud_mcp factory logs INFO lines via its own handler;
    those lines MUST NOT leak into the preview's stdout output. If they do,
    JSON output gets corrupted and text output is unreadable."""
    rc = run_preview(
        str(rbac_manifest),
        env_enabled=None, cli_enable=None, cli_disable=None,
        fmt="json", show_filtered=False,
    )
    assert rc == 0
    out = capsys.readouterr().out
    # If logs leaked, json.loads will throw.
    payload = json.loads(out)
    assert payload["ok"] is True


# --- CLI integration ----------------------------------------------------


def test_cli_config_preview_text(monkeypatch, capsys, rbac_manifest):
    monkeypatch.setenv("NO_COLOR", "1")
    rc = cli_main(["config", "preview", "--manifest", str(rbac_manifest)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Mount /hwc/ro" in out
    assert "Summary:" in out


def test_cli_config_preview_json(monkeypatch, capsys, rbac_manifest):
    rc = cli_main(["config", "preview", "--manifest", str(rbac_manifest), "--format", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert len(payload["services"]) == 2


def test_cli_config_preview_build_error_exits_1(monkeypatch, capsys, bad_manifest):
    monkeypatch.setenv("NO_COLOR", "1")
    rc = cli_main(["config", "preview", "--manifest", str(bad_manifest)])
    assert rc == 1
    assert "BUILD FAILED" in capsys.readouterr().out


def test_cli_config_preview_disable_flag(monkeypatch, capsys, rbac_manifest):
    monkeypatch.setenv("NO_COLOR", "1")
    rc = cli_main(
        ["config", "preview", "--manifest", str(rbac_manifest), "--disable", "huaweicloud"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "× skipped: huaweicloud" in out
    assert "cli:--disable" in out


def test_cli_config_preview_env_var_filter(monkeypatch, capsys, rbac_manifest):
    """``MCP_GATEWAY_ENABLED_SERVICES`` shrinks the enabled set."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("MCP_GATEWAY_ENABLED_SERVICES", "huaweicloud-readonly")
    rc = cli_main(["config", "preview", "--manifest", str(rbac_manifest)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Mount /hwc/ro" in out
    # The other service must be skipped, attributed to the env layer.
    assert "× skipped: huaweicloud" in out
    assert "env:MCP_GATEWAY_ENABLED_SERVICES" in out
