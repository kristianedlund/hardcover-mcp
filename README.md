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
- **Read-only mode** — set `HARDCOVER_READ_ONLY=true` to hide every tool that can change your
  account (see [Configuration](#configuration))

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
        "HARDCOVER_API_TOKEN": "<your token>",
        "HARDCOVER_TOOLSETS": "all",
        "HARDCOVER_READ_ONLY": "false"
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
        "HARDCOVER_API_TOKEN": "<your token>",
        "HARDCOVER_TOOLSETS": "all",
        "HARDCOVER_READ_ONLY": "false"
      }
    }
  }
}
```

`HARDCOVER_TOOLSETS` and `HARDCOVER_READ_ONLY` are optional and shown with their defaults; see
[Configuration](#configuration).

## Configuration

Optional environment variables, set in the same `env` block as your token:

| Variable | Default | Effect |
|----------|---------|--------|
| `HARDCOVER_TOOLSETS` | `all` | Comma-separated toolsets to load. Fewer tools means less context used and fewer wrong tool picks. |
| `HARDCOVER_READ_ONLY` | `false` | `true` hides every tool that creates, changes, or deletes anything. |

| Toolset | What it covers |
|---------|----------------|
| `core` | Always loaded: `search_books`, `get_user` |
| `catalog` | Books (with characters), editions, authors, series, publishers, trending, vibes |
| `library` | Your library, reading dates and progress, ownership, reviews, stats, goals |
| `lists` | Viewing and managing your lists |
| `journal` | Reading journal notes and quotes |
| `social` | Activity feed, following users, community prompts |

For example, a read-only assistant for browsing books and your own library:

```json
"env": {
  "HARDCOVER_API_TOKEN": "<your token>",
  "HARDCOVER_TOOLSETS": "catalog,library",
  "HARDCOVER_READ_ONLY": "true"
}
```

An unknown toolset name stops the server at startup with a message listing the valid names.

## Tools

Grouped by toolset (see [Configuration](#configuration)). Tools marked ✏️ can change your
account and are hidden in read-only mode.

### core (always loaded)

| What you can do | Tool |
|-----------------|------|
| Search for books, authors, series, lists, users, and more (with sort/filter) | `search_books` |
| See your own profile, or look up another user (optionally with their library) | `get_user` |

### catalog

| What you can do | Tool |
|-----------------|------|
| Look up a book by ID or slug, optionally with its characters | `get_book` |
| Look up a specific edition by ISBN or ASIN | `get_edition` |
| Browse an author's catalogue | `get_author` |
| Explore a series in reading order | `get_series` |
| Look up a publisher and its editions | `get_publisher` |
| See what's trending now | `get_trending_books` |
| Browse curated recommendation collections (vibes) | `get_vibes` |

### library

| What you can do | Tool |
|-----------------|------|
| Browse your library: filter by status, date range, or reviewed books; sort by rating/date | `get_user_library` |
| Check your status, rating, review, and reads for one book | `get_user_book` |
| List books you own, with edition details | `get_owned_books` |
| Get reading statistics (totals, ratings, books read per year) | `get_reading_stats` |
| Get your active reading goals and progress | `get_reading_goal` |
| ✏️ Add a book or update its status, rating, review, notes, privacy, and edition | `set_user_book` |
| ✏️ Mark an edition as owned or not owned | `set_edition_owned` |
| ✏️ Log or edit reading dates and progress (pages, audiobook time) | `set_user_book_read` |
| ✏️ Create or update a reading goal (books/pages, date range) | `set_reading_goal` |
| ✏️ Remove a reading entry or a whole book | `delete_user_book_read` / `delete_user_book` |

### lists

| What you can do | Tool |
|-----------------|------|
| View your lists, or one list with its books | `get_list` |
| ✏️ Create or rename a list, or change its privacy | `set_list` |
| ✏️ Add or remove a book on a list | `set_list_book` |
| ✏️ Delete a list | `delete_list` |

### journal

| What you can do | Tool |
|-----------------|------|
| Read your journal entries (notes, quotes, status events) | `get_reading_journal` |
| ✏️ Add or edit a journal note/quote | `set_journal_entry` |
| ✏️ Delete a journal entry | `delete_journal_entry` |

### social

| What you can do | Tool |
|-----------------|------|
| See recent activity from people you follow (or one user) | `get_activity_feed` |
| ✏️ Follow or unfollow a user | `set_following` |
| Browse community book prompts | `get_prompts` |
| ✏️ Answer a prompt with a book, or withdraw the answer | `set_prompt_answer` |

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
