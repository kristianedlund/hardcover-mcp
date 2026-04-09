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
uv run hardcover-mcp
```

### MCP client config (Claude Desktop / VS Code)

```json
{
  "mcpServers": {
    "hardcover": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/hardcover-mcp", "hardcover-mcp"],
      "env": {
        "HARDCOVER_API_TOKEN": "<your token>"
      }
    }
  }
}
```
