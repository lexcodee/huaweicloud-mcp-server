"""CLI entrypoint: ``mcp-gateway serve --manifest manifest.yaml`` or ``mcp-gateway token ...``."""
from __future__ import annotations

import argparse
import os
import sys

import uvicorn

from .gateway import DEFAULT_MANIFEST_PATH, build_app
from .logfmt import setup_logging
from .token import add_token_subcommands


def _build_factory(args: argparse.Namespace):
    def factory():
        return build_app(
            args.manifest,
            cli_enable=args.enable,
            cli_disable=args.disable,
        )

    return factory


def _cmd_serve(args: argparse.Namespace) -> int:
    """Start the gateway server (default when no subcommand given)."""
    log_format = os.environ.get("MCP_GATEWAY_LOG_FORMAT", "text").strip().lower()
    setup_logging(level=args.log_level, fmt=log_format)

    if args.print_only:
        app = build_app(args.manifest, cli_enable=args.enable, cli_disable=args.disable)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcp-gateway", description="Multi-MCP gateway")
    subparsers = parser.add_subparsers(dest="command")

    # --- serve (default sub-command) ---
    serve_p = subparsers.add_parser(
        "serve",
        help="Start the gateway server (default when no subcommand given)",
    )
    serve_p.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH, help="Path to manifest.yaml")
    serve_p.add_argument(
        "--enable",
        action="append",
        default=None,
        help="Comma-separated list of services to enable (overrides manifest + env).",
    )
    serve_p.add_argument(
        "--disable",
        action="append",
        default=None,
        help="Comma-separated list of services to disable after env/CLI enable layers.",
    )
    serve_p.add_argument("--host", default=os.environ.get("MCP_GATEWAY_HOST", "0.0.0.0"))
    serve_p.add_argument("--port", type=int, default=int(os.environ.get("MCP_GATEWAY_PORT", "8080")))
    serve_p.add_argument("--log-level", default=os.environ.get("MCP_GATEWAY_LOG_LEVEL", "info"))
    serve_p.add_argument(
        "--print-only",
        action="store_true",
        help="Build the app, print the mount plan, then exit without starting uvicorn.",
    )
    serve_p.set_defaults(func=_cmd_serve)

    # --- token sub-commands (keygen / create / verify) ---
    add_token_subcommands(subparsers)

    # If the first positional arg is a known subcommand, parse normally.
    # Otherwise, prepend 'serve' so bare flags like --print-only work.
    raw = argv if argv is not None else sys.argv[1:]
    known_commands = {"serve", "token"}
    if raw and raw[0] in known_commands:
        args = parser.parse_args(argv)
    else:
        args = parser.parse_args(["serve"] + list(raw))

    if hasattr(args, "func"):
        return args.func(args)

    # Fallback — should not reach here.
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
