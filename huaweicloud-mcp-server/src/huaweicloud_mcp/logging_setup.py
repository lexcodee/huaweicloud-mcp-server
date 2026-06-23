"""Structured logging setup with secret masking.

Configures a single root logger for the huaweicloud_mcp package.
Supports optional log file, configurable level, and automatic masking
of known secrets (AK/SK) in log output via a custom Filter.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

_PACKAGE_LOGGER = "huaweicloud_mcp"


class SecretMaskingFilter(logging.Filter):
    """Redact known secret values from log records."""

    def __init__(self, known_secrets: list[str]) -> None:
        super().__init__()
        self._patterns: list[tuple[str, str]] = []
        for s in known_secrets:
            if s and len(s) > 4:
                self._patterns.append((re.escape(s), "***MASKED***"))

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pat, repl in self._patterns:
            if pat in msg:
                msg = msg.replace(pat, repl)
        record.msg = msg
        record.args = ()
        return True


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    known_secrets: Optional[list[str]] = None,
) -> logging.Logger:
    """Configure and return the package logger.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional file path; if None, logs go to stderr only.
        known_secrets: List of secret strings to mask in log output.
    """
    logger = logging.getLogger(_PACKAGE_LOGGER)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    # Clear existing handlers (idempotent for tests / re-entry).
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler: logging.Handler
    if log_file:
        handler = logging.FileHandler(log_file)
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(fmt)

    if known_secrets:
        handler.addFilter(SecretMaskingFilter(known_secrets))

    logger.addHandler(handler)

    # Also set the SDK loggers to WARNING to reduce noise.
    for sdk_pkg in (
        "huaweicloudsdkcore",
        "huaweicloudsdkecs",
        "huaweicloudsdkcodeartspipeline",
        "huaweicloudsdkcts",
    ):
        logging.getLogger(sdk_pkg).setLevel(logging.WARNING)

    return logger
