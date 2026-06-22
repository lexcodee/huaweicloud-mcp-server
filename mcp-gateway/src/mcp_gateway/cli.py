"""CLI entrypoint: ``mcp-gateway --manifest manifest.yaml [--enable a,b] [--disable c]``."""
from __future__ import annotations

import argparse
import logging
import os
import sys

import uvicorn

from .gateway import DEFAULT_MANIFEST_PATH, build_app


def _build_factory(args: argparse.Namespace):
    def factory():
        return build_app(
            args.manifest,
            cli_enable=args.enable,
            cli_disable=args.disable,
        )

    return factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcp-gateway", description="Multi-MCP gateway")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH, help="Path to manifest.yaml")
    parser.add_argument(
        "--enable",
        action="append",
        default=None,
        help="Comma-separated list of services to enable (overrides manifest + env).",
    )
    parser.add_argument(
        "--disable",
        action="append",
        default=None,
        help="Comma-separated list of services to disable after env/CLI enable layers.",
    )
    parser.add_argument("--host", default=os.environ.get("MCP_GATEWAY_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_GATEWAY_PORT", "8080")))
    parser.add_argument("--log-level", default=os.environ.get("MCP_GATEWAY_LOG_LEVEL", "info"))
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Build the app, print the mount plan, then exit without starting uvicorn.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.print_only:
        app = build_app(args.manifest, cli_enable=args.enable, cli_disable=args.disable)
        # The Starlette routes carry mount_path; reach into the manifest log lines
        # instead of introspecting routes, which is friendlier output.
        sys.stdout.write("Gateway built. See logs above for mounted/skipped services.\n")
        return 0

    uvicorn.run(
        _build_factory(args),
        host=args.host,
        port=args.port,
        factory=True,
        log_level=args.log_level.lower(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
