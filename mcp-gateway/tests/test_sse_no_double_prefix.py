"""Regression test: gateway must not double-prefix the SSE endpoint.

The MCP SDK's ``connect_sse`` constructs the ``event: endpoint`` URL the
client POSTs to as ``scope['root_path'] + transport._endpoint``. Starlette's
``Mount(path, app=...)`` populates ``root_path`` automatically. If the gateway
ALSO passes ``mount_path=path`` to ``FastMCP.sse_app(...)``, the SDK bakes the
prefix into ``transport._endpoint`` on top of that — yielding ``/hwc/hwc/...``
and a 404 on every client POST.

This test starts a real uvicorn server, opens the SSE stream via httpx,
reads the first ``event: endpoint`` frame, and asserts the data starts with
``/hwc/messages/`` with exactly one ``/hwc`` prefix.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

import httpx
import uvicorn
import yaml

from mcp_gateway.gateway import build_app


def _write_manifest(tmp: Path) -> Path:
    p = tmp / "manifest.yaml"
    p.write_text(yaml.dump({
        "jwt": {"issuer": "test", "public_key": "dummy"},
        "auth_mode": "disabled",
        "services": [{
            "name": "hwc",
            "module": "huaweicloud_mcp",
            "attr": "build_server",
            "build_kwargs": {"enabled": []},
            "mount_path": "/hwc",
            "required_roles": ["readonly"],
        }],
    }), encoding="utf-8")
    return p


def test_sse_endpoint_event_uses_single_mount_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("HUAWEICLOUD_AK", "ak")
    monkeypatch.setenv("HUAWEICLOUD_SK", "sk")
    monkeypatch.setenv("HUAWEICLOUD_PROJECT_ID", "pid")
    monkeypatch.setenv("HUAWEICLOUD_REGION", "af-south-1")
    monkeypatch.setenv("MCP_GATEWAY_AUTH_MODE", "dev")

    manifest = _write_manifest(tmp_path)
    app = build_app(manifest)

    # Start a real uvicorn on a free port so DNS-rebinding checks pass.
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    # Wait until server is ready
    import time
    for _ in range(40):
        try:
            httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=0.5)
            break
        except Exception:
            time.sleep(0.05)

    try:
        # Read the first SSE event (event: endpoint) and stop.
        with httpx.stream("GET", f"http://127.0.0.1:{port}/hwc/sse", timeout=5) as resp:
            assert resp.status_code == 200, resp.text
            payload = ""
            for line in resp.iter_lines():
                payload += line + "\n"
                if line.startswith("data:"):
                    break

        m = re.search(r"data:\s*(\S+)", payload)
        assert m, f"no data line in SSE payload: {payload!r}"
        endpoint = m.group(1)

        # Must start with /hwc/messages — NOT /hwc/hwc/messages.
        assert endpoint.startswith("/hwc/messages"), (
            f"SSE endpoint {endpoint!r} should start with /hwc/messages — "
            f"a /hwc/hwc prefix means _mount_one is calling sse_app(mount_path=...) "
            f"on top of Starlette's Mount, double-prefixing the URL."
        )
        assert not endpoint.startswith("/hwc/hwc/"), (
            f"SSE endpoint {endpoint!r} is double-prefixed — regression of the "
            f"sse_app(mount_path=...) + Mount(...) interaction."
        )
    finally:
        server.should_exit = True
        t.join(timeout=3)
