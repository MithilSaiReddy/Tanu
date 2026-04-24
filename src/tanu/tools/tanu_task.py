"""
bujji/tools/tanu_task.py

Task management tools for Tanu.
Store tasks in workspace/tanu/tasks.json

Tools:
    tanu_create_task   - Create a new task
    tanu_list_tasks    - List all tasks with optional filtering
    tanu_complete_task - Mark a task as complete
    tanu_update_task   - Update task details
    tanu_delete_task   - Delete a task
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from bujji.tools.base import ToolContext, param, register_tool


TASKS_FILE = "tasks.json"


def _get_tanu_workspace(_ctx: ToolContext) -> Path:
    """Get or create the tanu workspace directory."""
    tanu_dir = _ctx.workspace / "tanu"
    tanu_dir.mkdir(parents=True, exist_ok=True)
    return tanu_dir


def _load_tasks(_ctx: ToolContext) -> dict:
    """Load tasks from storage."""
    tasks_path = _get_tanu_workspace(_ctx) / TASKS_FILE
    if not tasks_path.exists():
        return {"tasks": []}
    try:
        return json.loads(tasks_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return {"tasks": []}


def _save_tasks(_ctx: ToolContext, data: dict) -> None:
    """Save tasks to storage."""
    tasks_path = _get_tanu_workspace(_ctx) / TASKS_FILE
    tasks_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


@register_tool(
    description=(
        "Create a new task. Use when the user wants to remember something "
        "or track something they need to do."
    ),
    params=[
        param("title", "Task title or description", required=True),
        param(
            "priority",
            "Task priority",
            enum=["high", "medium", "low"],
            default="medium",
        ),
        param(
            "due",
            "Due date/time (ISO format or natural like 'tomorrow at 3pm')",
            default=None,
        ),
        param("notes", "Additional notes or details about the task", default=None),
    ],
)
def tanu_create_task(
    title: str,
    priority: str = "medium",
    due: str = None,
    notes: str = None,
    _ctx: ToolContext = None,
) -> str:
    if not title or not title.strip():
        return "Task title is required."

    tasks_data = _load_tasks(_ctx)

    task = {
        "id": str(uuid.uuid4())[:8],
        "title": title.strip(),
        "priority": priority,
        "due": due,
        "notes": notes,
        "created": datetime.now().isoformat(),
        "completed": None,
    }

    tasks_data["tasks"].insert(0, task)
    _save_tasks(_ctx, tasks_data)

    due_str = f", due {due}" if due else ""
    return f"Done. Created: {title}{due_str}"


@register_tool(
    description=(
        "List all tasks or filter by status. Use when the user asks "
        "'what do I have?', 'show tasks', or 'list my tasks'."
    ),
    params=[
        param(
            "filter",
            "Filter tasks by status",
            enum=["all", "pending", "completed"],
            default="all",
        ),
    ],
)
def tanu_list_tasks(
    filter: str = "all",
    _ctx: ToolContext = None,
) -> str:
    tasks_data = _load_tasks(_ctx)
    tasks = tasks_data.get("tasks", [])

    if not tasks:
        return "No tasks yet."

    if filter == "pending":
        tasks = [t for t in tasks if not t.get("completed")]
    elif filter == "completed":
        tasks = [t for t in tasks if t.get("completed")]

    if not tasks:
        status_str = f" {filter}" if filter != "all" else ""
        return f"No{status_str} tasks."

    total = len(tasks)
    pending = sum(1 for t in tasks if not t.get("completed"))
    completed = total - pending

    lines = [f"You have {total} task{'s' if total > 1 else ''}."]

    if filter == "all":
        lines.append(f"{pending} pending, {completed} completed.")

    lines.append("")
    for i, task in enumerate(tasks[:10], 1):
        status = "✓" if task.get("completed") else "○"
        priority_mark = {"high": "!", "medium": "", "low": "."}.get(
            task.get("priority", "medium"), ""
        )
        title = task["title"][:50] + ("..." if len(task["title"]) > 50 else "")
        due = f" (due: {task['due']})" if task.get("due") else ""
        lines.append(f"{status} {title}{due}{priority_mark}")

    if len(tasks) > 10:
        lines.append(f"...and {len(tasks) - 10} more")

    return "\n".join(lines)


@register_tool(
    description=(
        "Mark a task as complete. Use when the user confirms something is done "
        "or says 'complete task', 'done with task', 'finished task'."
    ),
    params=[
        param("task_id", "The task ID to mark complete", required=False),
        param("title", "Or search by title (partial match)", required=False),
    ],
)
def tanu_complete_task(
    task_id: str = None,
    title: str = None,
    _ctx: ToolContext = None,
) -> str:
    tasks_data = _load_tasks(_ctx)
    tasks = tasks_data.get("tasks", [])

    target_task = None

    if task_id:
        for t in tasks:
            if t["id"] == task_id:
                target_task = t
                break
    elif title:
        title_lower = title.lower()
        for t in tasks:
            if not t.get("completed") and title_lower in t["title"].lower():
                target_task = t
                break

    if not target_task:
        return "Task not found."

    if target_task.get("completed"):
        return f"Already done: {target_task['title']}"

    target_task["completed"] = datetime.now().isoformat()
    _save_tasks(_ctx, tasks_data)

    return "Done."


@register_tool(
    description=(
        "Update a task's details. Use when the user wants to change "
        "the title, priority, due date, or notes of an existing task."
    ),
    params=[
        param("task_id", "The task ID to update", required=True),
        param("title", "New title", required=False),
        param(
            "priority", "New priority", enum=["high", "medium", "low"], required=False
        ),
        param("due", "New due date/time", required=False),
        param("notes", "New notes", required=False),
    ],
)
def tanu_update_task(
    task_id: str,
    title: str = None,
    priority: str = None,
    due: str = None,
    notes: str = None,
    _ctx: ToolContext = None,
) -> str:
    tasks_data = _load_tasks(_ctx)
    tasks = tasks_data.get("tasks", [])

    target_task = None
    for t in tasks:
        if t["id"] == task_id:
            target_task = t
            break

    if not target_task:
        return "Task not found."

    if title is not None:
        target_task["title"] = title.strip()
    if priority is not None:
        target_task["priority"] = priority
    if due is not None:
        target_task["due"] = due
    if notes is not None:
        target_task["notes"] = notes

    _save_tasks(_ctx, tasks_data)

    return f"Updated: {target_task['title']}"


@register_tool(
    description=(
        "Delete a task permanently. Use when the user wants to remove a task "
        "without completing it."
    ),
    params=[
        param("task_id", "The task ID to delete", required=True),
    ],
)
def tanu_delete_task(
    task_id: str,
    _ctx: ToolContext = None,
) -> str:
    tasks_data = _load_tasks(_ctx)
    tasks = tasks_data.get("tasks", [])

    original_count = len(tasks)
    tasks = [t for t in tasks if t["id"] != task_id]

    if len(tasks) == original_count:
        return "Task not found."

    tasks_data["tasks"] = tasks
    _save_tasks(_ctx, tasks_data)

    return "Task deleted."
