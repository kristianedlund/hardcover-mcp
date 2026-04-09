# hardcover-mcp

MCP server for the [Hardcover](https://hardcover.app) GraphQL API — personal library tracking and list management.

## Requirements

- Python 3.13+
- A Hardcover API token from [hardcover.app/account/api](https://hardcover.app/account/api)

## Usage

Create a `.env` file with your token:

```
HARDCOVER_API_TOKEN=<your token>
```

Then run:

```bash
uv run python -m hardcover_mcp.server
```

### MCP client config (Claude Desktop / VS Code)

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
| `get_my_lists` | Get all of your Hardcover lists |
| `get_list` | Get a specific list with its books |

### Write

| Tool | Description |
|------|-------------|
| `set_user_book` | Add a book to your library or update its status/rating |
| `add_user_book_read` | Add a reading date entry (started/finished) to a book |
| `update_user_book_read` | Update an existing reading date entry |
| `create_list` | Create a new list |
| `update_list` | Update a list's name, description, or privacy |
| `delete_list` | Delete a list |
| `add_book_to_list` | Add a book to a list |
| `remove_book_from_list` | Remove a book from a list |
