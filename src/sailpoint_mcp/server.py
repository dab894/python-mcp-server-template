"""MCP server entry point.

Transport is stdio: the MCP client (Claude Code, Claude Desktop, Cursor, ...)
launches this process and speaks JSON-RPC over stdin/stdout. That has one hard
rule -- *nothing* may be printed to stdout except protocol traffic, so all
logging goes to stderr.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys

from mcp.server import MCPServer

from . import __version__, tools
from .config import ConfigError, load_settings

log = logging.getLogger("sailpoint_mcp")

INSTRUCTIONS = """\
Tools for SailPoint Identity Security Cloud (ISC), backed by the SailPoint
Python SDK. Use them to look up identities and other governance data in the
connected tenant instead of guessing or asking the user to check the UI.
"""


def configure_logging() -> None:
    level = os.environ.get("SAILPOINT_MCP_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        stream=sys.stderr,  # never stdout -- see module docstring
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # While the stdio transport is running it points fd 1 at stderr, so a stray
    # print() from library code is harmless -- unless it sits in Python's stdout
    # buffer until interpreter exit, by which point fd 1 has been restored to the
    # protocol pipe and the client gets a JSON parse error. Line buffering flushes
    # such writes while the diversion is still in place.
    with contextlib.suppress(Exception):  # not a TextIOWrapper under some hosts
        sys.stdout.reconfigure(line_buffering=True)


def build_server() -> MCPServer:
    """Create the server and register every tool module."""
    mcp = MCPServer("sailpoint", instructions=INSTRUCTIONS, version=__version__)
    registered = tools.register_all(mcp)
    log.info("Loaded %d tool module(s): %s", len(registered), ", ".join(registered))
    return mcp


def main() -> None:
    configure_logging()

    # Validate credentials at startup so misconfiguration shows up immediately
    # rather than as a confusing failure inside the first tool call. Note that
    # no token is requested yet -- authentication happens on first use.
    try:
        settings = load_settings()
        log.info("SailPoint tenant: %s (%s)", settings.tenant, settings.base_url)
    except ConfigError as exc:
        log.error("%s", exc)
        sys.exit(1)

    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
