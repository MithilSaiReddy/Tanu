"""
bujji/tools/tanu_reminder.py

Reminder tools for Tanu with background worker.
Store reminders in workspace/tanu/reminders.json

Tools:
    tanu_set_reminder      - Set a reminder for a specific time
    tanu_list_reminders    - List upcoming reminders
    tanu_cancel_reminder   - Cancel a reminder

Background Worker:
    TanuReminderWorker     - Checks for due reminders every 30 seconds
                            - Triggers via voice (TTS), Telegram, Discord
"""

from __future__ import annotations

import json
import queue
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from bujji.tools.base import ToolContext, param, register_tool


REMINDERS_FILE = "reminders.json"
CHECK_INTERVAL = 10

_reminder_worker: Optional["TanuReminderWorker"] = None
_tts_queue: Optional[queue.Queue] = None
_telegram_send_fn = None
_discord_send_fn = None


def set_tts_queue(q: queue.Queue) -> None:
    """Set TTS queue for voice output."""
    global _tts_queue
    _tts_queue = q


def set_channel_fns(telegram_fn=None, discord_fn=None) -> None:
    """Set channel send functions for notifications."""
    global _telegram_send_fn, _discord_send_fn
    _telegram_send_fn = telegram_fn
    _discord_send_fn = discord_fn


def _get_tanu_workspace(_ctx: ToolContext) -> Path:
    """Get or create the tanu workspace directory."""
    tanu_dir = _ctx.workspace / "tanu"
    tanu_dir.mkdir(parents=True, exist_ok=True)
    return tanu_dir


def _load_reminders(_ctx: ToolContext) -> dict:
    """Load reminders from storage."""
    reminders_path = _get_tanu_workspace(_ctx) / REMINDERS_FILE
    if not reminders_path.exists():
        return {"reminders": []}
    try:
        return json.loads(reminders_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return {"reminders": []}


def _save_reminders(_ctx: ToolContext, data: dict) -> None:
    """Save reminders to storage."""
    reminders_path = _get_tanu_workspace(_ctx) / REMINDERS_FILE
    reminders_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _parse_time_input(time_str: str) -> Optional[datetime]:
    """Parse natural time input into datetime."""
    if not time_str:
        return None

    time_str = time_str.strip().lower()
    now = datetime.now()

    if time_str in ("now", "immediately"):
        return now

    if time_str.startswith("in "):
        return _parse_relative_time(time_str[3:], now)

    return _parse_absolute_time(time_str, now)


def _parse_relative_time(delta: str, base: datetime) -> Optional[datetime]:
    """Parse relative time like '30 minutes', '2 hours', 'tomorrow'."""
    import re

    delta = delta.strip()

    patterns = [
        (r"(\d+)\s*min(?:ute)?s?", lambda m: timedelta(minutes=int(m.group(1)))),
        (r"(\d+)\s*hours?", lambda m: timedelta(hours=int(m.group(1)))),
        (r"(\d+)\s*days?", lambda m: timedelta(days=int(m.group(1)))),
        (r"(\d+)\s*sec(?:ond)?s?", lambda m: timedelta(seconds=int(m.group(1)))),
    ]

    for pattern, delta_fn in patterns:
        match = re.match(pattern, delta)
        if match:
            return base + delta_fn(match)

    return None


def _parse_absolute_time(time_str: str, base: datetime) -> Optional[datetime]:
    """Parse absolute time like '3pm', 'tomorrow at 9am', 'monday'."""
    import re

    time_str = time_str.strip()

    if "tomorrow" in time_str:
        target_date = base.date() + timedelta(days=1)
        time_str = time_str.replace("tomorrow", "").strip()
    else:
        target_date = base.date()

    time_match = re.search(
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", time_str, re.IGNORECASE
    )
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or "0")
        period = time_match.group(3)

        if period:
            if period.lower() == "pm" and hour < 12:
                hour += 12
            elif period.lower() == "am" and hour == 12:
                hour = 0

        target_datetime = datetime.combine(
            target_date, datetime.min.time().replace(hour=hour, minute=minute)
        )
        return target_datetime

    return base + timedelta(hours=1)


