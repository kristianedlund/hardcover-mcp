# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Editing a journal entry with `set_journal_entry(id=...)` failed with the newer, scoped API keys
  ("variable 'id' is declared as 'Int!', but used where 'bigint' is expected"). The lookup now
  uses the `bigint` type the API schema specifies; legacy keys had tolerated the mismatch.
- With a scoped API key, `set_user_book` failed on every update of a book already in your
  library unless the key had `write:reviews`, because it re-sent the existing review fields.
  It now sends review fields only when you change them, so status, rating, and notes updates
  work without that scope (the API keeps the review as it is).

### Added

- README section **API key and scopes**: the Hardcover API scopes each toolset needs, with links
  that open Hardcover's new-key form with the right scopes pre-selected (one for everything, one
  read-only). Each tool now declares its scopes in code; the README section is generated from
  them and a test keeps it in sync.

### Changed

- Clear errors for API failures instead of raw HTTP errors and tracebacks:
  - an invalid or expired token explains that and links to create a new key;
  - a key missing a scope names the missing scopes and links to a key form with them selected;
  - requests over the burst limit, operations not allowed for API tokens, and other refusals
    each get a specific message.
- Rate limiting follows the API's `RateLimit` and `Retry-After` headers. When the daily limit is
  used up, calls stop immediately with a message instead of retrying. 503 responses are retried
  like 429s.
- The User-Agent now reports the installed version (it was stuck at `0.7.1`) and links to the
  project.

## [0.8.0] - 2026-10-19

### Breaking: tools merged and renamed (39 → 31)

Related tools were merged so each tool covers one task and keeps a single, accurate behavior
annotation. The old names are gone (no aliases). If you reference tools by name, for example in
Claude Code permission rules such as `mcp__hardcover__follow_user`, update them:

| Removed | Use instead |
|---------|-------------|
| `me` | `get_user` with no arguments |
| `follow_user` / `unfollow_user` | `set_following` with `following: true` / `false` |
| `get_my_lists` | `get_list` without `id` |
| `create_list` / `update_list` | `set_list` without / with `id` |
| `add_book_to_list` / `remove_book_from_list` | `set_list_book` with `on_list: true` / `false` |
| `add_user_book_read` / `update_user_book_read` | `set_user_book_read` without / with `id` |
| `get_characters` | `get_book` with `include_characters: true` |
| `get_user_reviews` | `get_user_library` with `has_review: true` (results under `books`) |
| `add_journal_entry` | `set_journal_entry` without `id` |
| `answer_prompt` | `set_prompt_answer` with `answered: true` |

Behavior changes in the merged tools:

- `set_following`, `set_list_book`, and `set_prompt_answer` check the current state first, so
  repeating a call is a no-op and returns `changed: false`. Previously a repeated follow, list
  add, or prompt answer went straight to the API.
- `set_journal_entry` with an `id` edits one of your existing notes or quotes, changing only
  the fields you pass. Status, rating, and progress entries can't be edited.
- `set_prompt_answer` with `answered: false` withdraws your answer, which wasn't possible
  before. It also accepts an optional `description` of why the book fits. Hardcover takes a few
  seconds to show prompt-answer changes, so a call repeated immediately may not see the previous
  one.
- `set_list_book` identifies the entry by `list_id` + `book_id`; the list-entry `id` parameter of
  `remove_book_from_list` is gone.
- `get_user` with no arguments returns your full profile (bio, follower counts, privacy), not
  just the id/username/name/books_count that `me` returned.
