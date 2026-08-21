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
from typing import Any, Sequence

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

# The Search API itself allows far more, but a tool result has to fit in a model's
# context window. 250 matches the ceiling the TypeScript server uses.
MAX_LIMIT = 250

# Applied when the caller does not pass `sort`. Most-privileged first is a useful
# default for "who has access to X" style questions.
DEFAULT_SORT = ["-accessCount", "id"]


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


def _clean_fields(fields: Sequence[str] | None) -> list[str]:
    """Normalise a caller-supplied field/sort list: strip blanks, keep order."""
    if not fields:
        return []
    seen: set[str] = set()
    cleaned: list[str] = []
    for field in fields:
        field = (field or "").strip()
        if field and field not in seen:
            seen.add(field)
            cleaned.append(field)
    return cleaned


def build_search(
    query_string: str,
    *,
    sort: Sequence[str] | None = None,
    attributes: Sequence[str] | None = None,
    include_nested: bool = False,
) -> Search:
    """Assemble the `Search` request body for the identities index.

    Pulled out of the tool body so the filter wiring can be unit-tested without a
    tenant. Two things worth knowing:

    * `attributes` replaces `RESULT_FIELDS` wholesale. That is the point -- a
      caller who names the fields they want should not also get ours.
    * `include_nested` must be passed explicitly. The SDK model defaults it to
      `True`, which would drag `access`, `accounts` and `apps` into every hit.
    """
    includes = _clean_fields(attributes) or RESULT_FIELDS
    return Search(
        indices=["identities"],
        query=Query(query=query_string),
        query_result_filter=QueryResultFilter(includes=includes),
        sort=_clean_fields(sort) or DEFAULT_SORT,
        include_nested=include_nested,
    )


# Elasticsearch plumbing that rides along on every hit and tells the model nothing.
_SEARCH_METADATA = ("_type", "_index")


def strip_metadata(document: dict[str, Any]) -> dict[str, Any]:
    """Drop the search engine's internal keys from a raw result document."""
    return {
        key: value for key, value in document.items() if key not in _SEARCH_METADATA
    }


def total_count(headers: Any) -> int | None:
    """Read `X-Total-Count` out of a response's headers, if it is there."""
    if not headers:
        return None
    for key, value in dict(headers).items():
        if key.lower() == "x-total-count":
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def register(mcp: MCPServer) -> None:
    @mcp.tool(name="search-identities")
    def search_identities(
        query: str,
        limit: int = 10,
        offset: int = 0,
        sort: list[str] | None = None,
        attributes: list[str] | None = None,
        include_nested: bool = False,
        count: bool = False,
    ) -> dict[str, Any]:
        """Search for identities (people) in SailPoint Identity Security Cloud.

        Use this whenever the user asks about a person in SailPoint -- who they
        are, their job title, department, manager, lifecycle state, which sources
        they have accounts on, or how much access they have. Also use it to count
        or page through a population, e.g. "how many people are in Engineering".

        Args:
            query: Who to look for. A plain name or email like `Tyler Mairose`
                works. You can also pass Elasticsearch query-string syntax
                against the identities index for precise filtering, e.g.
                `attributes.department:Engineering AND isManager:true`,
                `email:*@example.com`, `lifecycleState:inactive`, or
                `@access(name:"Administrator")`. Use `*` to match everyone.
            limit: Maximum identities to return, 1-250. Default 10. Keep it small
                unless the user asked for a broad list.
            offset: How many matches to skip before returning results, for paging
                through a population. Default 0. Pair it with `limit`: offset=10,
                limit=10 gives the second page.
            sort: Fields to sort by, most significant first; prefix a field with
                `-` for descending. Example: `["attributes.department",
                "-created"]`. Defaults to most access first.
            attributes: Restrict the fields returned for each identity, which
                keeps the response small on large result sets. Example:
                `["id", "displayName", "email", "attributes.department"]`. When
                you pass this, raw documents are returned with exactly these
                fields instead of the usual summary.
            include_nested: Include each identity's nested `access`, `accounts`
                and `apps` arrays. Answers "what access does this person have",
                but responses get much larger -- use it with a small `limit`, and
                only when the user asked about specific access. Raw documents are
                returned when this is on.
            count: Also return `total_count`, the number of identities matching
                `query` ignoring `limit`/`offset`. Use it when the user asks how
                many, not who. Adds latency, so leave it off otherwise.

        Returns:
            A dict with `query`, `returned`, `offset`, `limit`, and `identities`.
            Each identity is a compact summary of core attributes and access
            counts -- unless `attributes` or `include_nested` was set, in which
            case the raw search documents are passed through. `total_count` is
            present when `count=True`.
        """
        limit = max(1, min(limit, MAX_LIMIT))
        offset = max(0, offset)
        query_string = build_query_string(query)

        # Either flag means the caller asked for a field shape the summarizer
        # would throw away, so hand back what the API actually returned.
        passthrough = bool(_clean_fields(attributes)) or include_nested

        search = build_search(
            query_string,
            sort=sort,
            attributes=attributes,
            include_nested=include_nested,
        )

        log.info(
            "search-identities: %s (limit=%d offset=%d nested=%s count=%s)",
            query_string,
            limit,
            offset,
            include_nested,
            count,
        )

        try:
            if count:
                # Only the *_with_http_info variant exposes X-Total-Count.
                api_response = call_sailpoint(
                    lambda client: SearchApi(client).search_post_v1_with_http_info(
                        search=search, limit=limit, offset=offset, count=True
                    )
                )
                results = api_response.data
                matched = total_count(api_response.headers)
            else:
                results = call_sailpoint(
                    lambda client: SearchApi(client).search_post_v1(
                        search=search, limit=limit, offset=offset
                    )
                )
                matched = None
        except Exception as exc:  # surfaced to the model as tool output, not a crash
            log.exception("search-identities failed")
            return {
                "query": query_string,
                "error": describe_api_error(exc),
                "identities": [],
            }

        documents = [
            document for document in results or [] if isinstance(document, dict)
        ]
        identities = [
            strip_metadata(d) if passthrough else summarize_identity(d)
            for d in documents
        ]

        response: dict[str, Any] = {
            "query": query_string,
            "returned": len(identities),
            "offset": offset,
            "limit": limit,
            "identities": identities,
        }
        if matched is not None:
            response["total_count"] = matched
        if not identities:
            response["note"] = (
                "No identities matched. Try a partial name, an email, or a "
                "wildcard such as `Tyler*`."
            )
        elif offset == 0 and matched is not None and matched > len(identities):
            response["note"] = (
                f"Showing {len(identities)} of {matched} matches. Raise `limit` "
                "or page with `offset` to see more."
            )
        return response
