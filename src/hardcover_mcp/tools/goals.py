"""Tools: get_reading_goal, set_reading_goal, and delete_reading_goal."""

import json
from typing import Any

from mcp.types import TextContent, Tool

from hardcover_mcp.client import execute
from hardcover_mcp.tools._registry import DELETE, READ, UPDATE, ToolSpec
from hardcover_mcp.tools._results import list_result
from hardcover_mcp.tools._validation import (
    PRIVACY_DESCRIPTION,
    ToolError,
    _privacy_argument,
    _require_int,
    _require_iso_date,
    privacy_label,
)
from hardcover_mcp.tools.user import get_current_user

VALID_GOAL_METRICS = {"book", "page"}

GET_READING_GOAL_QUERY = """
query GetReadingGoal($user_id: Int!, $limit: Int!, $offset: Int!) {
    goals(
        where: {user_id: {_eq: $user_id}, archived: {_eq: false}},
        order_by: [{end_date: asc}, {id: asc}],
        limit: $limit,
        offset: $offset
    ) {
        id
        goal
        metric
        progress
        start_date
        end_date
        state
        privacy_setting_id
    }
}
"""

FIND_MATCHING_READING_GOAL_QUERY = """
query FindMatchingReadingGoal(
    $user_id: Int!,
    $metric: String!,
    $start_date: date!,
    $end_date: date!
) {
    goals(
        where: {
            user_id: {_eq: $user_id},
            metric: {_eq: $metric},
            start_date: {_eq: $start_date},
            end_date: {_eq: $end_date},
            archived: {_eq: false}
        },
        order_by: {id: desc},
        limit: 1
    ) {
        id
    }
}
"""

INSERT_READING_GOAL_MUTATION = """
mutation InsertReadingGoal($object: GoalInput!) {
    insert_goal(object: $object) {
        id
        errors
        goal {
            id
            goal
            metric
            progress
            start_date
            end_date
            state
            privacy_setting_id
            archived
        }
    }
}
"""

GET_OWN_GOAL_QUERY = """
query GetOwnGoal($id: Int!, $user_id: Int!) {
    goals(where: {id: {_eq: $id}, user_id: {_eq: $user_id}}, limit: 1) {
        id
        goal
        metric
        progress
        start_date
        end_date
        description
        state
        privacy_setting_id
        archived
    }
}
"""

DELETE_READING_GOAL_MUTATION = """
mutation DeleteReadingGoal($id: Int!) {
    delete_goal(id: $id) {
        id
        errors
    }
}
"""

UPDATE_READING_GOAL_MUTATION = """
mutation UpdateReadingGoal($id: Int!, $object: GoalInput!) {
    update_goal(id: $id, object: $object) {
        id
        errors
        goal {
            id
            goal
            metric
            progress
            start_date
            end_date
            state
            privacy_setting_id
            archived
        }
    }
}
"""


def _format_reading_goal(goal: dict[str, Any]) -> dict[str, Any]:
    """Format a goal record into the MCP response shape."""
    return {
        "id": goal.get("id"),
        "goal": goal.get("goal"),
        "metric": goal.get("metric"),
        "progress": goal.get("progress"),
        "start_date": goal.get("start_date"),
        "end_date": goal.get("end_date"),
        "state": goal.get("state"),
        "privacy": privacy_label(goal.get("privacy_setting_id")),
        "archived": goal.get("archived", False),
    }


def _require_metric(value: Any) -> str:
    """Validate and normalize goal metric values."""
    if not isinstance(value, str) or not value.strip():
        raise ToolError("'metric' must be a non-empty string ('book' or 'page')")
    metric = value.strip().lower()
    if metric not in VALID_GOAL_METRICS:
        raise ToolError("'metric' must be either 'book' or 'page'")
    return metric


