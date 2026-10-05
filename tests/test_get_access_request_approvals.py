"""Unit tests for the approval-history helpers -- no tenant required."""

import pytest

from sailpoint_mcp.tools.get_access_request_approvals import (
    build_filter,
    summarize_item,
)


def test_build_filter_targets_the_access_request_id():
    assert (
        build_filter(" 2c91808b6ef1d43e016efba0ce470904 ")
        == 'accessRequestId eq "2c91808b6ef1d43e016efba0ce470904"'
    )


@pytest.mark.parametrize("bad", ["", 'abc" or id ne "x', "id with spaces", "a" * 65])
def test_build_filter_rejects_values_that_would_alter_the_filter(bad):
    with pytest.raises(ValueError):
        build_filter(bad)


def test_summarize_item_flattens_approval_history():
    summary = summarize_item(
        {
            "id": "item-1",
            "name": "Engineering Admin",
            "type": "ROLE",
            "state": "REJECTED",
            "requestType": "GRANT_ACCESS",
            "requester": {"type": "IDENTITY", "id": "r1", "name": "Ada Lovelace"},
            "requestedFor": {"type": "IDENTITY", "id": "t1", "name": "Tyler Mairose"},
            "requesterComment": {"comment": "Need it for on-call"},
            "approvalDetails": [
                {
                    "status": "APPROVED",
                    "scheme": "MANAGER",
                    "forwarded": False,
                    "originalOwner": {"name": "Grace Hopper"},
                    "currentOwner": {"name": "Grace Hopper"},
                    "comment": "ok",
                    "modified": "2026-10-01T10:00:00Z",
                },
                {
                    "status": "REJECTED",
                    "scheme": "ROLE_OWNER",
                    "forwarded": True,
                    "originalOwner": {"name": "Alan Turing"},
                    "currentOwner": {"name": "Linus Torvalds"},
                    "comment": "Too broad",
                    "errorMessages": [],
                },
            ],
            "accessRequestPhases": [{"name": "APPROVAL_PHASE", "state": "COMPLETED", "result": "FAILED"}],
        }
    )

    assert summary["item"] == "Engineering Admin"
    assert summary["requester"] == "Ada Lovelace"
    assert summary["requested_for"] == "Tyler Mairose"
    assert summary["requester_comment"] == "Need it for on-call"

    first, second = summary["approvals"]
    assert first == {
        "status": "APPROVED",
        "scheme": "MANAGER",
        "approver": "Grace Hopper",
        "comment": "ok",
        "decided_or_modified": "2026-10-01T10:00:00Z",
    }
    assert second["approver"] == "Linus Torvalds"
    assert second["original_approver"] == "Alan Turing"
    assert second["forwarded"] is True
    assert summary["phases"] == [{"name": "APPROVAL_PHASE", "state": "COMPLETED", "result": "FAILED"}]


def test_summarize_item_tolerates_a_sparse_record():
    assert summarize_item({"id": "x"}) == {"item_id": "x"}
