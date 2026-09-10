"""Unit tests for tools.discovery (query rendering + validation)."""

from hardcover_mcp.tools.discovery import (
    _TRENDING_DURATIONS,
    _render_vibes_query,
    handle_get_trending_books,
    handle_get_vibes,
)


class TestRenderVibesQuery:
    def test_featured_only_adds_where(self):
        assert "featured: {_eq: true}" in _render_vibes_query(True)

    def test_all_vibes_omits_where(self):
        assert "featured: {_eq: true}" not in _render_vibes_query(False)


class TestTrendingValidation:
    async def test_rejects_bad_duration(self):
        result = await handle_get_trending_books({"duration": "fortnight"})
        assert "invalid duration" in result[0].text

    async def test_duration_set_matches_schema_enum(self):
        assert {"all", "week", "month", "three_month", "one_year"} == _TRENDING_DURATIONS

    async def test_rejects_non_int_limit(self):
        result = await handle_get_trending_books({"limit": "lots"})
        assert "Error" in result[0].text


class TestVibesValidation:
    async def test_rejects_non_int_books_per_vibe(self):
        result = await handle_get_vibes({"books_per_vibe": "many"})
        assert "Error" in result[0].text
