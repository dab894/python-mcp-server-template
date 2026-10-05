"""`get_access_request_approvals` -- approval history for one access request.

Built on the same pattern as `search_identities`:

  1. Docstring written for the model.
  2. Build the request (here, a `filters` string for the status API).
  3. Run it through `call_sailpoint()`.
  4. Project a compact record per approval step instead of the raw payload.

One access request can ask for several items (a role, two entitlements, ...).
ISC tracks approvals per requested item, so the response groups the approval
steps under each item.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from mcp.server import MCPServer
from sailpoint import AccessRequestsApi

from ..client import call_sailpoint, describe_api_error

log = logging.getLogger(__name__)

# ISC ids are hex GUIDs; anything else would be spliced into the filter string.
_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,64}$")

MAX_LIMIT = 250


def build_filter(access_request_id: str) -> str:
    """Build the `filters` query parameter for one access request id."""
    access_request_id = access_request_id.strip()
    if not _ID_PATTERN.match(access_request_id):
        raise ValueError(
            f"'{access_request_id}' is not a valid access request id. Expected "
            "the 32-character id returned when the request was submitted."
        )
    return f'accessRequestId eq "{access_request_id}"'


def _name(ref: Any) -> Any:
    """Collapse a `{type, id, name}` reference to its name (or id)."""
    if isinstance(ref, dict):
        return ref.get("name") or ref.get("id")
    return ref


def _compact(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if value not in (None, [], {})}


def summarize_approval(approval: dict[str, Any]) -> dict[str, Any]:
    """Flatten one `approvalDetails` entry into an approval step."""
    original = _name(approval.get("originalOwner"))
    current = _name(approval.get("currentOwner"))
    return _compact(
        {
            "status": approval.get("status"),
            "scheme": approval.get("scheme"),
            "approver": current or original,
            "original_approver": original if approval.get("forwarded") else None,
            "forwarded": approval.get("forwarded") or None,
            "comment": approval.get("comment"),
            "decided_or_modified": approval.get("modified"),
            "errors": [
                e.get("text") if isinstance(e, dict) else e
                for e in approval.get("errorMessages") or []
            ],
        }
    )


def summarize_phase(phase: dict[str, Any]) -> dict[str, Any]:
    return _compact(
        {
            "name": phase.get("name"),
            "state": phase.get("state"),
            "result": phase.get("result"),
            "started": phase.get("started"),
            "finished": phase.get("finished"),
        }
    )


def summarize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Reduce one `RequestedItemStatus` to the facts about its approval history."""
    comment = item.get("requesterComment") or {}
    return _compact(
        {
            "item": item.get("name"),
            "item_type": item.get("type"),
            "item_id": item.get("id"),
            "request_type": item.get("requestType"),
            "state": item.get("state"),
            "requested_for": _name(item.get("requestedFor")),
            "requester": _name(item.get("requester")),
            "requester_comment": comment.get("comment") if isinstance(comment, dict) else None,
            "created": item.get("created"),
            "modified": item.get("modified"),
            "approvals": [
                summarize_approval(a)
                for a in item.get("approvalDetails") or []
                if isinstance(a, dict)
            ],
            "phases": [
                summarize_phase(p)
                for p in item.get("accessRequestPhases") or []
                if isinstance(p, dict)
            ],
        }
    )


def register(mcp: MCPServer) -> None:
    @mcp.tool(name="get_access_request_approvals")
    def get_access_request_approvals(
        access_request_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Get the approval history for a SailPoint access request.

        Use this when the user asks who approved or rejected an access request,
        why a request is still pending, whose queue it is sitting in, whether it
        was forwarded, or what comments approvers left.

        Args:
            access_request_id: The id of the access request, e.g.
                `2c91808b6ef1d43e016efba0ce470904`. This is the id returned when
                the request was submitted, not the id of a requested item.
            limit: Maximum requested items to return, 1-250. Default 50. One
                access request can contain several items, each with its own
                approvals.

        Returns:
            A dict with `access_request_id`, `item_count`, and `items`. Each item
            has its name, type, overall `state`, requester and target, and an
            ordered `approvals` list (status, approver, forwarding, comment,
            timestamp) plus the request `phases`.
        """
        limit = max(1, min(limit, MAX_LIMIT))
        try:
            filters = build_filter(access_request_id)
        except ValueError as exc:
            return {"access_request_id": access_request_id, "error": str(exc), "items": []}

        log.info("get_access_request_approvals: %s (limit=%d)", filters, limit)

        try:
            results = call_sailpoint(
                lambda client: AccessRequestsApi(client).list_access_request_status_v1(
                    filters=filters, limit=limit
                )
            )
        except Exception as exc:  # surfaced to the model as tool output, not a crash
            log.exception("get_access_request_approvals failed")
            return {
                "access_request_id": access_request_id,
                "error": describe_api_error(exc),
                "items": [],
            }

        items = [summarize_item(r.to_dict()) for r in results or []]

        response: dict[str, Any] = {
            "access_request_id": access_request_id.strip(),
            "item_count": len(items),
            "items": items,
        }
        if not items:
            response["note"] = (
                "No access request found with that id. Requests for access the "
                "identity already had are dropped by ISC and will not appear. "
                "Viewing other users' requests requires ORG_ADMIN."
            )
        return response
