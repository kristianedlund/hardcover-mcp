"""Tests for HARDCOVER_TOOLSETS / HARDCOVER_READ_ONLY tool selection."""

from types import SimpleNamespace

import pytest

from hardcover_mcp import server


def _names(env: dict[str, str]) -> set[str]:
    return {spec.tool.name for spec in server.select_tools(server.TOOL_REGISTRY, env)}


ALL = {spec.tool.name for spec in server.TOOL_REGISTRY}
CORE = {spec.tool.name for spec in server.TOOL_REGISTRY if spec.toolset == "core"}


def test_default_enables_everything():
    assert _names({}) == ALL


@pytest.mark.parametrize("value", ["all", "ALL", " all ", "catalog,all"])
def test_all_keyword_enables_everything(value):
    assert _names({"HARDCOVER_TOOLSETS": value}) == ALL


def test_single_toolset_includes_core():
    names = _names({"HARDCOVER_TOOLSETS": "lists"})
    lists = {s.tool.name for s in server.TOOL_REGISTRY if s.toolset == "lists"}
    assert names == lists | CORE
    assert "get_book" not in names


def test_multiple_toolsets_tolerate_spacing_and_case():
    names = _names({"HARDCOVER_TOOLSETS": " Catalog , journal "})
    assert "get_book" in names
    assert "set_journal_entry" in names
    assert "set_list" not in names


def test_unknown_toolset_raises_with_valid_names():
    with pytest.raises(ValueError, match="bogus") as exc:
        server.select_tools(server.TOOL_REGISTRY, {"HARDCOVER_TOOLSETS": "catalog,bogus"})
    assert "catalog" in str(exc.value)


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_read_only_keeps_only_read_tools(value):
    selected = server.select_tools(server.TOOL_REGISTRY, {"HARDCOVER_READ_ONLY": value})
    assert selected
    assert all(spec.tool.annotations.read_only_hint for spec in selected)
    names = {spec.tool.name for spec in selected}
    assert "get_book" in names
    assert "delete_list" not in names
    assert "set_user_book" not in names


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_read_only_off_values(value):
    assert _names({"HARDCOVER_READ_ONLY": value}) == ALL


def test_read_only_combines_with_toolsets():
    names = _names({"HARDCOVER_TOOLSETS": "lists", "HARDCOVER_READ_ONLY": "true"})
    assert "get_list" in names
    assert "set_list" not in names


async def test_configure_hides_disabled_tools(monkeypatch):
    monkeypatch.setattr(server, "_active_tools", server._active_tools)
    monkeypatch.setattr(server, "_dispatch", server._dispatch)
    server.configure({"HARDCOVER_READ_ONLY": "true"})

    listed = await server.list_tools(None, None)
    assert "delete_list" not in {t.name for t in listed.tools}

    result = await server.call_tool(None, SimpleNamespace(name="delete_list", arguments={}))
    assert result.is_error
    assert "disabled" in result.content[0].text
