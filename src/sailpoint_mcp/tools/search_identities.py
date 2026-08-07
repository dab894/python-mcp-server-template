"""`search_identities` -- find identities via the ISC Search API.

This is the reference tool: read it top to bottom and you have the whole pattern
for building your own. The shape is always the same:

  1. Describe the tool in the docstring (the model reads this to decide when to
     call it, so write it for the model).
  2. Build the SDK request object.
  3. Run it through `call_sailpoint()` so auth and retry are handled.
  4. Return a small, clean dict -- not the raw API payload.

Step 4 matters more than it looks. A single ISC identity document is several
kilobytes of JSON; ten of them will bury the useful facts in an LLM's context
window. Project the fields you actually need.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from mcp.server import MCPServer
from sailpoint import SearchApi
from sailpoint.search.models.query import Query
from sailpoint.search.models.query_result_filter import QueryResultFilter
from sailpoint.search.models.search import Search

from ..client import call_sailpoint, describe_api_error

log = logging.getLogger(__name__)

# Fields pulled back from the identities index. Trimmed on purpose -- see above.
RESULT_FIELDS = [
    "id",
    "name",
    "displayName",
    "firstName",
    "lastName",
    "email",
    "created",
    "lifecycleState",
    "identityStatus",
    "isManager",
    "inactive",
    "manager.name",
    "manager.displayName",
    "attributes.department",
    "attributes.jobTitle",
    "attributes.cloudLifecycleState",
    "source.name",
    "accounts.source.name",
    "accessCount",
    "entitlementCount",
    "roleCount",
    "accessProfileCount",
]

# Characters/words that mean the caller wrote real Elasticsearch query syntax and
# we should pass it through untouched instead of treating it as a name.
_QUERY_SYNTAX = re.compile(r'[:"*()~^\[\]]|\b(AND|OR|NOT|TO)\b')

MAX_LIMIT = 50


def build_query_string(query: str) -> str:
    """Turn a natural-language-ish query into an ISC search query string.

    A bare name like `Tyler Mairose` becomes the phrase `"Tyler Mairose"`, which
    keeps the two words together instead of matching every Tyler and every
    Mairose. Anything that already contains query syntax -- `email:t*@acme.com`,
    `attributes.department:Sales AND isManager:true` -- is left alone.
    """
    query = query.strip()
    if _QUERY_SYNTAX.search(query):
        return query
    return f'"{query}"'


def _get(document: dict[str, Any], path: str) -> Any:
    """Read a dotted path out of a search result, tolerating missing branches."""
    current: Any = document
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


def summarize_identity(document: dict[str, Any]) -> dict[str, Any]:
    """Flatten one raw identity document into a compact, readable record."""
    accounts = document.get("accounts") or []
    sources = sorted(
        {
            name
            for account in accounts
            if isinstance(account, dict)
            and (name := _get(account, "source.name")) is not None
        }
    )

    access_counts = {
        "total_access": document.get("accessCount"),
        "entitlements": document.get("entitlementCount"),
        "roles": document.get("roleCount"),
        "access_profiles": document.get("accessProfileCount"),
    }

    summary = {
        "id": document.get("id"),
        "name": document.get("displayName") or document.get("name"),
        "username": document.get("name"),
        "email": document.get("email"),
        "job_title": _get(document, "attributes.jobTitle"),
        "department": _get(document, "attributes.department"),
        "manager": _get(document, "manager.displayName") or _get(document, "manager.name"),
        "lifecycle_state": document.get("lifecycleState")
        or _get(document, "attributes.cloudLifecycleState"),
        "identity_status": document.get("identityStatus"),
        "is_manager": document.get("isManager"),
        "inactive": document.get("inactive"),
        "authoritative_source": _get(document, "source.name"),
        "account_sources": sources,
        # Omit the whole block when the identity has no counts at all.
        "access_counts": {
            key: value for key, value in access_counts.items() if value is not None
        },
        "created": document.get("created"),
    }
    # Drop empty keys so the model isn't reading a wall of nulls.
    return {key: value for key, value in summary.items() if value not in (None, [], {})}


def register(mcp: MCPServer) -> None:
    @mcp.tool(name="search-identities")
    def search_identities(query: str, limit: int = 10) -> dict[str, Any]:
        """Search for identities (people) in SailPoint Identity Security Cloud.

        Use this whenever the user asks about a person in SailPoint -- who they
        are, their job title, department, manager, lifecycle state, which sources
        they have accounts on, or how much access they have.

        Args:
            query: Who to look for. A plain name or email like `Tyler Mairose`
                works. You can also pass Elasticsearch query-string syntax
                against the identities index for precise filtering, e.g.
                `attributes.department:Engineering AND isManager:true`,
                `email:*@example.com`, or `lifecycleState:inactive`.
            limit: Maximum identities to return, 1-50. Default 10. Keep it small
                unless the user asked for a broad list.

        Returns:
            A dict with `query`, `returned` (count), and `identities` -- each a
            compact record of the person's core attributes and access counts.
        """
        limit = max(1, min(limit, MAX_LIMIT))
        query_string = build_query_string(query)

        search = Search(
            indices=["identities"],
            query=Query(query=query_string),
            query_result_filter=QueryResultFilter(includes=RESULT_FIELDS),
            sort=["-accessCount", "id"],
        )

        log.info("search-identities: %s (limit=%d)", query_string, limit)

        try:
            results = call_sailpoint(
                lambda client: SearchApi(client).search_post_v1(
                    search=search, limit=limit
                )
            )
        except Exception as exc:  # surfaced to the model as tool output, not a crash
            log.exception("search-identities failed")
            return {
                "query": query_string,
                "error": describe_api_error(exc),
                "identities": [],
            }

        identities = [
            summarize_identity(document)
            for document in results or []
            if isinstance(document, dict)
        ]

        response: dict[str, Any] = {
            "query": query_string,
            "returned": len(identities),
            "identities": identities,
        }
        if not identities:
            response["note"] = (
                "No identities matched. Try a partial name, an email, or a "
                "wildcard such as `Tyler*`."
            )
        return response
