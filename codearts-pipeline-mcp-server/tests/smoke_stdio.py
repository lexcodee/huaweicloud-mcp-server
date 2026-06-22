"""End-to-end stdio smoke test for the CodeArts Pipeline MCP server.

Boots the server with fake-but-well-formed credentials, walks the JSON-RPC
handshake, and verifies all 5 expected tools are advertised.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


SERVER_CMD = [sys.executable, "-m", "pipeline_mcp_server.server"]
ENV_OVERRIDES = {
    "HUAWEICLOUD_ACCESS_KEY_ID": "AKIDFAKEFAKEFAKEFAKE",
    "HUAWEICLOUD_SECRET_ACCESS_KEY": "SKFAKE" + "X" * 34 + "FAKE",
    "HUAWEICLOUD_REGION": "af-south-1",
    "CODEARTS_DEFAULT_PROJECT_ID": "ddb5e3259e81494f9d083c917e173e5b",
    "PYTHONPATH": "src",
    "PIPELINE_MCP_LOG_LEVEL": "WARNING",
}
EXPECTED_TOOLS = {
    "pipeline_list",
    "pipeline_get_detail",
    "pipeline_run",
    "pipeline_update_info",
    "pipeline_set_status",
    "pipeline_confirm_destructive",
}


def main() -> int:
    env = {**os.environ, **ENV_OVERRIDES}
    proc = subprocess.Popen(
        SERVER_CMD,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, text=True, bufsize=1,
    )

    def send(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def recv():
        line = proc.stdout.readline()
        return json.loads(line) if line.strip() else None

    try:
        # 1) initialize
        send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "smoke", "version": "0.0"},
            },
        })
        init = recv()
        assert init and "result" in init, f"initialize failed: {init}"
        print("init.result.serverInfo:", init["result"].get("serverInfo"))

        # 2) initialized notification (required by spec)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        # 3) tools/list
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        resp = recv()
        assert resp and "result" in resp, f"tools/list failed: {resp}"
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        print("tools:", sorted(names))
        missing = EXPECTED_TOOLS - names
        extra = names - EXPECTED_TOOLS
        assert not missing, f"missing tools: {missing}"
        assert not extra, f"unexpected tools: {extra}"

        # 4) every tool must have a non-empty description
        empty_desc = [t["name"] for t in tools if not t.get("description")]
        assert not empty_desc, f"tools without description: {empty_desc}"

    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()

    print("OK ✔ smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
