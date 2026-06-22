"""Test: three-layer override priority for service enable/disable.

Layers (lowest → highest):
  1. manifest.yaml per-service ``enabled`` field
  2. MCP_GATEWAY_ENABLED_SERVICES env var
  3. CLI --enable / --disable

Each higher layer overrides the lower.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from mcp_gateway.manifest_loader import Manifest, apply_overrides, load_manifest

FIXTURES = Path(__file__).parent / "fixtures"


def _write_manifest(tmp: Path, services: list[dict], jwt: dict | None = None) -> Path:
    doc = {
        "jwt": jwt or {"issuer": "test", "public_key": "env:MCP_JWT_PUBLIC_KEY"},
        "services": services,
    }
    p = tmp / "manifest.yaml"
    p.write_text(yaml.dump(doc), encoding="utf-8")
    return p


def _svc(name: str, enabled: bool = True, roles: list[str] | None = None) -> dict:
    return {
        "name": name,
        "module": f"{name}_mcp_server",
        "attr": "mcp",
        "mount_path": f"/{name}",
        "required_roles": roles or ["readonly"],
        "enabled": enabled,
    }


class TestManifestLoading:
    def test_all_enabled(self, tmp_path):
        p = _write_manifest(tmp_path, [_svc("ecs"), _svc("pipeline"), _svc("cts")])
        m = load_manifest(p)
        assert [s.name for s in m.enabled_services()] == ["ecs", "pipeline", "cts"]
        assert m.skipped_services() == []

    def test_partial_enabled(self, tmp_path):
        p = _write_manifest(tmp_path, [_svc("ecs", True), _svc("pipeline", False), _svc("cts", True)])
        m = load_manifest(p)
        assert [s.name for s in m.enabled_services()] == ["ecs", "cts"]
        assert [s.name for s in m.skipped_services()] == ["pipeline"]


class TestEnvOverride:
    """Layer 2: MCP_GATEWAY_ENABLED_SERVICES overrides manifest."""

    def test_env_narrows_to_subset(self, tmp_path):
        p = _write_manifest(tmp_path, [_svc("ecs"), _svc("pipeline"), _svc("cts")])
        m = load_manifest(p)
        m2 = apply_overrides(m, env_enabled="ecs,cts", cli_enable=None, cli_disable=None)
        assert [s.name for s in m2.enabled_services()] == ["ecs", "cts"]
        assert [s.name for s in m2.skipped_services()] == ["pipeline"]

    def test_env_enables_manifest_disabled(self, tmp_path):
        p = _write_manifest(tmp_path, [_svc("ecs", True), _svc("pipeline", False)])
        m = load_manifest(p)
        m2 = apply_overrides(m, env_enabled="ecs,pipeline", cli_enable=None, cli_disable=None)
        assert [s.name for s in m2.enabled_services()] == ["ecs", "pipeline"]


class TestCliOverride:
    """Layer 3: CLI --enable / --disable overrides env + manifest."""

    def test_cli_enable_wins_over_env(self, tmp_path):
        p = _write_manifest(tmp_path, [_svc("ecs"), _svc("pipeline"), _svc("cts")])
        m = load_manifest(p)
        # Env says only ecs; CLI says pipeline — CLI wins.
        m2 = apply_overrides(m, env_enabled="ecs", cli_enable=["pipeline"], cli_disable=None)
        assert [s.name for s in m2.enabled_services()] == ["pipeline"]

    def test_cli_disable_subtracts(self, tmp_path):
        p = _write_manifest(tmp_path, [_svc("ecs"), _svc("pipeline"), _svc("cts")])
        m = load_manifest(p)
        m2 = apply_overrides(m, env_enabled=None, cli_enable=None, cli_disable=["cts"])
        assert [s.name for s in m2.enabled_services()] == ["ecs", "pipeline"]
        assert [s.name for s in m2.skipped_services()] == ["cts"]

    def test_cli_enable_then_disable(self, tmp_path):
        p = _write_manifest(tmp_path, [_svc("ecs"), _svc("pipeline"), _svc("cts")])
        m = load_manifest(p)
        # --enable ecs,pipeline --disable pipeline
        m2 = apply_overrides(m, env_enabled=None, cli_enable=["ecs,pipeline"], cli_disable=["pipeline"])
        assert [s.name for s in m2.enabled_services()] == ["ecs"]

    def test_skip_reason_populated(self, tmp_path):
        p = _write_manifest(tmp_path, [_svc("ecs"), _svc("pipeline", False), _svc("cts")])
        m = load_manifest(p)
        m2 = apply_overrides(m, env_enabled="ecs,cts", cli_enable=None, cli_disable=["cts"])
        skipped = {s.name: s.skip_reason for s in m2.skipped_services()}
        assert "manifest:disabled" not in skipped.get("pipeline", "")
        assert "env:" in skipped.get("pipeline", "")
        assert "cli:" in skipped.get("cts", "")


class TestDuplicateDetection:
    def test_duplicate_name_rejected(self, tmp_path):
        p = _write_manifest(tmp_path, [_svc("ecs"), _svc("ecs")])
        with pytest.raises(ValueError, match="duplicate service name"):
            load_manifest(p)

    def test_duplicate_mount_rejected(self, tmp_path):
        s1 = _svc("ecs")
        s2 = _svc("other")
        s2["mount_path"] = "/ecs"
        p = _write_manifest(tmp_path, [s1, s2])
        with pytest.raises(ValueError, match="duplicate mount_path"):
            load_manifest(p)
