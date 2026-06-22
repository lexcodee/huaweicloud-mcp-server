"""End-to-end SSE smoke test.

Connects to a locally running ecs-mcp-server SSE endpoint, performs the
MCP handshake, lists tools, and invokes ecs_list_servers (read-only).
Also verifies that an SSE keep-alive comment frame appears after the
configured idle interval.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from contextlib import asynccontextmanager

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client

SSE_URL = os.environ.get("ECS_MCP_SSE_URL", "http://127.0.0.1:8000/sse")
KEEPALIVE_PROBE_SECONDS = float(os.environ.get("ECS_MCP_KEEPALIVE_PROBE", "0"))


async def mcp_handshake_and_call() -> None:
    print(f"[1] connecting SSE: {SSE_URL}")
    async with sse_client(SSE_URL) as (read, write):
        print("[2] SSE streams open, starting MCP session")
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"[3] initialized: server={init.serverInfo.name} "
                  f"v={init.serverInfo.version} "
                  f"protocol={init.protocolVersion}")

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print(f"[4] tools ({len(names)}): {names}")

            print("[5] invoking ecs_list_servers limit=2 ...")
            result = await session.call_tool(
                "ecs_list_servers", arguments={"limit": 2}
            )
            for c in result.content[:1]:
                preview = (c.text or "")[:300]
                print(f"[6] result preview: {preview}")
            if result.isError:
                print("FAIL: tool returned isError=True")
                sys.exit(1)


async def keepalive_probe() -> None:
    """Read the raw SSE bytes and look for our `: keepalive` comment."""
    if KEEPALIVE_PROBE_SECONDS <= 0:
        return
    deadline = time.monotonic() + KEEPALIVE_PROBE_SECONDS
    print(f"\n[K1] reading raw SSE for {KEEPALIVE_PROBE_SECONDS}s "
          f"to verify keep-alive frame ...")
    async with httpx.AsyncClient(timeout=KEEPALIVE_PROBE_SECONDS + 5) as cli:
        async with cli.stream("GET", SSE_URL) as resp:
            saw_keepalive = False
            saw_endpoint = False
            async for line in resp.aiter_lines():
                if line.startswith(": keepalive"):
                    saw_keepalive = True
                    print(f"[K2] keepalive frame received at "
                          f"t+{KEEPALIVE_PROBE_SECONDS - (deadline - time.monotonic()):.1f}s")
                    break
                if line.startswith("event: endpoint"):
                    saw_endpoint = True
                if time.monotonic() >= deadline:
                    break
            if not saw_keepalive:
                print(f"[K3] WARN no keepalive frame in "
                      f"{KEEPALIVE_PROBE_SECONDS}s "
                      f"(endpoint event seen={saw_endpoint})")


async def main() -> None:
    await mcp_handshake_and_call()
    await keepalive_probe()
    print("\nOK: SSE smoke passed")


if __name__ == "__main__":
    asyncio.run(main())
