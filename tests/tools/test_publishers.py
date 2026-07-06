"""Unit tests for tools.publishers."""

import json
from unittest.mock import AsyncMock, patch

from hardcover_mcp.tools.publishers import _format_publisher, handle_get_publisher


class TestFormatPublisher:
    def test_formats_full_publisher(self):
        raw = {
            "id": 185,
            "name": "Tor Books",
            "slug": "tor-books",
            "editions_count": 2914,
            "state": "active",
            "parent_publisher": {"name": "Macmillan Publishers", "slug": "macmillan-publishers"},
            "editions": [
                {
                    "id": 5195452,
                    "title": "Mistborn: The Final Empire",
                    "isbn_13": "9780765311788",
                    "edition_format": "hardcover",
                    "book": {
                        "id": 369692,
                        "title": "Mistborn: The Final Empire",
                        "slug": "mistborn",
                        "rating": 4.46,
                        "release_year": 2006,
                    },
                },
            ],
        }

        result = _format_publisher(raw)

        assert result["id"] == 185
        assert result["name"] == "Tor Books"
        assert result["slug"] == "tor-books"
        assert result["editions_count"] == 2914
        assert result["state"] == "active"
        assert result["parent_publisher"]["name"] == "Macmillan Publishers"
        assert len(result["editions"]) == 1
        assert result["editions"][0]["edition_id"] == 5195452
        assert result["editions"][0]["book_title"] == "Mistborn: The Final Empire"
        assert result["editions"][0]["isbn_13"] == "9780765311788"

    def test_handles_missing_parent(self):
        raw = {
            "id": 1,
            "name": "Independent Press",
            "slug": "independent-press",
            "editions_count": 0,
            "state": "active",
            "parent_publisher": None,
            "editions": [],
        }

        result = _format_publisher(raw)

        assert result["parent_publisher"] is None
        assert result["editions"] == []

    def test_handles_missing_fields_gracefully(self):
        result = _format_publisher({})

        assert result["id"] is None
        assert result["name"] is None
        assert result["slug"] is None
        assert result["editions"] == []


class TestHandleGetPublisher:
    async def test_returns_error_on_missing_args(self):
        result = await handle_get_publisher({})

        assert "Error" in result[0].text

    async def test_returns_error_on_non_numeric_id(self):
        result = await handle_get_publisher({"id": "not-a-number"})

        assert "must be an integer" in result[0].text

    @patch("hardcover_mcp.tools.publishers.execute", new_callable=AsyncMock)
    async def test_returns_not_found(self, mock_execute):
        mock_execute.return_value = {"data": {"publishers": []}}

        result = await handle_get_publisher({"id": 99999})

        assert "No publisher found" in result[0].text

    @patch("hardcover_mcp.tools.publishers.execute", new_callable=AsyncMock)
    async def test_returns_publisher_by_id(self, mock_execute):
        mock_execute.return_value = {
            "data": {
                "publishers": [
                    {
                        "id": 185,
                        "name": "Tor Books",
                        "slug": "tor-books",
                        "editions_count": 2914,
                        "state": "active",
                        "parent_publisher": None,
                        "editions": [],
                    }
                ]
            }
        }

        result = await handle_get_publisher({"id": 185})
        data = json.loads(result[0].text)

        assert data["id"] == 185
        assert data["name"] == "Tor Books"

    @patch("hardcover_mcp.tools.publishers.execute", new_callable=AsyncMock)
    async def test_name_search_fallback(self, mock_execute):
        mock_execute.side_effect = [
            {"data": {"search": {"results": {"hits": [{"document": {"id": 185}}]}}}},
            {
                "data": {
                    "publishers": [
                        {
                            "id": 185,
                            "name": "Tor Books",
                            "slug": "tor-books",
                            "editions_count": 2914,
                            "state": "active",
                            "parent_publisher": None,
                            "editions": [],
                        }
                    ]
                }
            },
        ]

        result = await handle_get_publisher({"name": "Tor Books"})
        data = json.loads(result[0].text)

        assert data["id"] == 185
        assert data["name"] == "Tor Books"
        # Verify search was called first
        search_call = mock_execute.call_args_list[0]
        assert "Publisher" in str(search_call)

    @patch("hardcover_mcp.tools.publishers.execute", new_callable=AsyncMock)
    async def test_name_search_no_hits(self, mock_execute):
        mock_execute.return_value = {"data": {"search": {"results": {"hits": []}}}}

        result = await handle_get_publisher({"name": "Nonexistent Publisher"})

        assert "No publisher found" in result[0].text

    @patch("hardcover_mcp.tools.publishers.execute", new_callable=AsyncMock)
    async def test_passes_editions_limit_and_offset(self, mock_execute):
        mock_execute.return_value = {
            "data": {
                "publishers": [
                    {
                        "id": 185,
                        "name": "Tor",
                        "slug": "tor",
                        "editions_count": 100,
                        "state": "active",
                        "parent_publisher": None,
                        "editions": [],
                    }
                ]
            }
        }

        await handle_get_publisher({"id": 185, "editions_limit": 50, "editions_offset": 10})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["editions_limit"] == 50
        assert call_vars["editions_offset"] == 10

    @patch("hardcover_mcp.tools.publishers.execute", new_callable=AsyncMock)
    async def test_caps_editions_limit_at_100(self, mock_execute):
        mock_execute.return_value = {
            "data": {
                "publishers": [
                    {
                        "id": 1,
                        "name": "P",
                        "slug": "p",
                        "editions_count": 0,
                        "state": "active",
                        "parent_publisher": None,
                        "editions": [],
                    }
                ]
            }
        }

        await handle_get_publisher({"id": 1, "editions_limit": 999})

        call_vars = mock_execute.call_args[0][1]
        assert call_vars["editions_limit"] == 100
