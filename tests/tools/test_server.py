"""Smoke tests for server wiring — guards against MCP SDK API drift.

0.7.0 shipped broken because nothing imported server.py (handlers were tested
directly), so an incompatible MCP `Server` API slipped through. These tests
exercise the registration path.
"""

from types import SimpleNamespace

from hardcover_mcp import server


def test_server_constructs_and_builds_init_options():
    # Importing the module already ran Server(...) — if the SDK's constructor API
    # drifts (e.g. on_list_tools/on_call_tool removed), import fails here. Building
    # init options exercises the run() startup path too.
    assert server.server.create_initialization_options() is not None


async def test_list_tools_returns_registry():
    result = await server.list_tools(None, None)
    assert len(result.tools) == len(server.TOOL_REGISTRY)
    assert result.tools[0].name


def test_expected_tools_registered():
    names = {tool.name for tool, _ in server.TOOL_REGISTRY}
    # Spot-check across feature areas so a dropped registration is caught.
    assert {"me", "search_books", "get_trending_books", "follow_user"} <= names


async def test_call_tool_unknown_is_error():
    result = await server.call_tool(None, SimpleNamespace(name="nope", arguments={}))
    assert result.is_error
    assert "Unknown tool" in result.content[0].text
