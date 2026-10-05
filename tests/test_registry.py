"""The auto-loader must actually find and register the shipped tools."""

from mcp.server import MCPServer

from sailpoint_mcp import tools


def test_register_all_registers_search_identities():
    mcp = MCPServer("test")
    registered = tools.register_all(mcp)

    assert "search_identities" in registered
    assert "get_access_request_approvals" in registered
    assert "_template" not in registered


def test_search_identities_is_exposed_with_a_description():
    import asyncio

    mcp = MCPServer("test")
    tools.register_all(mcp)

    listed = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    assert "search_identities" in listed
    assert listed["search_identities"].description
