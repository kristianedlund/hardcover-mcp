# hardcover-mcp

[![PyPI](https://img.shields.io/pypi/v/hardcover-mcp)](https://pypi.org/project/hardcover-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/)

**Talk to your [Hardcover](https://hardcover.app) library from any AI assistant.**

hardcover-mcp connects your [Hardcover](https://hardcover.app) library to AI assistants like Claude and Copilot. Search for books, update your reading status, manage lists, explore series — all through natural conversation instead of clicking through menus.

### What you can say

> *"What's on my currently reading list?"*
>
> *"Add Project Hail Mary to my library as currently reading"*
>
> *"Search for books by Brandon Sanderson"*
>
> *"Look up ISBN 9780547928227"*
>
> *"Create a list called 'Summer Reading' and add The Hobbit to it"*
>
> *"Show me the Stormlight Archive series in reading order"*
>
> *"Move Project Hail Mary and The Martian to currently reading"*
>
> *"What books has Andy Weir written? Add any I haven't read to my want-to-read list"*
>
> *"Compare my rating of Dune with the Hardcover average"*

## What's covered

- **Library tracking** — status, ratings, reading dates
- **List management** — create, edit, add/remove books
- **Discovery** — search books, authors, series, editions, and more
- **Account info** — your profile and reading stats

## Safety & control

- **You control your API key** — it stays on your machine, never shared with third parties
- **Runs locally** through your MCP client — no external server involved
- **Actions only happen when explicitly requested** — nothing runs in the background
- **You review prompts and outputs** in your client before anything is sent

## Quick Start

1. Install [uv](https://docs.astral.sh/uv/) (a fast Python package runner — the setup takes seconds).
2. Get an API token from [hardcover.app/account/api](https://hardcover.app/account/api).
3. Add the config below to your MCP client — no manual install needed, `uvx` handles it.

### VS Code

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "hardcover": {
      "command": "uvx",
      "args": ["hardcover-mcp"],
      "env": {
        "HARDCOVER_API_TOKEN": "<your token>"
      }
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hardcover": {
      "command": "uvx",
      "args": ["hardcover-mcp"],
      "env": {
        "HARDCOVER_API_TOKEN": "<your token>"
      }
    }
  }
}
```

## Tools

### Browse & discover

| What you can do | Tool |
|-----------------|------|
| Search for books, authors, series, and more | `search_books` |
| Look up a book by title or ID | `get_book` |
| Look up a specific edition by ISBN or ASIN | `get_edition` |
| Explore a series in reading order | `get_series` |
| Browse an author's catalogue | `get_author` |

### Your library

| What you can do | Tool |
|-----------------|------|
| See your profile and book count | `me` |
| Get reading statistics (totals, ratings, books read per year) | `get_reading_stats` |
| Browse your library, filter by reading status | `get_user_library` |
| Check your status/rating for a specific book (includes privacy setting) | `get_user_book` |
| List your reviews | `get_user_reviews` |
| Add a book or update its status, rating, review, notes, privacy, and edition | `set_user_book` |
| Log reading dates and progress (pages, audiobook time) | `add_user_book_read` / `update_user_book_read` |
| Remove a book or reading entry | `delete_user_book` / `delete_user_book_read` |

### Lists

| What you can do | Tool |
|-----------------|------|
| View all your lists | `get_my_lists` |
| View a specific list with its books | `get_list` |
| Create, rename, or delete a list | `create_list` / `update_list` / `delete_list` |
| Add or remove books from a list | `add_book_to_list` / `remove_book_from_list` |

## Development

```bash
git clone https://github.com/kristianedlund/hardcover-mcp.git
cd hardcover-mcp
uv sync
```

Lint and format checks (using [Ruff](https://docs.astral.sh/ruff/)):

```bash
uv run ruff check src/
uv run ruff format --check src/
```

Run tests:

```bash
uv run pytest tests/ -v
```

### Integration Tests

Integration tests hit the live Hardcover API and require a valid token. They are **skipped
automatically** in CI and when the token is absent.

To run them locally, create a `.env` file with your token:

```
HARDCOVER_API_TOKEN=your_token_here
```

Then run:

```bash
uv run pytest tests/integration/ -v
```

Write tests follow a create → verify → delete lifecycle so the account is left unchanged.

## Contributing

Contributions are welcome! Please:

1. Open an issue first to discuss the change.
2. Fork the repo and create a branch (`feature/short-description` or `fix/short-description`).
3. Run lint and tests before submitting:
   ```bash
   uv run ruff check src/
   uv run ruff format --check src/
   uv run pytest tests/ -v
   ```
4. Keep PRs focused — one change per PR.
5. Use conventional commit prefixes: `feat:`, `fix:`, `chore:`, `docs:`.

## Rate Limiting

The Hardcover API allows 60 requests per minute. The server handles this automatically — it queues requests and retries if needed. You shouldn't hit this in normal use.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "API token is not set" | Add your token to the config (see Quick Start above) |
| "Access is denied" on Windows | Add `"UV_LINK_MODE": "copy"` to the `env` block in your config |
| Slow or repeated errors | The server retries automatically — wait a moment and try again |
| Unexpected results | Check for a newer version: the Hardcover API may have changed |

## Disclaimer

Unofficial project. Not affiliated with [Hardcover](https://hardcover.app).
