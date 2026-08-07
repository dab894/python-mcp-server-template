"""Credential loading and validation.

The SailPoint Python SDK reads SAIL_BASE_URL / SAIL_CLIENT_ID / SAIL_CLIENT_SECRET
from the environment on its own. All this module does is load a `.env` file (so
local development works without exporting variables by hand) and fail loudly with
a useful message when something is missing -- an MCP server that dies with a
KeyError inside a tool call is miserable to debug from a chat window.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REQUIRED_VARS = ("SAIL_BASE_URL", "SAIL_CLIENT_ID", "SAIL_CLIENT_SECRET")


class ConfigError(RuntimeError):
    """Raised when credentials are missing or malformed."""


@dataclass(frozen=True)
class SailPointSettings:
    base_url: str
    client_id: str
    client_secret: str

    @property
    def tenant(self) -> str:
        """Best-effort tenant name, useful for log lines."""
        host = self.base_url.removeprefix("https://").removeprefix("http://")
        return host.split(".", 1)[0]


def load_dotenv_file() -> None:
    """Load `.env` from the repo root, if present. Real env vars always win."""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)


def load_settings() -> SailPointSettings:
    """Read and validate credentials from the environment."""
    load_dotenv_file()

    missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
    if missing:
        raise ConfigError(
            "Missing SailPoint credentials: "
            + ", ".join(missing)
            + ".\nCopy .env.example to .env and fill in your tenant's Personal "
            "Access Token, or export the variables in your shell."
        )

    base_url = os.environ["SAIL_BASE_URL"].rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ConfigError(
            f"SAIL_BASE_URL must be a full URL (got {base_url!r}). "
            "Example: https://your-tenant.api.identitynow.com"
        )

    return SailPointSettings(
        base_url=base_url,
        client_id=os.environ["SAIL_CLIENT_ID"],
        client_secret=os.environ["SAIL_CLIENT_SECRET"],
    )
