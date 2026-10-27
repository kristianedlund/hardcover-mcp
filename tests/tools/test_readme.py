"""Keep README.md in sync with the tool registry (tool tables and the API key scopes section)."""

import re
from pathlib import Path

from hardcover_mcp import server
from hardcover_mcp.client import new_key_link
from hardcover_mcp.tools._registry import TOOLSETS, scopes_for

README = Path(__file__).resolve().parents[2] / "README.md"
SCOPES_START = "<!-- scopes:start -->"
SCOPES_END = "<!-- scopes:end -->"


def render_scopes_section() -> str:
    """The README block between the scopes markers, generated from the registry."""
    registry = server.TOOL_REGISTRY
    read_only = [s for s in registry if s.tool.annotations.read_only_hint]
    lines = [
        f"- **Everything:** [create a key with all scopes]({new_key_link(scopes_for(registry))})",
        "- **Read-only:** [create a read-only key]"
        f"({new_key_link(scopes_for(read_only))}). Pair it with `HARDCOVER_READ_ONLY=true`; "
        "Hardcover then refuses writes even if a tool tried one.",
        "",
        "| Toolset | Scopes needed |",
        "|---------|---------------|",
    ]
    for toolset in TOOLSETS:
        specs = [s for s in registry if s.toolset == toolset]
        scopes = ", ".join(f"`{scope}`" for scope in scopes_for(specs))
        lines.append(f"| `{toolset}` | {scopes} |")
    return "\n".join(lines)


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def test_scopes_section_matches_registry():
    text = _readme()
    start = text.index(SCOPES_START) + len(SCOPES_START)
    end = text.index(SCOPES_END)
    expected = render_scopes_section()
    assert text[start:end].strip() == expected, (
        f"README scopes section is out of date; replace it with:\n\n{expected}\n"
    )


def test_tool_tables_list_every_tool_and_mark_writes():
    text = _readme()
    tables = text[text.index("## Tools") : text.index("## Development")]
    listed: set[str] = set()
    marked: set[str] = set()
    groups: dict[str, str] = {}
    toolset = ""
    for line in tables.splitlines():
        if line.startswith("### "):
            toolset = line.removeprefix("### ").split()[0]
            continue
        if line.count("|") < 3:
            continue
        names = set(re.findall(r"`([a-z_]+)`", line.split("|")[-2]))
        listed |= names
        for name in names:
            assert name not in groups, f"Tool {name} is listed more than once"
            groups[name] = toolset
        if "✏️" in line:
            marked |= names

    registry = {s.tool.name for s in server.TOOL_REGISTRY}
    writes = {s.tool.name for s in server.TOOL_REGISTRY if not s.tool.annotations.read_only_hint}
    assert listed == registry
    assert marked == writes
    assert groups == {s.tool.name: s.toolset for s in server.TOOL_REGISTRY}


def test_configuration_table_lists_every_toolset():
    text = _readme()
    table = text.split("| Toolset | What it covers |", 1)[1].split("\n\n", 1)[0]
    listed = re.findall(r"^\| `([a-z_]+)` \|", table, re.MULTILINE)
    assert len(listed) == len(set(listed)), "Toolset table contains duplicate rows"
    assert set(listed) == set(TOOLSETS)


SRC = README.parents[0] / "src" / "hardcover_mcp"
ENV_EXAMPLE = README.parents[0] / ".env.example"


def _env_vars_read_by_the_code() -> set[str]:
    pattern = re.compile(r"""(?:environ|env)\.get\(\s*["'](HARDCOVER_[A-Z_]+)["']""")
    return {m for path in SRC.rglob("*.py") for m in pattern.findall(path.read_text("utf-8"))}


def test_every_setting_the_code_reads_is_documented():
    settings = _env_vars_read_by_the_code()
    assert "HARDCOVER_API_TOKEN" in settings  # sanity check that the scan finds them

    text = _readme()
    table = text.split("| Variable | Default | Effect |", 1)[1].split("\n\n", 1)[0]
    rows = set(re.findall(r"^\| `(HARDCOVER_[A-Z_]+)` \|", table, re.MULTILINE))
    # The token is covered by the setup sections; every other setting needs a table row.
    assert rows == settings - {"HARDCOVER_API_TOKEN"}

    example = ENV_EXAMPLE.read_text(encoding="utf-8")
    missing = {name for name in settings if f"{name}=" not in example}
    assert not missing, f".env.example doesn't mention {sorted(missing)}"