def _format_time(dt: datetime) -> str:
    """Format datetime for display."""
    now = datetime.now()
    diff = dt - now

    if diff.total_seconds() < 0:
        return "past"

    if diff.total_seconds() < 60:
        return "in a moment"

    if diff.total_seconds() < 3600:
        mins = int(diff.total_seconds() / 60)
        return f"in {mins} minute{'s' if mins > 1 else ''}"

    if diff.days == 0:
        return f"at {dt.strftime('%I:%M %p').lstrip('0')}"

    if diff.days == 1:
        return f"tomorrow at {dt.strftime('%I:%M %p').lstrip('0')}"

    return f"on {dt.strftime('%b %d at %I:%M %p').lstrip('0')}"


@register_tool(
    description=(
        "Set a reminder for a specific time. The reminder will notify via "
        "voice, Telegram, or Discord depending on user preference and channel availability."
    ),
    params=[
        param("message", "What to remind about", required=True),
        param(
            "time",
            "When to remind (e.g. '3pm', 'tomorrow at 9am', 'in 30 minutes')",
            required=True,
        ),
        param(
            "channel",
            "How to notify",
            enum=["voice", "telegram", "discord", "both", "auto"],
            default="voice",
        ),
    ],
)
def tanu_set_reminder(
    message: str,
    time: str,
    channel: str = "voice",
    _ctx: ToolContext = None,
) -> str:
    if not message or not message.strip():
        return "Reminder message is required."
    if not time or not time.strip():
        return "Reminder time is required."

    reminder_time = _parse_time_input(time)
    if not reminder_time:
        return "Couldn't parse time. Try '3pm', 'tomorrow at 9am', or 'in 30 minutes'."

    if reminder_time < datetime.now():
        return "That time has already passed."

    if channel == "auto":
        channel = "both"

    reminders_data = _load_reminders(_ctx)

    reminder = {
        "id": str(uuid.uuid4())[:8],
        "message": message.strip(),
        "time": reminder_time.isoformat(),
        "channel": channel,
        "created": datetime.now().isoformat(),
        "triggered": None,
    }

    reminders_data["reminders"].insert(0, reminder)
    _save_reminders(_ctx, reminders_data)

    time_str = _format_time(reminder_time)
    return f"Reminder set for {time_str}."


@register_tool(
    description=(
        "List upcoming reminders. Shows all pending reminders sorted by time."
    ),
    params=[
        param(
            "filter",
            "Filter reminders",
            enum=["all", "upcoming", "past"],
            default="upcoming",
        ),
    ],
)
def tanu_list_reminders(
    filter: str = "upcoming",
    _ctx: ToolContext = None,
) -> str:
    reminders_data = _load_reminders(_ctx)
    reminders = reminders_data.get("reminders", [])

    if not reminders:
        return "No reminders set."

    now = datetime.now()
    filtered = []

    for r in reminders:
        try:
            r_time = datetime.fromisoformat(r["time"])
            r["_parsed_time"] = r_time
            r["_is_past"] = r_time < now
            r["_is_triggered"] = r.get("triggered") is not None
            filtered.append(r)
        except (ValueError, TypeError):
            pass

    if filter == "upcoming":
        filtered = [r for r in filtered if not r["_is_past"] and not r["_is_triggered"]]
    elif filter == "past":
        filtered = [r for r in filtered if r["_is_past"] or r["_is_triggered"]]

    if not filtered:
        return "No reminders."

    filtered.sort(key=lambda r: r["_parsed_time"])

    lines = [f"Found {len(filtered)} reminder{'s' if len(filtered) > 1 else ''}."]

    for r in filtered[:10]:
        time_str = _format_time(r["_parsed_time"])
        status = "✓ " if r["_is_triggered"] else ""
        msg = r["message"][:40] + ("..." if len(r["message"]) > 40 else "")
        lines.append(f"{status}{time_str}: {msg}")

    if len(filtered) > 10:
        lines.append(f"...and {len(filtered) - 10} more")

    return "\n".join(lines)


