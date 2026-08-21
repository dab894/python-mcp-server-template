"""Unit tests for the pure helpers -- no tenant or credentials required."""

from sailpoint_mcp.tools.search_identities import (
    DEFAULT_SORT,
    RESULT_FIELDS,
    build_query_string,
    build_search,
    strip_metadata,
    summarize_identity,
    total_count,
)


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


def test_build_search_defaults_to_trimmed_fields_and_no_nesting():
    search = build_search('"Tyler Mairose"')

    assert search.indices == ["identities"]
    assert search.query.query == '"Tyler Mairose"'
    assert search.query_result_filter.includes == RESULT_FIELDS
    assert search.sort == DEFAULT_SORT
    # The SDK model defaults include_nested to True; we must override it.
    assert search.include_nested is False


def test_attributes_replace_the_default_field_list():
    search = build_search("*", attributes=["id", " displayName ", "", "id"])

    assert search.query_result_filter.includes == ["id", "displayName"]


def test_sort_and_include_nested_are_passed_through():
    search = build_search("*", sort=["displayName", "-created"], include_nested=True)

    assert search.sort == ["displayName", "-created"]
    assert search.include_nested is True


def test_blank_sort_falls_back_to_the_default():
    assert build_search("*", sort=["", "  "]).sort == DEFAULT_SORT


def test_total_count_reads_the_header_case_insensitively():
    assert total_count({"X-Total-Count": "137"}) == 137
    assert total_count({"x-total-count": "0"}) == 0


def test_total_count_handles_missing_or_junk_headers():
    assert total_count(None) is None
    assert total_count({}) is None
    assert total_count({"X-Total-Count": "many"}) is None


def test_strip_metadata_removes_only_search_internals():
    assert strip_metadata(
        {"id": "abc", "displayName": "A", "type": "identity", "_type": "identity", "_index": "939"}
    ) == {"id": "abc", "displayName": "A", "type": "identity"}
