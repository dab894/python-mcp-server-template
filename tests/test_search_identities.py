"""Unit tests for the pure helpers -- no tenant or credentials required."""

from sailpoint_mcp.tools.search_identities import build_query_string, summarize_identity


def test_plain_name_is_quoted_as_a_phrase():
    assert build_query_string("Tyler Mairose") == '"Tyler Mairose"'


def test_existing_query_syntax_is_passed_through():
    for query in (
        "attributes.department:Engineering AND isManager:true",
        "email:*@example.com",
        '"Tyler Mairose"',
    ):
        assert build_query_string(query) == query


def test_summarize_flattens_and_drops_empties():
    summary = summarize_identity(
        {
            "id": "2c9180875",
            "name": "tyler.mairose",
            "displayName": "Tyler Mairose",
            "email": "tyler.mairose@example.com",
            "manager": {"displayName": "Ada Lovelace"},
            "attributes": {"jobTitle": "Developer Tools Lead", "department": None},
            "accounts": [
                {"source": {"name": "Active Directory"}},
                {"source": {"name": "Workday"}},
                {"source": {"name": "Active Directory"}},
                {"nosource": True},
            ],
            "accessCount": 42,
            "lifecycleState": None,
        }
    )

    assert summary["name"] == "Tyler Mairose"
    assert summary["username"] == "tyler.mairose"
    assert summary["manager"] == "Ada Lovelace"
    assert summary["job_title"] == "Developer Tools Lead"
    assert summary["account_sources"] == ["Active Directory", "Workday"]
    assert summary["access_counts"]["total_access"] == 42
    assert "department" not in summary
    assert "lifecycle_state" not in summary


def test_summarize_tolerates_a_sparse_document():
    assert summarize_identity({"id": "abc"}) == {"id": "abc"}
