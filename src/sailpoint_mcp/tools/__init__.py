"""Tool auto-discovery.

Every module in this package that defines a module-level `register(mcp)` function
is imported and registered at startup. To add a tool, drop a new file in this
directory -- there is no central list to edit and no import to wire up.

Modules whose names start with `_` are skipped, which is how `_template.py` stays
out of the running server.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server import MCPServer

log = logging.getLogger(__name__)


def register_all(mcp: "MCPServer") -> list[str]:
    """Import every tool module and let it register itself. Returns module names."""
    registered: list[str] = []

    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_"):
            continue

        module = importlib.import_module(f"{__name__}.{module_info.name}")
        register = getattr(module, "register", None)
        if register is None:
            log.warning(
                "Skipping %s: no register(mcp) function found", module_info.name
            )
            continue

        register(mcp)
        registered.append(module_info.name)
        log.info("Registered tool module: %s", module_info.name)

    return registered
