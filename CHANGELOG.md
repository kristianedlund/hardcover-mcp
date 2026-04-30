# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `set_user_book` now accepts `review_raw` (plain text, converted to Slate JSON),
  `review_has_spoilers`, `reviewed_at`, and `private_notes`. All new fields are
  preserved on update when not specified.
- `get_user_book` now returns `review_raw`, `review_has_spoilers`, `reviewed_at`,
  and `private_notes` in its response.
- `get_reading_stats` tool — returns library statistics (total books, books per status,
  average rating, and books read in a given year) via `user_books_aggregate`.
- `add_user_book_read` and `update_user_book_read` now accept `progress_seconds` for
  tracking audiobook listening progress.

## [0.2.0] - 2026-04-29

### Added

- `get_edition` tool — look up a specific edition by Hardcover ID, ISBN-13, or ASIN;
  returns publisher, format, language, and linked book details.
- `search_books` now supports searching across all entity types (authors, series, lists,
  users, publishers, characters, prompts) via an optional `query_type` parameter.
  Defaults to books for backward compatibility.
- `get_author` tool — look up an author by id, slug, or name; returns bio, book counts,
  and books sorted by popularity.
- `get_series` tool — browse a book series by name, look up which series an author
  has written, or find the series a specific book belongs to.
- Integration test suite covering all read tools and account-safe write tools.

### Changed

- README rewritten with reader-friendly language, example prompts, and reorganized
  tool documentation.

## [0.1.2] - 2026-04-28

### Added

- PyPI package metadata: classifiers, project URLs, and keywords.

### Changed

- Updated README with PyPI quick-start instructions now that the package is published.

## [0.1.1] - 2026-04-28

### Added

- GitHub Actions CI workflow (lint + test on every push/PR).
- `pytest` test suite for tool helpers and input validation logic.
- Contributing guidelines in README.
- Copilot instructions for project conventions and Python coding style.
- Inline comments and docstrings throughout the codebase.

### Fixed

- Integer and float tool arguments now produce clear, user-readable error messages
  instead of raw Python exceptions when the value cannot be coerced.

## [0.1.0] - 2026-04-09

Initial release.

### Added

- GraphQL client (`client.py`) with per-minute rate limiting and automatic retry on
  transient errors.
- `get_me` — return the authenticated user's profile.
- `search_books` — full-text book search with pagination.
- `get_book` — fetch detailed metadata for a single book by ID.
- `get_user_library` — list books in a user's library with status filter, pagination,
  and total count.
- `set_user_book` — add a book to the library or update its reading status and rating.
- `add_user_book_read` / `update_user_book_read` / `delete_user_book_read` — manage
  individual reading log entries (start date, finish date, edition).
- `get_my_lists` — list all reading lists owned by the authenticated user.
- `get_list` — fetch the contents of a specific list.
- `create_list` / `update_list` / `delete_list` — full CRUD for reading lists.
- `add_book_to_list` / `remove_book_from_list` — manage books within a list.
- Ruff linter configuration, `.env.example`, and initial README.

[Unreleased]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/kristianedlund/hardcover-mcp/releases/tag/v0.1.0
