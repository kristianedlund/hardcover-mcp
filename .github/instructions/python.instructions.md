---
description: 'Python coding conventions for hardcover-mcp'
applyTo: '**/*.py'
---

# Python Coding Conventions

## General Instructions

- **Readability first.** Write code that is easy to read and reason about.
  Clever one-liners are acceptable only when they do not obscure intent.
- **State intent in comments.** For non-trivial logic — especially GraphQL query
  construction, mutation side-effects, and caching — add a comment explaining *why*,
  not just *what*.
- **Fail loud, fail early.** Validate inputs at function boundaries. Never silently
  swallow bad data or fall back to a default that hides a bug.
- **Keep functions focused.** A function should do one thing. If a function needs a
  multi-step comment header (`# --- 1. ...`, `# --- 2. ...`), consider whether any step
  deserves its own function.
- **Async by default.** All I/O-bound functions (API calls, network) must be `async`.
  Keep sync helpers for pure data formatting.

## Type Hints

- Use union syntax: `X | Y` and `X | None` (Python 3.10+, PEP 604), not `Optional[X]`
  or `Union[X, Y]`.
- Annotate all function signatures with parameter and return types.
- Use `list[int]` / `dict[str, float]` (lowercase built-ins, Python 3.9+, PEP 585),
  not `List` / `Dict` from `typing`.
- Do **not** use `from __future__ import annotations`. The project targets Python 3.14;
  the import is a no-op and adds noise.

## Docstrings

- Follow **NumPy docstring style** for all public functions and classes.
- Private helpers (prefixed `_`) require at minimum a one-line summary docstring.
- Always document: what the input data shape/convention is, and what the output represents.

```python
async def handle_search_books(arguments: dict[str, Any]) -> list[TextContent]:
    """
    Search Hardcover for books matching a query string.

    Parameters
    ----------
    arguments : dict[str, Any]
        Tool arguments. Required key: ``query`` (str).
        Optional: ``per_page`` (int, default 10, max 25), ``page`` (int, default 1).

    Returns
    -------
    list[TextContent]
        Single-element list with JSON-formatted search results.
    """
```

- Include a `Raises` section whenever a function explicitly raises an exception.
  Document the exception type and the condition that triggers it.

## Code Style

- Follow **PEP 8**. Maximum line length: **99 characters** (matching `ruff` config).
- 4-space indentation. No tabs.
- Use blank lines between logical sections within a function with an inline comment
  explaining the step (e.g. `# --- 1. Validate input`, `# --- 2. Execute query`).

## Imports

- Group imports in this order, with a **blank line between each group**:
  1. Standard library (`os`, `json`, `asyncio`, etc.)
  2. Third-party packages (`httpx`, `mcp`, `dotenv`, etc.)
  3. Internal `hardcover_mcp.*` imports
- Within each group, sort imports **alphabetically**.
- Never mix groups on the same line or omit the blank-line separator.

```python
import json
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
```

## Naming Conventions

**PEP 8 standard:**
- Functions and variables: `snake_case`.
- Classes: `PascalCase`.
- Constants: `UPPER_CASE` (e.g. `_RATE_LIMIT = 60`).
- Private/internal helpers: single leading underscore `_name` (e.g. `_format_search_hit`).

**Project conventions** (consistent in this codebase):
- Tool handlers: `handle_<tool_name>` — each corresponds to one MCP tool.
- Formatting helpers: `_format_<entity>` — pure functions that reshape API data.
- GraphQL query constants: `UPPER_CASE` ending in `_QUERY` or `_MUTATION`.
- Status/privacy maps: `dict` constants named `<CONCEPT>_MAP` (e.g. `STATUS_MAP`,
  `PRIVACY_MAP`).

## Error Handling — "Fail Loud"

- Raise explicit exceptions for violated data contracts. Never silently swallow bad input.
- Prefer `TypeError` for wrong types, `ValueError` for illegal values.
- Return `TextContent` error messages for user-facing input validation in tool handlers
  (e.g. missing required arguments). Reserve exceptions for programming errors and
  unexpected API failures.
- Do NOT use bare `except:` or `except Exception:` without re-raising or logging.

## MCP Tool Pattern

Each tool consists of three parts — follow this pattern when adding new tools:

1. **GraphQL query/mutation constant** in the tool module (e.g. `books.py`, `lists.py`).
2. **Handler function** (`handle_<tool_name>`) in the same module. Accepts
   `dict[str, Any]` arguments, returns `list[TextContent]`.
3. **Registry entry** in `server.py`: a `(Tool, Handler)` tuple in `TOOL_REGISTRY`
   with the JSON Schema for the tool's inputs.

Adding a new tool = one query constant, one handler, one registry entry. Nothing else.

### Handler conventions

- Validate required arguments early; return a `TextContent` error if missing.
- Call `execute()` for all API communication — never create `httpx` clients directly.
- Format response data through a `_format_*` helper when the raw API shape is noisy.
- Return results as `json.dumps(..., indent=2)` wrapped in `TextContent`.

## GraphQL Conventions

- Store queries as module-level `str` constants (triple-quoted, named `*_QUERY` or
  `*_MUTATION`).
- Use GraphQL variables (`$name: Type!`) for all dynamic values — never interpolate
  user input into query strings.
- Keep queries minimal: request only the fields the tool actually uses.

## Public API and `__init__.py`

- Each module's `__init__.py` defines its public surface. Only export what external
  callers should use.
- Private helpers (prefixed `_`) must not be exported from `__init__.py`.
- When adding a new public function, explicitly add it to the relevant `__init__.py`.


