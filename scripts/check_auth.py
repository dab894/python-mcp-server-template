#!/usr/bin/env python3
"""Verify credentials and the search tool without an MCP client in the loop.

    python scripts/check_auth.py
    python scripts/check_auth.py "Tyler Mairose"

Run this first when something is broken -- it isolates "my PAT is wrong" from
"my MCP client config is wrong".
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sailpoint_mcp.client import get_api_client  # noqa: E402
from sailpoint_mcp.config import ConfigError, load_settings  # noqa: E402
from sailpoint_mcp.tools.search_identities import (  # noqa: E402
    build_query_string,
    summarize_identity,
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"OK  credentials found for tenant '{settings.tenant}' ({settings.base_url})")

    try:
        get_api_client()
    except Exception as exc:
        print(f"FAIL: could not get an access token: {type(exc).__name__}: {exc}")
        return 1
    print("OK  authenticated (access token retrieved)")

    query = sys.argv[1] if len(sys.argv) > 1 else "a*"
    from sailpoint import SearchApi
    from sailpoint.search.models.query import Query
    from sailpoint.search.models.search import Search

    from sailpoint_mcp.client import call_sailpoint

    search = Search(indices=["identities"], query=Query(query=build_query_string(query)))
    try:
        results = call_sailpoint(
            lambda client: SearchApi(client).search_post_v1(search=search, limit=3)
        )
    except Exception as exc:
        print(f"FAIL: search request failed: {type(exc).__name__}: {exc}")
        return 1

    print(f"OK  search for {query!r} returned {len(results or [])} result(s)")
    for document in results or []:
        print(json.dumps(summarize_identity(document), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
