"""Logging setup with secret masking for the CodeArts Pipeline MCP server.

stderr is mandatory for stdio MCP transport (stdout is JSON-RPC).
"""
from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from typing import Iterable, Optional

# Heuristic patterns. Conservative: prefer false-positive masking over leaks.
_SECRET_PATTERNS = [
    re.compile(r"\b([A-Z0-9]{20,40})\b"),       # likely AK (uppercase alnum)
    re.compile(r"\b([A-Za-z0-9+/=]{40,})\b"),   # likely SK (mixed alnum + b64)
]


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


class SecretMaskingFilter(logging.Filter):
    """Strip credentials from every log record before emission."""

    def __init__(self, known_secrets: Optional[Iterable[str]] = None) -> None:
        super().__init__()
        self.known_secrets = [s for s in (known_secrets or []) if s]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True

        masked = msg
        for s in self.known_secrets:
            if s and s in masked:
                masked = masked.replace(s, _mask(s))
        for pat in _SECRET_PATTERNS:
            masked = pat.sub(lambda m: _mask(m.group(1)), masked)

        if masked != msg:
            record.msg = masked
            record.args = ()
        return True


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    known_secrets: Optional[Iterable[str]] = None,
) -> logging.Logger:
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)  # idempotent for tests

    root.setLevel(getattr(logging, level, logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    masker = SecretMaskingFilter(known_secrets=known_secrets)

    # CRITICAL: stderr only. stdout is reserved for MCP JSON-RPC.
    sh = logging.StreamHandler(stream=sys.stderr)
    sh.setFormatter(fmt)
    sh.addFilter(masker)
    root.addHandler(sh)

    if log_file:
        fh = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=3)
        fh.setFormatter(fmt)
        fh.addFilter(masker)
        root.addHandler(fh)

    # Quiet noisy SDK loggers — they often log full request bodies at DEBUG.
    logging.getLogger("huaweicloudsdkcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return logging.getLogger("pipeline_mcp_server")