@register_tool(
    description=("Cancel a reminder. Removes the reminder without triggering it."),
    params=[
        param("reminder_id", "The reminder ID to cancel", required=True),
    ],
)
def tanu_cancel_reminder(
    reminder_id: str,
    _ctx: ToolContext = None,
) -> str:
    reminders_data = _load_reminders(_ctx)
    reminders = reminders_data.get("reminders", [])

    original_count = len(reminders)
    reminders = [r for r in reminders if r["id"] != reminder_id]

    if len(reminders) == original_count:
        return "Reminder not found."

    reminders_data["reminders"] = reminders
    _save_reminders(_ctx, reminders_data)

    return "Reminder cancelled."


class TanuReminderWorker:
    """
    Background worker that checks for due reminders every 30 seconds.
    Triggers notifications via voice (TTS), Telegram, or Discord.
    """

    def __init__(self, workspace: Path, check_interval: int = CHECK_INTERVAL):
        self.workspace = workspace
        self.check_interval = check_interval
        self._stop = threading.Event()
        self._running = False
        self._check_count = 0

    def start(self) -> None:
        """Start the background worker thread."""
        if self._running:
            return

        self._running = True
        self._stop.clear()
        thread = threading.Thread(target=self._run, daemon=True, name="TanutReminder")
        thread.start()
        print("[Tanu] Reminder worker started")

    def stop(self) -> None:
        """Stop the background worker."""
        self._running = False
        self._stop.set()
        print("[Tanu] Reminder worker stopped")

    def _run(self) -> None:
        """Main loop: check for due reminders."""
        while not self._stop.wait(self.check_interval):
            self._check()
            self._check_count += 1

    def _check(self) -> None:
        """Check for due reminders and trigger them."""
        reminders_path = self.workspace / "tanu" / REMINDERS_FILE
        if not reminders_path.exists():
            return

        try:
            data = json.loads(reminders_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return

        reminders = data.get("reminders", [])
        now = datetime.now()
        changed = False

        for r in reminders:
            if r.get("triggered"):
                continue

            try:
                r_time = datetime.fromisoformat(r["time"])
            except (ValueError, TypeError):
                continue

            if r_time <= now:
                self._trigger_reminder(r)
                r["triggered"] = now.isoformat()
                changed = True

        if changed:
            reminders_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    def _trigger_reminder(self, reminder: dict) -> None:
        """Trigger a single reminder via configured channels."""
        message = f"Reminder: {reminder['message']}"
        channel = reminder.get("channel", "both")

        print(f"[Tanu] Triggering reminder: {message}")

        if channel in ("voice", "both", "auto") and _tts_queue:
            try:
                _tts_queue.put(message, timeout=1)
            except queue.Full:
                print("[Tanu] TTS queue full, skipping voice")

        if channel in ("telegram", "both") and _telegram_send_fn:
            try:
                _telegram_send_fn(message)
            except Exception as e:
                print(f"[Tanu] Telegram send error: {e}")

        if channel in ("discord", "both") and _discord_send_fn:
            try:
                _discord_send_fn(message)
            except Exception as e:
                print(f"[Tanu] Discord send error: {e}")

    def get_status(self) -> dict:
        """Get worker status for debugging."""
        return {
            "running": self._running,
            "checks": self._check_count,
            "interval": self.check_interval,
        }


def get_worker() -> Optional[TanuReminderWorker]:
    """Get the global reminder worker instance."""
    return _reminder_worker


def init_worker(workspace: Path) -> TanuReminderWorker:
    """Initialize the global reminder worker."""
    global _reminder_worker
    if _reminder_worker is None:
        _reminder_worker = TanuReminderWorker(workspace)
    return _reminder_worker
