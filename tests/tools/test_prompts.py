"""Unit tests for tools/prompts.py — formatting helpers."""

from hardcover_mcp.tools.prompts import _format_prompt


class TestFormatPrompt:
    def test_formats_full_prompt(self):
        raw = {
            "id": 1,
            "slug": "best-sci-fi-2025",
            "question": "Best sci-fi of 2025?",
            "description": "Share your favourite sci-fi reads from 2025.",
            "featured": True,
            "answers_count": 42,
            "books_count": 15,
        }
        result = _format_prompt(raw)

        assert result["id"] == 1
        assert result["slug"] == "best-sci-fi-2025"
        assert result["question"] == "Best sci-fi of 2025?"
        assert result["description"] == "Share your favourite sci-fi reads from 2025."
        assert result["featured"] is True
        assert result["answers_count"] == 42
        assert result["books_count"] == 15

    def test_defaults_featured_to_false(self):
        raw = {
            "id": 2,
            "slug": "cozy-reads",
            "question": "Favourite cozy reads?",
            "answers_count": 10,
            "books_count": 5,
        }
        result = _format_prompt(raw)

        assert result["featured"] is False

    def test_defaults_counts_to_zero(self):
        raw = {
            "id": 3,
            "slug": "new-prompt",
            "question": "New prompt?",
        }
        result = _format_prompt(raw)

        assert result["answers_count"] == 0
        assert result["books_count"] == 0

    def test_description_can_be_none(self):
        raw = {
            "id": 4,
            "slug": "no-desc",
            "question": "No description prompt?",
            "description": None,
            "answers_count": 0,
            "books_count": 0,
        }
        result = _format_prompt(raw)

        assert result["description"] is None
