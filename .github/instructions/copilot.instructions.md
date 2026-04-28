---
description: 'Copilot instructions for the hardcover-mcp project'
applyTo: '**'
---

# hardcover-mcp — Copilot Instructions

## Project Overview

hardcover-mcp is a public MCP (Model Context Protocol) server for the
[Hardcover](https://hardcover.app) GraphQL API. It exposes library tracking and list
management as MCP tools that AI assistants (Claude Desktop, VS Code Copilot, etc.) can call.

The project is intentionally small and focused. It is a thin, typed wrapper around
Hardcover's GraphQL API — not a general-purpose library or framework.

## Architecture

```
src/hardcover_mcp/
  server.py        # Entry point, MCP server setup, tool registry
  client.py        # GraphQL client (httpx, rate limiting, retry logic)
  tools/
    user.py        # Authenticated user info + cached user lookup
    books.py       # Book search and detail retrieval
    library.py     # User library: status, ratings, reading log, delete
    lists.py       # List CRUD and list-book management
```

### Key Architectural Rules

- **Tool registry in `server.py`** is the single source of truth for available tools.
  Each tool is a `(Tool, Handler)` tuple in `TOOL_REGISTRY`. Adding a new tool = one
  GraphQL query constant, one handler function, one registry entry. Nothing else.
- **`client.execute()`** is the only way to talk to the Hardcover API. Never create
  `httpx` clients directly in tool modules.
- **Handlers** (`handle_*`) accept `dict[str, Any]` and return `list[TextContent]`.
  They validate input, call `execute()`, format the response, and return JSON.
- **Formatting helpers** (`_format_*`) are pure functions that reshape API responses.
  They live in the same module as their handlers.
- **GraphQL queries** are module-level string constants named `*_QUERY` or `*_MUTATION`.
  User input is always passed via GraphQL variables — never interpolated into query strings.
- Private helpers are prefixed with `_` and must not be exported from `__init__.py`.

## Scope

The server covers library tracking and list management only. Features like social
(followers, feed), recommendations, and edition management are out of scope unless
explicitly discussed.

## Branch Naming

- **Features:** `feature/short-description` (e.g. `feature/ci-workflow`)
- **Bug fixes:** `fix/short-description` (e.g. `fix/rate-limit-edge-case`)
- **Chores/tooling:** `chore/short-description` (e.g. `chore/add-ruff-ci`)
- Use lowercase, hyphens only within the description, slash after prefix
- All work happens on a branch — never commit directly to `main`

## GitHub Issues

- Issue titles are concise and descriptive — no category prefix in the title.
- Categorise with GitHub labels instead: `bug`, `enhancement`, `chore`.
- Title format: one sentence, sentence case, no trailing period.
  - Good: `Rate limiter does not reset after window expires`
  - Good: `Add pagination support to get_user_library`
  - Avoid: `Bug: Rate limiter does not reset` (prefix belongs in the label)
- Reference issues in commit messages and PR descriptions with `#N` (e.g. `closes #3`).

## Commit Messages

- Use conventional-style prefixes: `feat:`, `fix:`, `chore:`, `docs:`.
- Keep the first line under 72 characters.
- Reference issues when applicable: `fix: handle empty search results (closes #5)`.

## Communication Style

- Be direct. Skip filler phrases and unsolicited validation.
- When reviewing code, lead with the problems.
- Do not praise work by default. Only comment on something specific and genuinely
  noteworthy.
