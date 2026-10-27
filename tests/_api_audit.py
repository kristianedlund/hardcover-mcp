"""Collect the GraphQL documents each tool can send, for scope and depth checks.

Used by ``tests/tools/test_api_audit.py``. Starting from a tool's handler, this follows every
global name the code references: GraphQL string constants are collected, query-rendering
helpers are called with every flag combination, and other functions from this package
(including helpers imported from other modules, like ``get_current_user``) are followed
recursively.
"""

import inspect
import itertools
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from types import CodeType, FunctionType

from graphql import FieldNode, OperationDefinitionNode, parse
from graphql.error import GraphQLSyntaxError

CAPABILITIES = Path(__file__).parent / "data" / "capabilities.json"

# Query-rendering helpers and the argument combinations that produce every variant.
_RENDERERS: dict[str, list[dict]] = {
    "_render_library_query": [
        {
            "with_status": s,
            "order_field": "updated_at",
            "order_dir": "desc",
            "with_review": r,
            "with_owned": o,
        }
        for s, r, o in itertools.product([False, True], repeat=3)
    ],
    "_render_library_by_date_query": [
        {"with_status": s, "with_owned": o} for s, o in itertools.product([False, True], repeat=2)
    ],
    "_render_user_query": [
        {
            "by": by,
            "with_library": lib,
            "with_status": st,
            "with_following": fg,
            "with_followers": fs,
        }
        for by in ("id", "username")
        for lib, st in [(False, False), (True, False), (True, True)]
        for fg, fs in itertools.product([False, True], repeat=2)
    ],
    "_render_vibes_query": [{"featured_only": f} for f in (False, True)],
}


def _is_document(value: object) -> bool:
    if not isinstance(value, str) or ("query" not in value and "mutation" not in value):
        return False
    try:
        parse(value)
    except GraphQLSyntaxError:
        return False
    return True


def _names(code: CodeType) -> Iterator[str]:
    """Global names referenced by ``code`` and any nested functions/lambdas/comprehensions."""
    yield from code.co_names
    for const in code.co_consts:
        if isinstance(const, CodeType):
            yield from _names(const)


def _render_variants(func: Callable) -> dict[str, str]:
    accepted = inspect.signature(func).parameters
    return {
        f"{func.__module__}.{func.__name__}[{i}]": func(
            **{k: v for k, v in kwargs.items() if k in accepted}
        )
        for i, kwargs in enumerate(_RENDERERS[func.__name__])
    }


def documents_for(handler: Callable) -> dict[str, str]:
    """``{document_name: text}`` for every GraphQL document ``handler`` can send."""
    docs: dict[str, str] = {}
    seen: set[int] = set()

    def visit(func: FunctionType) -> None:
        if id(func) in seen:
            return
        seen.add(id(func))
        for name in _names(func.__code__):
            value = func.__globals__.get(name)
            if _is_document(value):
                docs[f"{func.__module__}.{name}"] = value
            elif isinstance(value, FunctionType) and value.__module__.startswith("hardcover_mcp"):
                if value.__name__ in _RENDERERS:
                    docs.update(_render_variants(value))
                else:
                    visit(value)

    visit(handler)
    return docs


def root_fields(text: str) -> set[str]:
    """Names of the root fields of every operation in the document."""
    return {
        selection.name.value
        for definition in parse(text).definitions
        if isinstance(definition, OperationDefinitionNode)
        for selection in definition.selection_set.selections
        if isinstance(selection, FieldNode)
    }


def max_depth(text: str) -> int:
    """Deepest selection-set nesting; the operation's own selection set (root fields) is 1."""

    def depth(selection_set, level: int) -> int:
        return max(
            (
                depth(sel.selection_set, level + 1)
                for sel in selection_set.selections
                if isinstance(sel, FieldNode) and sel.selection_set
            ),
            default=level,
        )

    return max(
        depth(d.selection_set, 1)
        for d in parse(text).definitions
        if isinstance(d, OperationDefinitionNode)
    )


def scopes_granting() -> dict[str, set[str]]:
    """``{operation: {scopes that grant it, including broader scopes that imply them}}``."""
    caps = json.loads(CAPABILITIES.read_text(encoding="utf-8"))
    implied_by: dict[str, set[str]] = {}
    for scope in caps["scopes"]:
        for child in scope.get("implies", []):
            implied_by.setdefault(child, set()).add(scope["scope"])
    granting: dict[str, set[str]] = {}
    for scope in caps["scopes"]:
        grantors = {scope["scope"], *implied_by.get(scope["scope"], ())}
        for op in scope.get("operations", []):
            granting.setdefault(op, set()).update(grantors)
    # "all" grants everything; leaving it out keeps the check about specific scopes.
    return {op: s - {"all"} for op, s in granting.items()}
