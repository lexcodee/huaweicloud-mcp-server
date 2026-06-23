"""Test: manifest factory mode (attr=callable + build_kwargs).

Strategy 1 unified deployment: the gateway should be able to mount a single
service that points at a factory function (e.g. ``huaweicloud_mcp.build_server``)
and pass ``build_kwargs`` (e.g. ``enabled: [ecs, pipeline, cts]``) to choose
the active tool subset. This keeps Agent configuration at exactly one URL
even as the number of underlying cloud services grows.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
import yaml
from mcp.server.fastmcp import FastMCP

from mcp_gateway.gateway import _resolve_fastmcp
from mcp_gateway.manifest_loader import (
    ServiceConfig,
    apply_overrides,
    load_manifest,
)


def _write_manifest(tmp: Path, services: list[dict]) -> Path:
    doc = {
        "jwt": {"issuer": "test", "public_key": "env:MCP_JWT_PUBLIC_KEY"},
        "services": services,
    }
    p = tmp / "manifest.yaml"
    p.write_text(yaml.dump(doc), encoding="utf-8")
    return p


def _install_fake_module(name: str, **attrs) -> None:
    """Register a synthetic module in sys.modules for importlib.import_module."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod


class TestManifestBuildKwargs:
    def test_build_kwargs_parsed_from_yaml(self, tmp_path):
        p = _write_manifest(tmp_path, [{
            "name": "huaweicloud",
            "module": "huaweicloud_mcp",
            "attr": "build_server",
            "build_kwargs": {"enabled": ["ecs", "pipeline", "cts"]},
            "mount_path": "/hwc",
            "required_roles": ["operator"],
        }])
        m = load_manifest(p)
        assert len(m.services) == 1
        svc = m.services[0]
        assert svc.attr == "build_server"
        assert svc.build_kwargs == {"enabled": ["ecs", "pipeline", "cts"]}
        assert svc.mount_path == "/hwc"

    def test_build_kwargs_defaults_to_empty(self, tmp_path):
        p = _write_manifest(tmp_path, [{
            "name": "legacy",
            "module": "some_pkg",
            "attr": "mcp",
            "mount_path": "/legacy",
            "required_roles": ["readonly"],
        }])
        m = load_manifest(p)
        assert m.services[0].build_kwargs == {}

    def test_overrides_preserve_build_kwargs(self, tmp_path):
        p = _write_manifest(tmp_path, [{
            "name": "huaweicloud",
            "module": "huaweicloud_mcp",
            "attr": "build_server",
            "build_kwargs": {"enabled": ["ecs"]},
            "mount_path": "/hwc",
            "required_roles": ["operator"],
        }])
        m = load_manifest(p)
        m2 = apply_overrides(m, env_enabled=None, cli_enable=None, cli_disable=None)
        assert m2.services[0].build_kwargs == {"enabled": ["ecs"]}


class TestFactoryResolution:
    """`_resolve_fastmcp` invokes the factory with build_kwargs."""

    def test_factory_with_kwargs_invoked(self):
        captured: dict = {}

        def build_server(*, enabled: list[str]) -> FastMCP:
            captured["enabled"] = enabled
            return FastMCP(f"fake-{'-'.join(enabled)}")

        _install_fake_module("fake_pkg_factory_kwargs", build_server=build_server)
        svc = ServiceConfig(
            name="fake",
            module="fake_pkg_factory_kwargs",
            attr="build_server",
            build_kwargs={"enabled": ["ecs", "cts"]},
            mount_path="/fake",
        )

        inst = _resolve_fastmcp(svc)
        assert isinstance(inst, FastMCP)
        assert captured["enabled"] == ["ecs", "cts"]

    def test_factory_without_kwargs(self):
        def build_server() -> FastMCP:
            return FastMCP("fake-no-kwargs")

        _install_fake_module("fake_pkg_factory_nokw", build_server=build_server)
        svc = ServiceConfig(
            name="fake",
            module="fake_pkg_factory_nokw",
            attr="build_server",
            mount_path="/fake",
        )
        inst = _resolve_fastmcp(svc)
        assert isinstance(inst, FastMCP)

    def test_factory_bad_kwargs_raises_clear_error(self):
        def build_server(*, enabled: list[str]) -> FastMCP:
            return FastMCP("fake")

        _install_fake_module("fake_pkg_factory_bad", build_server=build_server)
        svc = ServiceConfig(
            name="fake",
            module="fake_pkg_factory_bad",
            attr="build_server",
            build_kwargs={"wrong_arg": 1},
            mount_path="/fake",
        )
        with pytest.raises(RuntimeError, match="rejected build_kwargs"):
            _resolve_fastmcp(svc)

    def test_singleton_still_works(self):
        """Legacy form — attr names a module-level FastMCP instance."""
        singleton = FastMCP("legacy-singleton")
        _install_fake_module("fake_pkg_singleton", mcp=singleton)
        svc = ServiceConfig(
            name="legacy",
            module="fake_pkg_singleton",
            attr="mcp",
            mount_path="/legacy",
        )
        inst = _resolve_fastmcp(svc)
        assert inst is singleton

    def test_factory_returning_non_fastmcp_rejected(self):
        def build_server() -> object:
            return "not a fastmcp"

        _install_fake_module("fake_pkg_factory_wrongtype", build_server=build_server)
        svc = ServiceConfig(
            name="fake",
            module="fake_pkg_factory_wrongtype",
            attr="build_server",
            mount_path="/fake",
        )
        with pytest.raises(RuntimeError, match="is not a FastMCP instance"):
            _resolve_fastmcp(svc)


class TestStrategy1SingleMount:
    """End-to-end check that the real shipped manifest.yaml parses and
    points at the unified huaweicloud_mcp package with all three services."""

    def test_repo_manifest_uses_factory(self):
        # Repo root is two levels up from this test file:
        # mcp-gateway/tests/test_factory_mode.py -> repo/
        repo_root = Path(__file__).resolve().parents[2]
        manifest_path = repo_root / "manifest.yaml"
        if not manifest_path.exists():
            pytest.skip("repo manifest.yaml not present")
        m = load_manifest(manifest_path)
        enabled = m.enabled_services()
        assert len(enabled) == 1, "Strategy 1 expects exactly one mount"
        svc = enabled[0]
        assert svc.module == "huaweicloud_mcp"
        assert svc.attr == "build_server"
        assert "enabled" in svc.build_kwargs
        assert set(svc.build_kwargs["enabled"]) >= {"ecs", "pipeline", "cts"}
        assert svc.mount_path == "/hwc"
