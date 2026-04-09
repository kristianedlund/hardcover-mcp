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

| Tool | Description |
|------|-------------|
| `me` | Get authenticated user info (id, username, name, books count) |
| `search_books` | Search for books by title, author, or ISBN |
| `get_book` | Get book details by Hardcover ID or slug |
