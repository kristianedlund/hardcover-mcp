"""Smoke tests for server wiring — guards against MCP SDK API drift.

0.7.0 shipped broken because nothing imported server.py (handlers were tested
directly), so an incompatible MCP `Server` API slipped through. These tests
exercise the registration path.
"""

import dataclasses
from types import SimpleNamespace

import pytest

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
    # Exact list so an accidental addition, removal, or rename is caught.
    names = {spec.tool.name for spec in server.TOOL_REGISTRY}
    assert names == {
        # core
        "search_books",
        "get_user",
        # catalog
        "get_book",
        "get_edition",
        "get_author",
        "get_series",
        "get_publisher",
        "get_trending_books",
        "get_vibes",
        # library
        "get_user_library",
        "get_user_book",
        "get_owned_books",
        "get_reading_stats",
        "set_user_book",
        "set_edition_owned",
        "set_user_book_read",
        "delete_user_book_read",
        "delete_user_book",
        "get_reading_goal",
        "set_reading_goal",
        # lists
        "get_list",
        "set_list",
        "delete_list",
        "set_list_book",
        # journal
        "get_reading_journal",
        "set_journal_entry",
        "delete_journal_entry",
        # social
        "get_activity_feed",
        "set_following",
        "get_prompts",
        "set_prompt_answer",
    }


async def test_call_tool_unknown_is_error():
    result = await server.call_tool(None, SimpleNamespace(name="nope", arguments={}))
    assert result.is_error
    assert "Unknown tool" in result.content[0].text


def test_every_tool_is_annotated_and_described():
    for spec in server.TOOL_REGISTRY:
        assert spec.tool.annotations is not None, spec.tool.name
        assert spec.tool.annotations.read_only_hint is not None, spec.tool.name
        assert spec.tool.description, spec.tool.name


def test_collect_tools_rejects_duplicates(monkeypatch):
    dup = SimpleNamespace(TOOLS=[server.TOOL_REGISTRY[0], server.TOOL_REGISTRY[0]])
    monkeypatch.setattr(server, "_MODULES", (dup,))
    with pytest.raises(ValueError, match="Duplicate tool name"):
        server._collect_tools()


def test_collect_tools_rejects_unknown_toolset(monkeypatch):
    bad = dataclasses.replace(server.TOOL_REGISTRY[0], toolset="nope")
    monkeypatch.setattr(server, "_MODULES", (SimpleNamespace(TOOLS=[bad]),))
    with pytest.raises(ValueError, match="unknown toolset"):
        server._collect_tools()
