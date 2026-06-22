"""One-shot real-backend probe for the CodeArts Pipeline MCP server.

Spawns the server via the run-with-env.sh wrapper (which loads the shared
Huawei Cloud .env), walks the MCP handshake, then issues a single
`pipeline_list` call. Prints the unwrapped tool envelope.
"""
import json
import subprocess
import sys


WRAPPER = "/root/huaweicloud-mcp-server/codearts-pipeline-mcp-server/scripts/run-with-env.sh"


def main() -> int:
    proc = subprocess.Popen(
        [WRAPPER],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )

    def send(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def recv():
        line = proc.stdout.readline()
        return json.loads(line)

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05",
                         "capabilities": {},
                         "clientInfo": {"name": "probe", "version": "0.0"}}})
        init = recv()
        print("server:", init["result"]["serverInfo"])

        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": "pipeline_list",
                         "arguments": {"limit": 5}}})
        resp = recv()

        payload = json.loads(resp["result"]["content"][0]["text"])
        if payload.get("ok"):
            d = payload["data"]
            print(f"OK total={d.get('total')} returned={len(d.get('pipelines') or [])}")
            for p in (d.get("pipelines") or [])[:5]:
                lr = (p.get("latest_run") or {})
                name = p.get("name") or "?"
                status = lr.get("status") or "N/A"
                branch = lr.get("target_branch") or "N/A"
                print(f"  - {name:32s} status={status:10s} branch={branch}")
        else:
            e = payload["error"]
            print(f"FAIL code={e.get('code')} status={e.get('status_code')} "
                  f"msg={e.get('message')} req_id={e.get('request_id')}")

    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()

    err = proc.stderr.read()
    print("---stderr tail (3 lines)---")
    for line in err.splitlines()[-3:]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
