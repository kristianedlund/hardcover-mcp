# hardcover-mcp

MCP server for the [Hardcover](https://hardcover.app) GraphQL API — personal library tracking and list management.

## Requirements

- Python 3.13+
- A Hardcover API token from [hardcover.app/account/api](https://hardcover.app/account/api)

## Installation

```bash
git clone <repo-url>
cd hardcover-mcp
```

## Usage

Create a `.env` file with your token:

```
HARDCOVER_API_TOKEN=<your token>
```

Then run:

```bash
uv run python -m hardcover_mcp.server
```

`uv run` automatically installs dependencies on first use.

### MCP client config

**VS Code** (`.vscode/mcp.json`):

```json
{
  "servers": {
    "hardcover": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/hardcover-mcp", "python", "-m", "hardcover_mcp.server"]
    }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "hardcover": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/hardcover-mcp", "python", "-m", "hardcover_mcp.server"]
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

## Rate Limiting

The Hardcover API allows 60 requests per minute with a max query depth of 3. The client includes a sliding-window rate limiter and automatic retry with exponential backoff on 429 responses.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `HARDCOVER_API_TOKEN is not set` | Create a `.env` file in the project root or set the env var directly |
| `Access is denied` on Windows | Use `python -m hardcover_mcp.server` instead of the script entry point (OneDrive .exe sync issue) |
| `Rate limited` / 429 errors | The client retries automatically up to 3 times. If persistent, reduce concurrent tool calls |
| `GraphQL error: field not found` | The Hardcover API may have changed. Check for updates to this server |
