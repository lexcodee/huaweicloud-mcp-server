"""Logging setup with secret-masking filter.

- Logs go to stderr by default (stdout is reserved for MCP JSON-RPC traffic).
- If CTS_MCP_LOG_FILE is set, a rotating file handler is also attached.
- A regex filter scrubs accidental AK/SK leakage from any log message.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional


# Heuristics for AK/SK shapes; conservative to avoid mangling unrelated text.
# Huawei Cloud AK is typically 20+ chars alnum; SK is 40+ chars alnum.
_SECRET_PATTERNS = [
    re.compile(r"\b([A-Z0-9]{20,40})\b"),  # likely AK
    re.compile(r"\b([A-Za-z0-9+/=]{40,})\b"),  # likely SK
]


class SecretMaskingFilter(logging.Filter):
    """Replace tokens that look like AK/SK in log records."""

    def __init__(self, known_secrets: Optional[list[str]] = None) -> None:
        super().__init__()
        self.known_secrets = [s for s in (known_secrets or []) if s]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True

        masked = msg
        # 1) replace exact known secrets first (most reliable)
        for s in self.known_secrets:
            if s and s in masked:
                masked = masked.replace(s, _mask(s))

        # 2) heuristic patterns (best-effort)
        for pat in _SECRET_PATTERNS:
            masked = pat.sub(lambda m: _mask(m.group(1)), masked)

        if masked != msg:
            record.msg = masked
            record.args = ()
        return True


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    known_secrets: Optional[list[str]] = None,
) -> logging.Logger:
    """Configure root logger for the server. Idempotent."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    root.setLevel(getattr(logging, level, logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    masker = SecretMaskingFilter(known_secrets=known_secrets)

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setFormatter(fmt)
    stderr_handler.addFilter(masker)
    root.addHandler(stderr_handler)

    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
            file_handler = RotatingFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(fmt)
            file_handler.addFilter(masker)
            root.addHandler(file_handler)
        except OSError as e:
            root.error("failed to attach log file %s: %s", log_file, e)

    # Quiet down noisy third-party loggers
    logging.getLogger("huaweicloudsdkcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return logging.getLogger("cts_mcp_server")
