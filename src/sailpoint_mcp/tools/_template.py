"""Copy me.

    cp src/sailpoint_mcp/tools/_template.py src/sailpoint_mcp/tools/my_tool.py

Then edit, restart the server, and your tool is live. Files starting with `_` are
skipped by the auto-loader, so this one never registers.

Finding the right SDK call:
  * API + SDK reference: https://developer.sailpoint.com/docs/api/
  * Every API class is exported flat: `from sailpoint import SourcesApi, AccountsApi, ...`
  * Models live under their partition: `from sailpoint.sources.models.source import Source`
  * Methods are suffixed with their API version, e.g. `list_sources_v3`, `search_post_v1`.
    In a Python REPL: `from sailpoint import SourcesApi; print(dir(SourcesApi))`
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import MCPServer

# 1. Import the API class you need.
# from sailpoint import SourcesApi
from ..client import call_sailpoint, describe_api_error

log = logging.getLogger(__name__)


def register(mcp: MCPServer) -> None:
    """Required. The auto-loader calls this at startup."""

    @mcp.tool(name="my-tool")
    def my_tool(some_argument: str, limit: int = 10) -> dict[str, Any]:
        """One-line summary of what this does -- the model reads this to decide
        whether to call the tool, so describe *when* it applies.

        Args:
            some_argument: What the caller should pass, with a concrete example.
            limit: Maximum results to return. Default 10.

        Returns:
            Describe the shape you return.
        """
        limit = max(1, min(limit, 50))

        try:
            # 2. Make the call. `call_sailpoint` supplies the authenticated
            #    ApiClient and retries once if the token was rejected.
            # result = call_sailpoint(
            #     lambda client: SourcesApi(client).list_sources_v3(limit=limit)
            # )
            raise NotImplementedError("Replace this with a real SailPoint call")
        except Exception as exc:
            # 3. Return errors as data. Raising inside a tool gives the model a
            #    stack trace; a sentence tells it what to do next.
            log.exception("my-tool failed")
            return {"error": describe_api_error(exc)}

        # 4. Return a small, flat summary -- not the raw API payload. SDK models
        #    are pydantic, so `model.to_dict()` gets you a plain dict to trim.
        return {"results": []}
