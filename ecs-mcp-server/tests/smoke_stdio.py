"""End-to-end stdio smoke test — speaks JSON-RPC to the server,
initializes, and lists the tools. No real Huawei Cloud calls.
"""
import json
import os
import subprocess
import sys


def main():
    env = {
        **os.environ,
        "HUAWEICLOUD_ACCESS_KEY_ID": "AKIDFAKEFAKEFAKEFAKE",
        "HUAWEICLOUD_SECRET_ACCESS_KEY": "SKFAKE" + "X" * 34 + "FAKE",
        "PYTHONPATH": "src",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "ecs_mcp_server.server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, text=True, bufsize=1,
    )

    def send(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def recv():
        line = proc.stdout.readline()
        return json.loads(line) if line.strip() else None

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
    print("init.result.serverInfo:", init.get("result", {}).get("serverInfo"))

    # 2) initialized notification
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    # 3) tools/list
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = recv()
    names = [t["name"] for t in tools["result"]["tools"]]
    print("tools:", names)
    assert len(names) == 10

    # 4) shutdown — close stdin
    proc.stdin.close()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.terminate()

    print("OK ✔ smoke test passed")


if __name__ == "__main__":
    main()
