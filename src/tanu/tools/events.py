"""Local event tools for communication between skills and components."""

import json

from tanu.tools.base import ToolContext, param, register_tool


@register_tool(
    description=(
        "Publish a small event to other local skills and components. Events are "
        "in-memory, bounded, and never sent over the network."
    ),
    params=[
        param("topic", "Short event topic, for example task.completed"),
        param("message", "Concise event message"),
    ],
)
def publish_event(topic: str, message: str, _ctx: ToolContext = None) -> str:
    if not _ctx or not _ctx.event_bus:
        return "[TOOL ERROR] Local event bus is unavailable"
    try:
        event = _ctx.event_bus.publish(topic, {"message": message}, source="skill")
        return f"Published local event #{event.sequence}: {event.topic}"
    except ValueError as exc:
        return f"[TOOL ERROR] {exc}"


@register_tool(
    description="Read recent local events published by skills and runtime components.",
    params=[
        param("topic", "Optional exact topic filter", default=""),
        param("limit", "Maximum events to return (default 10, max 50)", type="integer", default=10),
    ],
)
def read_events(topic: str = "", limit: int = 10, _ctx: ToolContext = None) -> str:
    if not _ctx or not _ctx.event_bus:
        return "[TOOL ERROR] Local event bus is unavailable"
    return json.dumps(_ctx.event_bus.recent(topic=topic.strip().lower(), limit=limit), ensure_ascii=False)
