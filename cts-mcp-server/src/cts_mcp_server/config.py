"""Configuration loading and validation.

Reads Huawei Cloud credentials and CTS settings from environment variables.
The CTS server REUSES the same env vars as the sibling ECS / CodeArts
Pipeline MCP servers (single shared ``.env`` in the repo root):

    HUAWEICLOUD_ACCESS_KEY_ID       (required)
    HUAWEICLOUD_SECRET_ACCESS_KEY   (required)
    HUAWEICLOUD_PROJECT_ID          (required — CTS is project-scoped, so
                                     BasicCredentials MUST receive project_id)
    HUAWEICLOUD_REGION              (required — e.g. af-south-1)
    CTS_DEFAULT_TIMEZONE            (optional, default Asia/Shanghai)
    CTS_MCP_LOG_FILE                (optional)
    CTS_MCP_LOG_LEVEL               (optional, default INFO)

Fails fast on missing values. Provides secret masking utility.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()  # local dev convenience; no-op in production if no .env present
except ImportError:  # pragma: no cover
    pass


REQUIRED_VARS = (
    "HUAWEICLOUD_ACCESS_KEY_ID",
    "HUAWEICLOUD_SECRET_ACCESS_KEY",
    "HUAWEICLOUD_PROJECT_ID",
    "HUAWEICLOUD_REGION",
)
DEFAULT_TIMEZONE = "Asia/Shanghai"


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration."""

    access_key_id: str
    secret_access_key: str
    project_id: str
    region: str
    default_timezone: str
    log_file: Optional[str]
    log_level: str

    def masked(self) -> dict:
        """Return a dict suitable for logging — secrets masked."""
        return {
            "access_key_id": mask_secret(self.access_key_id),
            "secret_access_key": mask_secret(self.secret_access_key),
            "project_id": self.project_id,
            "region": self.region,
            "default_timezone": self.default_timezone,
            "log_file": self.log_file,
            "log_level": self.log_level,
        }


def mask_secret(value: Optional[str]) -> str:
    """Mask a secret value, keeping first 4 and last 4 chars only."""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def load_settings() -> Settings:
    """Load settings from env. Exit(2) if required vars missing."""
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        hint = ""
        if "HUAWEICLOUD_PROJECT_ID" in missing:
            hint = (
                "\nNOTE: CTS is a project-scoped service — HUAWEICLOUD_PROJECT_ID "
                "is mandatory and must be passed to BasicCredentials, otherwise "
                "the SDK will fail to sign requests."
            )
        sys.stderr.write(
            "ERROR: missing required environment variables: "
            + ", ".join(missing)
            + hint
            + "\n"
        )
        sys.exit(2)

    return Settings(
        access_key_id=os.environ["HUAWEICLOUD_ACCESS_KEY_ID"].strip(),
        secret_access_key=os.environ["HUAWEICLOUD_SECRET_ACCESS_KEY"].strip(),
        project_id=os.environ["HUAWEICLOUD_PROJECT_ID"].strip(),
        region=os.environ["HUAWEICLOUD_REGION"].strip(),
        default_timezone=os.environ.get("CTS_DEFAULT_TIMEZONE", DEFAULT_TIMEZONE).strip(),
        log_file=os.environ.get("CTS_MCP_LOG_FILE") or None,
        log_level=os.environ.get("CTS_MCP_LOG_LEVEL", "INFO").upper(),
    )