async def handle_get_reading_goal(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch active (non-archived) reading goals for the authenticated user.

    Parameters
    ----------
    arguments : dict[str, Any]
        Optional: ``limit`` (int, default 10, max 100), ``offset`` (int, default 0).

    Returns
    -------
    list[TextContent]
        JSON ``{returned, offset, goals}``.
    """
    # --- 1. Validate input
    limit = _require_int(arguments.get("limit", 10), "limit")

    if limit <= 0:
        raise ToolError("'limit' must be greater than 0.")
    offset = _require_int(arguments.get("offset", 0), "offset")

    # --- 2. Resolve user and query active goals
    user = await get_current_user()
    result = await execute(
        GET_READING_GOAL_QUERY,
        {"user_id": user["id"], "limit": min(limit, 100), "offset": offset},
    )

    # --- 3. Format and return
    goals = [_format_reading_goal(goal) for goal in result["data"]["goals"]]
    return list_result("goals", goals, offset=offset)


async def handle_set_reading_goal(arguments: dict[str, Any]) -> list[TextContent]:
    """Create or update a reading goal for the authenticated user.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``goal`` (int), ``metric`` (str: books/pages), ``start_date`` (str),
        and ``end_date`` (str), both as ISO 8601 dates.
        Optional: ``description`` (str), ``privacy`` (public/followers/private or 1/2/3).
        With ``id`` (int), edits that goal instead — see ``_edit_reading_goal``.

    Returns
    -------
    list[TextContent]
        JSON object for the created or updated reading goal.
    """
    if arguments.get("id") is not None:
        return await _edit_reading_goal(arguments)
    if arguments.get("archived") is not None:
        raise ToolError("'archived' needs the goal's id (from get_reading_goal).")

    # --- 1. Validate required arguments
    for required in ("goal", "metric", "start_date", "end_date"):
        if required not in arguments:
            raise ToolError(f"'{required}' is required.")

    goal = _require_int(arguments["goal"], "goal")
    if goal <= 0:
        raise ToolError("'goal' must be greater than 0")
    metric = _require_metric(arguments["metric"])
    start_date = _require_iso_date(arguments["start_date"], "start_date")
    end_date = _require_iso_date(arguments["end_date"], "end_date")
    if end_date < start_date:
        raise ToolError("'end_date' must be on or after 'start_date'")

    description_raw = arguments.get("description")
    if description_raw is not None and not isinstance(description_raw, str):
        raise ToolError("'description' must be a string")
    description = description_raw if description_raw else f"{goal} {metric}s"

    privacy_setting_id = _privacy_argument(arguments)

    # --- 2. Build mutation input
    user = await get_current_user()
    goal_input: dict[str, Any] = {
        "goal": goal,
        "metric": metric,
        "start_date": start_date,
        "end_date": end_date,
        "description": description,
        "conditions": {},
    }
    if privacy_setting_id is not None:
        goal_input["privacy_setting_id"] = privacy_setting_id

    # --- 3. Update a matching active goal if present; otherwise create one
    existing_result = await execute(
        FIND_MATCHING_READING_GOAL_QUERY,
        {
            "user_id": user["id"],
            "metric": metric,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    existing_goals = existing_result["data"]["goals"]

    if existing_goals:
        mutation_result = await execute(
            UPDATE_READING_GOAL_MUTATION,
            {"id": existing_goals[0]["id"], "object": goal_input},
        )
        update_payload = mutation_result["data"]["update_goal"]
        if update_payload.get("errors"):
            errors = "; ".join(update_payload["errors"])
            raise ToolError(errors)
        raw_goal = update_payload.get("goal") or {
            **goal_input,
            "id": existing_goals[0]["id"],
            "progress": None,
            "state": None,
        }
    else:
        mutation_result = await execute(INSERT_READING_GOAL_MUTATION, {"object": goal_input})
        insert_payload = mutation_result["data"]["insert_goal"]
        if insert_payload.get("errors"):
            errors = "; ".join(insert_payload["errors"])
            raise ToolError(errors)
        raw_goal = insert_payload.get("goal") or {
            **goal_input,
            "id": insert_payload.get("id"),
            "progress": None,
            "state": None,
        }

    # --- 4. Format and return
    return [TextContent(type="text", text=json.dumps(_format_reading_goal(raw_goal), indent=2))]


async def _find_own_goal(goal_id: Any) -> dict[str, Any]:
    """Your goal with ``goal_id`` (any archived state); ``ToolError`` if there is none."""
    goal_id = _require_int(goal_id, "id")
    user = await get_current_user()
    found = await execute(GET_OWN_GOAL_QUERY, {"id": goal_id, "user_id": user["id"]})
    goals = found["data"]["goals"]
    if not goals:
        raise ToolError("no reading goal of yours with that id.")
    return goals[0]


async def _edit_reading_goal(arguments: dict[str, Any]) -> list[TextContent]:
    """Edit your goal by ``id``: only the fields passed change; ``archived`` hides/restores it.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``id`` (int). At least one of ``goal``, ``metric``, ``start_date``,
        ``end_date``, ``description``, ``privacy``, ``archived`` (bool).

    Returns
    -------
    list[TextContent]
        JSON object for the updated reading goal.
    """
    editable = (
        "goal",
        "metric",
        "start_date",
        "end_date",
        "description",
        "privacy",
        "archived",
    )
    privacy = _privacy_argument(arguments)
    if all(arguments.get(key) is None for key in editable):
        raise ToolError(f"provide at least one of {', '.join(repr(k) for k in editable)}.")

    current = await _find_own_goal(arguments["id"])

    def pick(key: str) -> Any:
        return arguments[key] if arguments.get(key) is not None else current.get(key)

    goal = _require_int(pick("goal"), "goal")
    if goal <= 0:
        raise ToolError("'goal' must be greater than 0")
    metric = _require_metric(pick("metric"))
    start_date = _require_iso_date(pick("start_date"), "start_date")
    end_date = _require_iso_date(pick("end_date"), "end_date")
    if end_date < start_date:
        raise ToolError("'end_date' must be on or after 'start_date'")
    archived = pick("archived")
    if not isinstance(archived, bool):
        raise ToolError("'archived' must be true or false")
    description = pick("description") or f"{goal} {metric}s"
    if not isinstance(description, str):
        raise ToolError("'description' must be a string")

    goal_input: dict[str, Any] = {
        "goal": goal,
        "metric": metric,
        "start_date": start_date,
        "end_date": end_date,
        "description": description,
        "archived": archived,
        # The goals table doesn't expose conditions, so they can't be read back and kept.
        "conditions": {},
    }
    if privacy is None:
        privacy = current.get("privacy_setting_id")
    if privacy is not None:
        goal_input["privacy_setting_id"] = privacy

    result = await execute(
        UPDATE_READING_GOAL_MUTATION, {"id": current["id"], "object": goal_input}
    )
    payload = result["data"]["update_goal"]
    if payload.get("errors"):
        raise ToolError("; ".join(payload["errors"]))
    raw_goal = payload.get("goal") or {**current, **goal_input}
    return [TextContent(type="text", text=json.dumps(_format_reading_goal(raw_goal), indent=2))]


async def handle_delete_reading_goal(arguments: dict[str, Any]) -> list[TextContent]:
    """Permanently delete one of your reading goals by ``id``.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``id`` (int).

    Returns
    -------
    list[TextContent]
        JSON confirmation ``{deleted: true, id}``.
    """
    if arguments.get("id") is None:
        raise ToolError("'id' is required.")
    current = await _find_own_goal(arguments["id"])

    result = await execute(DELETE_READING_GOAL_MUTATION, {"id": current["id"]})
    payload = result["data"]["delete_goal"] or {}
    if payload.get("errors"):
        raise ToolError("; ".join(payload["errors"]))
    return [TextContent(type="text", text=json.dumps({"deleted": True, "id": current["id"]}))]


# ── Tool definitions ──

TOOLS: list[ToolSpec] = [
    ToolSpec(
        Tool(
            name="get_reading_goal",
            description=(
                "Get your active (non-archived) reading goals, soonest end date first. "
                "Read-only. Returns {returned, offset, goals} with each goal's id, target, "
                "metric (book/page), progress, date range, privacy, and state; 'goals' is "
                "empty if you have none. To create or "
                "change or archive a goal use set_reading_goal; to delete one use "
                "delete_reading_goal."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max goals to return (default 10, max 100).",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Offset for pagination (default 0).",
                    },
                },
            },
            annotations=READ,
        ),
        handle_get_reading_goal,
        toolset="library",
        scopes=("read:goals", "read:me"),
    ),
    ToolSpec(
        Tool(
            name="set_reading_goal",
            description=(
                "Create, update, or archive a reading goal. Without id: goal, metric, "
                "start_date, and end_date are required; if an active goal with the same "
                "metric and dates exists its target, description, and privacy are "
                "overwritten, otherwise a new goal is created. With id (from "
                "get_reading_goal): edit that goal, changing only the fields you pass; "
                "archived=true hides it from get_reading_goal and archived=false brings it "
                "back. Returns the goal with id, target, progress, state, and archived. To "
                "remove a goal for good use delete_reading_goal."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Goal ID to edit (from get_reading_goal). Omit to create.",
                    },
                    "goal": {
                        "type": "integer",
                        "description": "Target count to reach by end_date.",
                    },
                    "metric": {
                        "type": "string",
                        "description": "Goal metric: 'book' or 'page'.",
                        "enum": ["book", "page"],
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date (ISO 8601, e.g. '2026-01-01').",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date (ISO 8601, e.g. '2026-12-31').",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional goal description.",
                    },
                    "privacy": {
                        "type": "string",
                        "description": PRIVACY_DESCRIPTION,
                    },
                    "archived": {
                        "type": "boolean",
                        "description": "With id: true archives the goal, false restores it.",
                    },
                },
            },
            annotations=UPDATE,
        ),
        handle_set_reading_goal,
        toolset="library",
        scopes=("read:goals", "read:me", "write:goals"),
    ),
    ToolSpec(
        Tool(
            name="delete_reading_goal",
            description=(
                "Permanently delete one of your reading goals by id (from get_reading_goal). "
                "Cannot be undone; to just hide a goal use set_reading_goal(id, "
                "archived=true). Your books and reading progress are unaffected. Returns "
                "{deleted: true, id}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": "Reading goal ID to delete.",
                    },
                },
                "required": ["id"],
            },
            annotations=DELETE,
        ),
        handle_delete_reading_goal,
        toolset="library",
        scopes=("read:goals", "read:me", "write:goals"),
    ),
]
