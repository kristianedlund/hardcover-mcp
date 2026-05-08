"""Tools: get_reading_goal and set_reading_goal."""

import json
from datetime import date
from typing import Any

from mcp.types import TextContent

from hardcover_mcp.client import execute
from hardcover_mcp.tools._validation import _require_int
from hardcover_mcp.tools.user import get_current_user

VALID_GOAL_METRICS = {"books", "pages"}

GET_READING_GOAL_QUERY = """
query GetReadingGoal($user_id: Int!, $limit: Int!) {
    goals(
        where: {user_id: {_eq: $user_id}, archived: {_eq: false}},
        order_by: {end_date: asc},
        limit: $limit
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
mutation InsertReadingGoal($object: ReadingGoalInput!) {
    insert_reading_goal(object: $object) {
        id
        reading_goal {
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
}
"""

UPDATE_READING_GOAL_MUTATION = """
mutation UpdateReadingGoal($id: Int!, $object: ReadingGoalInput!) {
    update_reading_goal(id: $id, object: $object) {
        id
        reading_goal {
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
        "privacy_setting_id": goal.get("privacy_setting_id"),
    }


def _require_iso_date(value: Any, name: str) -> str:
    """Validate and return an ISO 8601 date string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{name}' must be a non-empty ISO 8601 date string")
    normalized = value.strip()
    try:
        date.fromisoformat(normalized)
    except ValueError:
        raise ValueError(
            f"'{name}' must be an ISO 8601 date (YYYY-MM-DD), got: {value!r}"
        ) from None
    return normalized


def _require_metric(value: Any) -> str:
    """Validate and normalize goal metric values."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("'metric' must be a non-empty string ('books' or 'pages')")
    metric = value.strip().lower()
    if metric not in VALID_GOAL_METRICS:
        raise ValueError("'metric' must be either 'books' or 'pages'")
    return metric


async def handle_get_reading_goal(arguments: dict[str, Any]) -> list[TextContent]:
    """Fetch active (non-archived) reading goals for the authenticated user.

    Parameters
    ----------
    arguments : dict[str, Any]
        Optional: ``limit`` (int, default 10, max 100).

    Returns
    -------
    list[TextContent]
        JSON payload with ``goals`` and ``returned``.
    """
    # --- 1. Validate input
    try:
        limit = _require_int(arguments.get("limit", 10), "limit")
    except ValueError as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]

    if limit <= 0:
        return [TextContent(type="text", text="Error: 'limit' must be greater than 0.")]

    # --- 2. Resolve user and query active goals
    user = await get_current_user()
    result = await execute(
        GET_READING_GOAL_QUERY,
        {"user_id": user["id"], "limit": min(limit, 100)},
    )

    # --- 3. Format and return
    goals = [_format_reading_goal(goal) for goal in result["data"]["goals"]]
    payload = {"goals": goals, "returned": len(goals)}
    return [TextContent(type="text", text=json.dumps(payload, indent=2))]


async def handle_set_reading_goal(arguments: dict[str, Any]) -> list[TextContent]:
    """Create or update a reading goal for the authenticated user.

    Parameters
    ----------
    arguments : dict[str, Any]
        Required: ``goal`` (int), ``metric`` (str: books/pages), ``start_date`` (str),
        and ``end_date`` (str), both as ISO 8601 dates.
        Optional: ``description`` (str), ``privacy_setting_id`` (int).

    Returns
    -------
    list[TextContent]
        JSON object for the created or updated reading goal.
    """
    # --- 1. Validate required arguments
    for required in ("goal", "metric", "start_date", "end_date"):
        if required not in arguments:
            return [TextContent(type="text", text=f"Error: '{required}' is required.")]

    try:
        goal = _require_int(arguments["goal"], "goal")
        if goal <= 0:
            raise ValueError("'goal' must be greater than 0")
        metric = _require_metric(arguments["metric"])
        start_date = _require_iso_date(arguments["start_date"], "start_date")
        end_date = _require_iso_date(arguments["end_date"], "end_date")
        if end_date < start_date:
            raise ValueError("'end_date' must be on or after 'start_date'")

        description = arguments.get("description")
        if description is not None and not isinstance(description, str):
            raise ValueError("'description' must be a string")

        privacy_setting_id = None
        if "privacy_setting_id" in arguments and arguments["privacy_setting_id"] is not None:
            privacy_setting_id = _require_int(
                arguments["privacy_setting_id"],
                "privacy_setting_id",
            )
    except ValueError as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]

    # --- 2. Build mutation input
    user = await get_current_user()
    goal_input: dict[str, Any] = {
        "user_id": user["id"],
        "goal": goal,
        "metric": metric,
        "start_date": start_date,
        "end_date": end_date,
    }
    if description is not None:
        goal_input["description"] = description
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
        raw_goal = mutation_result["data"]["update_reading_goal"].get("reading_goal") or {
            **goal_input,
            "id": existing_goals[0]["id"],
            "progress": None,
            "state": None,
        }
    else:
        mutation_result = await execute(INSERT_READING_GOAL_MUTATION, {"object": goal_input})
        insert_payload = mutation_result["data"]["insert_reading_goal"]
        raw_goal = insert_payload.get("reading_goal") or {
            **goal_input,
            "id": insert_payload.get("id"),
            "progress": None,
            "state": None,
        }

    # --- 4. Format and return
    return [TextContent(type="text", text=json.dumps(_format_reading_goal(raw_goal), indent=2))]
