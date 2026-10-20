"""Check every GraphQL document each tool sends against Hardcover's published capabilities.

``tests/data/capabilities.json`` is a copy of https://api.hardcover.app/capabilities.json,
which maps each API operation (root field) to the token scopes that grant it. Refresh it when
Hardcover changes scopes:

    curl -s https://api.hardcover.app/capabilities.json -o tests/data/capabilities.json

Checks are per tool: the scopes a tool declares must grant every root field of every document
its handler can send, including documents of helpers it calls (like ``get_current_user``).
"""

import sys
from pathlib import Path

import pytest

from hardcover_mcp import server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _api_audit as audit

# Scopes declared for something capabilities.json can't see, because it only maps root fields.
EXTRA_SCOPES = {
    # include_library reads the nested users { user_books } relation.
    ("get_user", "read:library"),
    # Reads the nested me { followed_users } relation.
    ("set_following", "read:social"),
    # write:reviews gates review *arguments* (review_slate, reviewed_at, ...), not an operation.
    ("set_user_book", "write:reviews"),
    # owned=true filters through the nested book { list_books { list } } relation.
    ("get_user_library", "read:lists"),
}

# Hardcover's roadmap limits query depth to 3. Its docs explorer (config "matches API limit")
# counts fields inside the root object as level 0, which is depth 5 in ``audit.max_depth``
# (where the root fields are 1). Not enforced yet. Author names come from the
# ``cached_contributors`` JSON field where a relation chain would go too deep. Add a query
# here only as a tracked exception, and remove it once flattened.
DEPTH_LIMIT = 5
KNOWN_TOO_DEEP: set[str] = set()

GRANTING = audit.scopes_granting()
SPECS = {spec.tool.name: spec for spec in server.TOOL_REGISTRY}
DOCUMENTS = {name: audit.documents_for(spec.handler) for name, spec in SPECS.items()}


def _all_documents() -> dict[str, str]:
    return {doc: text for docs in DOCUMENTS.values() for doc, text in docs.items()}


@pytest.mark.parametrize("tool", sorted(SPECS))
def test_documents_were_found(tool):
    assert DOCUMENTS[tool], f"no GraphQL documents found for {tool}"


def test_every_root_field_is_a_known_api_operation():
    unknown = {
        (doc, field)
        for doc, text in _all_documents().items()
        for field in audit.root_fields(text)
        if field not in GRANTING
    }
    assert not unknown, f"root fields missing from capabilities.json: {sorted(unknown)}"


@pytest.mark.parametrize("tool", sorted(SPECS))
def test_declared_scopes_grant_every_operation(tool):
    declared = set(SPECS[tool].scopes)
    missing = {
        (doc.split("tools.")[-1], field, tuple(sorted(GRANTING[field])))
        for doc, text in DOCUMENTS[tool].items()
        for field in audit.root_fields(text)
        if field in GRANTING and not (GRANTING[field] & declared)
    }
    assert not missing, f"{tool} declares {sorted(declared)} but needs one of: {sorted(missing)}"


@pytest.mark.parametrize("tool", sorted(SPECS))
def test_no_unneeded_scopes(tool):
    used = {
        scope
        for text in DOCUMENTS[tool].values()
        for field in audit.root_fields(text)
        for scope in GRANTING.get(field, ())
    }
    declared = SPECS[tool].scopes
    unneeded = {s for s in declared if s not in used and (tool, s) not in EXTRA_SCOPES}
    assert not unneeded, f"{tool} declares scopes no query needs: {sorted(unneeded)}"


def test_extra_scopes_are_still_declared():
    stale = {(t, s) for t, s in EXTRA_SCOPES if s not in SPECS[t].scopes}
    assert not stale, f"EXTRA_SCOPES entries no longer declared; remove them: {sorted(stale)}"


def test_query_depth_within_documented_limit():
    depths = {doc: audit.max_depth(text) for doc, text in _all_documents().items()}
    too_deep = {doc for doc, depth in depths.items() if depth > DEPTH_LIMIT}
    new = too_deep - KNOWN_TOO_DEEP
    fixed = KNOWN_TOO_DEEP - too_deep
    assert not new, f"queries deeper than {DEPTH_LIMIT}: {sorted(new)}"
    assert not fixed, f"no longer too deep; remove from KNOWN_TOO_DEEP: {sorted(fixed)}"
