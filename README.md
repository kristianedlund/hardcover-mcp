# hardcover-mcp

[![PyPI](https://img.shields.io/pypi/v/hardcover-mcp)](https://pypi.org/project/hardcover-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/kristianedlund/hardcover-mcp/blob/main/LICENSE)
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
- **Least-privilege keys** — give the key only the scopes you need; a read-only key makes
  Hardcover itself refuse writes (see [API key and scopes](#api-key-and-scopes))

## Quick Start

1. Install [uv](https://docs.astral.sh/uv/) (a fast Python package runner — the setup takes seconds).
2. Create an API key at [hardcover.app/account/api](https://hardcover.app/account/api); see
   [API key and scopes](#api-key-and-scopes) for links that pre-select the right scopes.
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

### Claude Code

```bash
claude mcp add --scope user hardcover --env HARDCOVER_API_TOKEN=<your token> -- uvx hardcover-mcp
```

Replace `<your token>` with your Hardcover API key. `--scope user` makes the server available
in every project; leave it out to add it to the current project only (see the
[Claude Code MCP documentation](https://code.claude.com/docs/en/mcp) for scopes). Other settings
from [Configuration](#configuration) are extra `--env KEY=value` flags after the server name,
e.g. `--env HARDCOVER_READ_ONLY=true`.

To keep the token off the command line, put the variables in a file and let uvx read it:

```bash
claude mcp add --scope user hardcover -- uvx --env-file /path/to/hardcover.env hardcover-mcp
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

`HARDCOVER_TOOLSETS` and `HARDCOVER_READ_ONLY` are optional and shown with their defaults;
[Configuration](#configuration) lists every setting, including `HARDCOVER_API_URL`.

To keep the token out of the client config, put the variables in a `.env` file and point uvx at
it. The server only reads the file you name:

```json
"command": "uvx",
"args": ["--env-file", "/path/to/hardcover.env", "hardcover-mcp"]
```

## API key and scopes

Hardcover API keys carry **scopes** that limit what the key can do. Create a key with only the
scopes this server needs (the links open Hardcover's key form with them pre-selected):

<!-- scopes:start -->
- **Everything:** [create a key with all scopes](https://hardcover.app/account/api/keys/new?scope=read%3Acatalog%20read%3Agoals%20read%3Ajournal%20read%3Alibrary%20read%3Alists%20read%3Ame%20read%3Aprompts%20read%3Asocial%20read%3Ausers%20read%3Avibes%20write%3Agoals%20write%3Alibrary%20write%3Alists%20write%3Aprompts%20write%3Areviews%20write%3Asocial)
- **Read-only:** [create a read-only key](https://hardcover.app/account/api/keys/new?scope=read%3Acatalog%20read%3Agoals%20read%3Ajournal%20read%3Alibrary%20read%3Alists%20read%3Ame%20read%3Aprompts%20read%3Asocial%20read%3Ausers%20read%3Avibes). Pair it with `HARDCOVER_READ_ONLY=true`; Hardcover then refuses writes even if a tool tried one.

| Toolset | Scopes needed |
|---------|---------------|
| `core` | `read:catalog`, `read:library`, `read:me`, `read:social`, `read:users` |
| `catalog` | `read:catalog`, `read:vibes` |
| `library` | `read:catalog`, `read:goals`, `read:library`, `read:lists`, `read:me`, `write:goals`, `write:library`, `write:reviews` |
| `lists` | `read:lists`, `read:me`, `write:lists` |
| `journal` | `read:journal`, `read:me`, `write:library` |
| `social` | `read:me`, `read:prompts`, `read:social`, `read:users`, `write:prompts`, `write:social` |
<!-- scopes:end -->

`read:me` is needed almost everywhere because tools look up who you are first. `write:reviews`
is only needed to write or edit a review with `set_user_book`; without it, status, rating, and
notes changes still work. If you only load
some toolsets (see [Configuration](#configuration)), the key only needs those rows plus `core`.

- Keys created before August 2026 have full access and keep working.
- When you create a key, Hardcover asks for an expiry date. After it, every tool returns
  "Hardcover rejected the API token … expired" with a link to create a new one.
- If a tool needs a scope your key lacks, its error names the missing scopes and links to a key
  form with them pre-selected.

## Configuration

Optional environment variables, set in the same `env` block as your token:

| Variable | Default | Effect |
|----------|---------|--------|
| `HARDCOVER_TOOLSETS` | `all` | Comma-separated toolsets to load. Fewer tools means less context used and fewer wrong tool picks. |
| `HARDCOVER_READ_ONLY` | `false` | `true` hides every tool that creates, changes, or deletes anything. |
| `HARDCOVER_API_URL` | Hardcover's API | GraphQL endpoint to call instead, e.g. a proxy. Must be `https://`, since every request carries your token. |

| Toolset | What it covers |
|---------|----------------|
| `core` | Always loaded: `search_books`, `get_user` |
| `catalog` | Books (with characters and editions), editions, authors, series, publishers, trending, vibes |
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
| See your profile and reading stats, or look up another user; optionally with library, followers, and following | `get_user` |

### catalog

| What you can do | Tool |
|-----------------|------|
| Look up a book by ID or slug, including contributors and their roles (optionally with characters and editions), or a specific edition by ISBN, ASIN, or edition ID | `get_book` |
| Browse an author's catalogue | `get_author` |
| Explore a series in reading order | `get_series` |
| Look up a publisher and its editions | `get_publisher` |
| See what's trending now | `get_trending_books` |
| Browse curated recommendation collections (vibes) | `get_vibes` |

### library

| What you can do | Tool |
|-----------------|------|
| Browse your library: filter by status, date range, reviewed or owned books; sort by rating/date | `get_user_library` |
| Check your status, rating, review, reads, and list memberships for one book (excluding the internal Owned list) | `get_user_book` |
| Get your active reading goals and progress | `get_reading_goal` |
| ✏️ Add a book or update its status, rating, review, notes, privacy, edition, and ownership | `set_user_book` |
| ✏️ Log or edit reading dates and progress (pages, audiobook time) | `set_user_book_read` |
| ✏️ Create, update, or archive a reading goal (books/pages, date range) | `set_reading_goal` |
| ✏️ Delete a reading goal | `delete_reading_goal` |
| ✏️ Remove a reading entry or a whole book | `delete_user_book_read` / `delete_user_book` |

### lists

| What you can do | Tool |
|-----------------|------|
| View your lists, or one list with its books | `get_list` |
| ✏️ Create or rename a list, or change its privacy | `set_list` |
| ✏️ Add or remove a book on one list (`list_id`) or up to 20 lists (`list_ids`) | `set_list_book` |
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
uv run ruff check .
uv run ruff format --check .
```

Run tests:

```bash
uv run pytest tests/ -v
```

### Integration Tests

Integration tests hit the live Hardcover API and require a valid token. They are **skipped
automatically** in CI and when the token is absent.

To run them locally, create a `.env` file in the repository with your token (the tests load
it; the server itself reads only real environment variables):

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
   uv run ruff check .
   uv run ruff format --check .
   uv run pytest tests/ -v
   ```
4. Keep PRs focused — one change per PR.
5. Use conventional commit prefixes: `feat:`, `fix:`, `chore:`, `docs:`.

## Rate Limiting

The Hardcover API allows 60 requests per minute with a short burst allowance, and a daily
limit (5,000 requests on the free plan). The server queues requests, follows the API's
rate-limit headers, and retries when asked to wait. It waits at most a minute at a time; if
Hardcover asks for longer, the call stops and says how long to wait. Once the daily limit is
used up it stops immediately with a message saying so (it resets at midnight UTC). Your usage is shown at
[hardcover.app/account/api](https://hardcover.app/account/api). Keys created after August
2026 get twice the burst allowance of older keys.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "API token is not set" | Add your token to the config (see Quick Start above) |
| "Hardcover rejected the API token" | The key is invalid or expired; create a new one with the link in the error |
| "missing the scope(s) this tool needs" | Create a key that includes them; the error links to a pre-filled form |
| "daily API limit … is used up" | Wait until midnight UTC, or load fewer tools to make fewer calls |
| "rate limit asks to wait N seconds" | Hardcover is throttling this key; try again after that time |
| "Hardcover didn't answer within 30 seconds" | Try again; if you asked for a change, check whether it was saved first |
| "Access is denied" on Windows | Add `"UV_LINK_MODE": "copy"` to the `env` block in your config |
| Slow or repeated errors | The server retries automatically — wait a moment and try again |
| Unexpected results | Check for a newer version: the Hardcover API may have changed |

## Disclaimer

Unofficial project. Not affiliated with [Hardcover](https://hardcover.app).
