# hardcover-mcp

MCP server for the [Hardcover](https://hardcover.app) GraphQL API — personal library tracking and list management.

## Quick Start

1. Install [uv](https://docs.astral.sh/uv/) if you don't have it.
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

### Read

| Tool | Description |
|------|-------------|
| `me` | Get authenticated user info (id, username, name, books count) |
| `search_books` | Search for books by title, author, or ISBN |
| `get_book` | Get book details by Hardcover ID or slug |
| `get_user_library` | Get books from your library, optionally filtered by status |
| `get_user_book` | Get your library entry for a specific book (status, rating, reading dates) |
| `get_my_lists` | Get all of your Hardcover lists |
| `get_list` | Get a specific list with its books |
| `get_series` | Get a book series by id, slug, or name with books in reading order |

### Write

| Tool | Description |
|------|-------------|
| `set_user_book` | Add a book to your library or update its status/rating (merge-safe) |
| `add_user_book_read` | Add or update a reading date entry (updates active reads instead of duplicating) |
| `update_user_book_read` | Update an existing reading date entry (merge-safe) |
| `delete_user_book_read` | Delete a reading date entry |
| `delete_user_book` | Remove a book from your library |
| `create_list` | Create a new list |
| `update_list` | Update a list's name, description, or privacy |
| `delete_list` | Delete a list |
| `add_book_to_list` | Add a book to a list |
| `remove_book_from_list` | Remove a book from a list |

## Scope

This server focuses on library tracking and list management. Features like social (followers, feed), recommendations, and edition management are not currently supported.

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

The Hardcover API allows 60 requests per minute with a max query depth of 3. The client includes a sliding-window rate limiter and automatic retry with exponential backoff on 429 responses.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `HARDCOVER_API_TOKEN is not set` | Create a `.env` file in the project root or set the env var directly |
| `Access is denied` on Windows | Add `"UV_LINK_MODE": "copy"` to the `env` block in your MCP client config |
| `Rate limited` / 429 errors | The client retries automatically up to 3 times. If persistent, reduce concurrent tool calls |
| `GraphQL error: field not found` | The Hardcover API may have changed. Check for updates to this server |