- `get_book(include_characters=true)` returns an empty `characters` array when a book has none,
  instead of `get_characters`' "No characters found" message. Characters come back in book
  order with `biography` (previously requested as `description`, which doesn't exist) plus
  `spoiler` and `only_mentioned` flags.
- `get_user_library(has_review=true)` rows include `status` and `updated_at` in addition to the
  review fields, and can be combined with `status` and `sort` (default: newest review first),
  but not with `start_date`/`end_date`.

### Fixed

- Character lookup (formerly `get_characters`) always failed against the live API: it declared
  the book id as `Int!` where the API expects `bigint`, and asked for a `description` field that
  characters don't have.

### Added

- `HARDCOVER_TOOLSETS` environment variable to load only some toolsets (`core`, `catalog`,
  `library`, `lists`, `journal`, `social`; default all). `core` is always loaded.
- `HARDCOVER_READ_ONLY` environment variable to hide every tool that can modify your account.

### Changed

- Tool definitions now live next to their handlers in each `tools/` module instead of one large
  registry in `server.py`. The server checks at startup that every tool has a unique name,
  annotations, and a known toolset.
- Every tool now declares MCP tool annotations (`readOnlyHint`, `destructiveHint`,
  `idempotentHint`, `openWorldHint`), so clients can tell read-only lookups from writes and
  deletes without parsing descriptions.
- Rewrote all tool descriptions to state what each tool returns, its side effects
  (upsert/overwrite/permanent delete), prerequisites, and which sibling tool to use instead for
  related tasks.

## [0.7.2] - 2026-09-22

### Fixed

- The `authorization` header now sends the API token as `Bearer <token>`. Previously the raw
  token was passed through as-is, so a token stored in the env file without the `Bearer ` prefix
  produced an unauthenticated request. The prefix is added when missing and left intact when the
  stored value already includes it. (#54, thanks @laforcem)

## [0.7.1] - 2026-09-10

### Fixed

- Server failed to start (`AttributeError: 'Server' object has no attribute 'list_tools'`) when
  installed against the MCP SDK 2.x, whose low-level `Server` replaced the decorator API
  (`@server.list_tools()` / `@server.call_tool()`) with `on_list_tools` / `on_call_tool`
  constructor handlers. Migrated to the 2.x API and pinned `mcp>=2.0.0`. Added server-wiring
  smoke tests so SDK API drift is caught before release.

## [0.7.0] - 2026-09-10

### Added

- `follow_user` / `unfollow_user` tools — follow or unfollow a user by `user_id` or `username`.
- `get_trending_books` tool — currently trending books, most popular first, with a `duration`
  window (`all`/`week`/`month`/`three_month`/`one_year`) and `limit`/`offset` pagination.
- `get_vibes` tool — list Hardcover "vibes" (curated, themed book recommendation collections),
  each hydrated with its books. Filter to `featured` only; paginate with `limit`/`offset` and
  cap books per vibe with `books_per_vibe`.
- `search_books` now accepts `sort` (e.g. `rating:desc`) and `filter_by` (e.g.
  `release_year:>2020`), enabling faceted discovery like "top-rated fantasy since 2020".
- `get_user` tool — look up another user's public profile by `id`, `username`, or `name`.
  Returns bio, book/follower/following counts, flair, and privacy setting. Set
  `include_library=true` to also fetch recent library entries, optionally filtered by
  `library_status` and capped by `library_limit` (subject to the target user's privacy).
- `get_activity_feed` tool — recent reading activity (status changes, ratings, reviews, list
  updates), newest first. Defaults to the feed of users you follow; pass `user_id` or `username`
  to fetch a single user's activity. Paginated via `limit`/`offset`.

## [0.6.0] - 2026-09-07

### Added

- `get_prompts` tool — list community book prompts, optionally filtered to featured only,
  with `limit`/`offset` pagination. Returns `question`, `description`, `answers_count`, and
  `books_count`.
- `answer_prompt` tool — submit a book as an answer to a community prompt by `prompt_id` and
  `book_id`.

### Fixed

- `get_reading_stats` returned a 403 (`request_exceeds_capacity`) because it fired 9 top-level
  aggregate fields in one request, exceeding the API tier's burst capacity of 5. The aggregates
  are now split across two requests and merged.
- `add_journal_entry` defaulted `privacy_setting_id` to `0` when omitted, which the API silently
  rejects (returning a null entry and causing a crash). The default is now `1` (public), and a
  null response is surfaced as a clear error.


## [0.5.0] - 2026-07-06

### Added

- `get_characters` tool — fetch characters associated with a book by Hardcover ID. Returns character `id`, `name`, `slug`, and `description`.
- `get_publisher` tool — look up a publisher by ID, slug, or name. Returns publisher info, parent publisher, and a paginated list of editions sorted by popularity.
- `add_user_book_read` and `update_user_book_read` now accept `edition_id` parameter, enabling audiobook `progress_seconds` tracking (the Hardcover API requires an audiobook edition to be linked for time-based progress to persist).

### Fixed

- Journal `insert_reading_journal` mutation updated to match Hardcover API schema changes
  (`ReadingJournalCreateType!`, required `privacy_setting_id` and `tags` fields).
- Increased API retry backoff (5 retries, 3s initial) to prevent flaky test failures under load.
- Reading goal integration test now cleans up after itself instead of leaving orphan goals in the user's account.


## [0.4.0] - 2026-05-16

### Added

- `get_user_library` now accepts `start_date` and `end_date` parameters (ISO 8601) — returns
  books whose `finished_at` falls within the range, with `finished_at` and `started_at` in
  each result. Answers "what did I read in May last year?" in a single call.
- `get_user_library` now accepts `sort` (`updated`, `rating`, `date_added`) and `order`
  (`asc`, `desc`) parameters for server-side sorting. Use `sort=rating, order=desc` to get
  top-rated books without paging through the entire library.
- `get_reading_journal` tool — fetch reading journal entries (notes, quotes, status changes,
  ratings, reviews, and progress updates). Accepts optional filters: `book_id`, `event` type,
  `limit` (default 25, max 100), and `offset`. Returns `id`, `event`, `entry`, `action_at`,
  `book_id`, `edition_id`, `metadata`, `privacy_setting_id`, and book info (title, slug,
  authors).
- Added journal write tools: `add_journal_entry` (create note/quote entries) and
  `delete_journal_entry` (delete by ID).
- Added reading goal tools: `get_reading_goal` (active goals + progress) and
  `set_reading_goal` (create/update goal target, metric, and date range).

### Fixed

- Input validation for `get_user_library` sort/order/date parameters now runs before
  the authenticated user lookup, failing fast on bad input.
- Reading goal responses include complete fallback fields when the API returns
  partial data.

### Changed

- Moved shared `_require_iso_date` helper to `tools/_validation.py` for consistency
  with other validators.

## [0.3.0] - 2026-05-01

### Added

- `get_owned_books` tool — list all books you have marked as owned; returns title,
  authors, and edition details. Supports pagination via
  `page` and `per_page` (default 20, max 100).
- `set_edition_owned` tool — mark an edition as owned or not owned. Uses the
  `edition_owned` toggle mutation with idempotent state checking.
- `get_user_book` now includes `privacy` (Public/Followers/Private) in its response,
  mapped from `privacy_setting_id`.
- `set_user_book` now accepts a `privacy` parameter (label or numeric ID 1/2/3) to
  view and change the privacy setting on library entries. Existing privacy is preserved
  when the field is not specified.
- `set_user_book` now accepts `edition_id` to select the specific edition being read.
  `get_user_book` includes edition details in the response.
- `get_user_reviews` tool — list your reviews with review text, rating, spoiler flag, and book info.
- `set_user_book` now accepts `review_raw` (plain text, converted to Slate JSON),
  `review_has_spoilers`, `reviewed_at`, and `private_notes`. All new fields are
  preserved on update when not specified.
- `get_user_book` now returns `review_raw`, `review_has_spoilers`, `reviewed_at`,
  and `private_notes` in its response.
- `get_reading_stats` tool — returns library statistics (total books, books per status,
  average rating, and books read in a given year) via `user_books_aggregate`.
- `add_user_book_read` and `update_user_book_read` now accept `progress_seconds` for
  tracking audiobook listening progress.

### Fixed

- `get_series` and `get_author` tools now support partial, typo-tolerant name
  matching via the Hardcover Typesense search endpoint instead of disabled GraphQL
  LIKE operators.

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

[Unreleased]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.7.2...v0.8.0
[0.7.2]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/kristianedlund/hardcover-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/kristianedlund/hardcover-mcp/releases/tag/v0.1.0
