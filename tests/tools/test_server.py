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
    names = {spec.tool.name for spec in server.TOOL_REGISTRY}
    # Spot-check across feature areas so a dropped registration is caught.
    assert {"me", "search_books", "get_trending_books", "follow_user"} <= names


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
