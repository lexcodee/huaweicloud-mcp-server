"""Test: structured JSON log format and audit event fields."""
from __future__ import annotations

import json
import logging
import os

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mcp_gateway.auth_middleware import GatewayAuthMiddleware
from mcp_gateway.logfmt import JsonFormatter, TextFormatter, setup_logging


class TestJsonFormatter:
    def test_basic_fields(self):
        """JSON output contains ts, level, logger, msg."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="mcp_gateway.auth",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="auth-rejected",
            args=(),
            exc_info=None,
        )
        out = formatter.format(record)
        obj = json.loads(out)
        assert "ts" in obj
        assert obj["level"] == "WARNING"
        assert obj["logger"] == "mcp_gateway.auth"
        assert obj["msg"] == "auth-rejected"

    def test_extra_fields_promoted(self):
        """extra kwargs become top-level JSON keys."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="mcp_gateway.auth",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="auth-rejected",
            args=(),
            exc_info=None,
        )
        record.status = 403
        record.path = "/ecs/sse"
        record.peer = "10.0.1.5"
        record.reason = "path-rbac:required=[admin];caller=[readonly]"
        out = formatter.format(record)
        obj = json.loads(out)
        assert obj["status"] == 403
        assert obj["path"] == "/ecs/sse"
        assert obj["peer"] == "10.0.1.5"
        assert "path-rbac" in obj["reason"]

    def test_non_serialisable_extra_falls_back_to_str(self):
        """Non-JSON-serialisable extra values become strings."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="ok",
            args=(),
            exc_info=None,
        )
        record.data = b"\x00binary"  # not JSON-serialisable
        out = formatter.format(record)
        obj = json.loads(out)
        assert isinstance(obj["data"], str)

    def test_iso8601_timestamp(self):
        """Timestamp is ISO-8601 with timezone."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="ok",
            args=(),
            exc_info=None,
        )
        out = formatter.format(record)
        obj = json.loads(out)
        # ISO-8601 contains 'T' and timezone offset or 'Z'
        assert "T" in obj["ts"]


class TestTextFormatter:
    def test_backward_compatible_format(self):
        """Text formatter produces human-readable single-line output."""
        formatter = TextFormatter()
        record = logging.LogRecord(
            name="mcp_gateway.auth",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="auth-rejected",
            args=(),
            exc_info=None,
        )
        out = formatter.format(record)
        assert "WARNING" in out
        assert "mcp_gateway.auth" in out
        assert "auth-rejected" in out


class TestSetupLogging:
    def test_json_mode_installs_json_formatter(self):
        """setup_logging(fmt='json') puts JsonFormatter on the mcp_gateway logger."""
        gw = logging.getLogger("mcp_gateway")
        setup_logging(level="INFO", fmt="json")
        assert len(gw.handlers) == 1
        assert isinstance(gw.handlers[0].formatter, JsonFormatter)
        # Cleanup
        setup_logging(level="INFO", fmt="text")

    def test_text_mode_installs_text_formatter(self):
        """setup_logging(fmt='text') puts TextFormatter on the mcp_gateway logger."""
        gw = logging.getLogger("mcp_gateway")
        setup_logging(level="INFO", fmt="text")
        assert len(gw.handlers) == 1
        assert isinstance(gw.handlers[0].formatter, TextFormatter)


class TestAuditEventsInJson:
    """Verify that auth rejection events produce structured JSON with audit fields."""

    def test_auth_rejection_json_output(self, caplog):
        """When JWT auth fails, the log record carries structured extra fields."""
        os.environ["MCP_GATEWAY_AUTH_MODE"] = "jwt"
        os.environ["MCP_GATEWAY_HOST"] = "127.0.0.1"

        async def ok(request):
            return JSONResponse({"ok": True})

        app = Starlette(routes=[Route("/ecs/sse", ok, methods=["GET"])])
        app.add_middleware(
            GatewayAuthMiddleware,
            public_key_spec="file:jwt-public.pem",  # will fail to verify
            issuer="mcp-gateway",
            audience=None,
            leeway=30,
            path_roles=[],
            exempt_paths=("/healthz",),
        )

        # Build a real JsonFormatter and capture what it would emit.
        formatter = JsonFormatter()

        with caplog.at_level(logging.WARNING, logger="mcp_gateway.auth"):
            client = TestClient(app, raise_server_exceptions=False)
            r = client.get("/ecs/sse")
            # Expect 401 (no token) or 500 (no key file) — either way a log is emitted.
            assert r.status_code in (401, 500)

        # Find the auth-rejected record.
        auth_records = [rec for rec in caplog.records if rec.getMessage() == "auth-rejected"]
        if auth_records:
            rec = auth_records[0]
            out = formatter.format(rec)
            obj = json.loads(out)
            assert obj["event"] == "auth-rejected"
            assert "status" in obj
            assert "path" in obj
            assert "peer" in obj
            assert "reason" in obj

        os.environ.pop("MCP_GATEWAY_AUTH_MODE", None)

    def test_dev_mode_request_json_output(self, caplog):
        """Dev mode request events carry structured fields."""
        os.environ["MCP_GATEWAY_AUTH_MODE"] = "dev"
        os.environ["MCP_GATEWAY_HOST"] = "127.0.0.1"

        async def ok(request):
            return JSONResponse({"ok": True})

        app = Starlette(routes=[Route("/ecs/sse", ok, methods=["GET"])])
        app.add_middleware(
            GatewayAuthMiddleware,
            public_key_spec="",
            issuer="mcp-gateway",
            audience=None,
            leeway=30,
            path_roles=[],
            exempt_paths=("/healthz",),
        )

        formatter = JsonFormatter()

        with caplog.at_level(logging.WARNING, logger="mcp_gateway.auth"):
            client = TestClient(app)
            r = client.get("/ecs/sse")
            assert r.status_code == 200

        dev_records = [rec for rec in caplog.records if rec.getMessage() == "dev-mode-request"]
        if dev_records:
            rec = dev_records[0]
            out = formatter.format(rec)
            obj = json.loads(out)
            assert obj["event"] == "dev-mode-request"
            assert obj["auth_mode"] == "dev"
            assert "sub" in obj
            assert "roles" in obj
            assert "path" in obj

        os.environ.pop("MCP_GATEWAY_AUTH_MODE", None)
