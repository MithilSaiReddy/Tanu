"""
bujji/tools/gmail_storage.py

Storage utilities for Gmail tools:
- Templates: Save and reuse common email responses
- Blocked senders: Manage blocked email addresses
- Scheduled emails: Store emails to be sent later
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

WORKSPACE_DIR = Path.home() / ".bujji" / "tanu"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATES_FILE = WORKSPACE_DIR / "gmail_templates.json"
BLOCKED_FILE = WORKSPACE_DIR / "gmail_blocked.json"
SCHEDULED_FILE = WORKSPACE_DIR / "gmail_scheduled.json"
STATS_FILE = WORKSPACE_DIR / "gmail_stats.json"


def _load_json(filepath: Path) -> dict | list:
    if filepath.exists():
        try:
            return json.loads(filepath.read_text())
        except (json.JSONDecodeError, IOError):
            return {} if filepath == STATS_FILE else []
    return {} if filepath == STATS_FILE else []


def _save_json(filepath: Path, data) -> None:
    filepath.write_text(json.dumps(data, indent=2, default=str))


class GmailTemplates:
    @staticmethod
    def list() -> list[dict]:
        templates = _load_json(TEMPLATES_FILE)
        return [
            {
                "id": t["id"],
                "name": t["name"],
                "subject": t["subject"],
                "preview": t["body"][:80] + "..." if len(t["body"]) > 80 else t["body"],
                "created": t.get("created", ""),
            }
            for t in templates
        ]

    @staticmethod
    def get(name: str) -> dict | None:
        templates = _load_json(TEMPLATES_FILE)
        for t in templates:
            if t["name"].lower() == name.lower():
                return t
        return None

    @staticmethod
    def save(name: str, subject: str, body: str, description: str = "") -> dict:
        templates = _load_json(TEMPLATES_FILE)
        template_id = str(uuid.uuid4())[:8]

        for i, t in enumerate(templates):
            if t["name"].lower() == name.lower():
                templates[i] = {
                    **t,
                    "subject": subject,
                    "body": body,
                    "description": description,
                    "updated": datetime.now().isoformat(),
                }
                _save_json(TEMPLATES_FILE, templates)
                return templates[i]

        templates.append(
            {
                "id": template_id,
                "name": name,
                "subject": subject,
                "body": body,
                "description": description,
                "created": datetime.now().isoformat(),
                "updated": datetime.now().isoformat(),
                "use_count": 0,
            }
        )
        _save_json(TEMPLATES_FILE, templates)
        return templates[-1]

    @staticmethod
    def delete(name: str) -> bool:
        templates = _load_json(TEMPLATES_FILE)
        original_len = len(templates)
        templates = [t for t in templates if t["name"].lower() != name.lower()]
        if len(templates) < original_len:
            _save_json(TEMPLATES_FILE, templates)
            return True
        return False

    @staticmethod
    def increment_use(name: str) -> None:
        templates = _load_json(TEMPLATES_FILE)
        for t in templates:
            if t["name"].lower() == name.lower():
                t["use_count"] = t.get("use_count", 0) + 1
                break
        _save_json(TEMPLATES_FILE, templates)


class GmailBlocked:
    @staticmethod
    def list() -> list[dict]:
        blocked = _load_json(BLOCKED_FILE)
        return blocked

    @staticmethod
    def add(email: str, reason: str = "") -> dict:
        blocked = _load_json(BLOCKED_FILE)
        email = email.lower().strip()

        for b in blocked:
            if b["email"] == email:
                return b

        entry = {
            "email": email,
            "reason": reason,
            "blocked_at": datetime.now().isoformat(),
        }
        blocked.append(entry)
        _save_json(BLOCKED_FILE, blocked)
        return entry

    @staticmethod
    def remove(email: str) -> bool:
        blocked = _load_json(BLOCKED_FILE)
        email = email.lower().strip()
        original_len = len(blocked)
        blocked = [b for b in blocked if b["email"] != email]
        if len(blocked) < original_len:
            _save_json(BLOCKED_FILE, blocked)
            return True
        return False

    @staticmethod
    def is_blocked(email: str) -> bool:
        blocked = _load_json(BLOCKED_FILE)
        email = email.lower().strip()
        return any(b["email"] == email for b in blocked)


class GmailScheduled:
    @staticmethod
    def list() -> list[dict]:
        scheduled = _load_json(SCHEDULED_FILE)
        return scheduled

    @staticmethod
    def add(
        to: str,
        subject: str,
        body: str,
        scheduled_at: datetime,
        cc: str = "",
        bcc: str = "",
        html: bool = False,
        attachments: list = None,
    ) -> dict:
        scheduled = _load_json(SCHEDULED_FILE)
        schedule_id = str(uuid.uuid4())[:8]

        entry = {
            "id": schedule_id,
            "to": to,
            "subject": subject,
            "body": body,
            "cc": cc,
            "bcc": bcc,
            "html": html,
            "attachments": attachments or [],
            "scheduled_at": scheduled_at.isoformat(),
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        scheduled.append(entry)
        _save_json(SCHEDULED_FILE, scheduled)
        return entry

    @staticmethod
    def get(schedule_id: str) -> dict | None:
        scheduled = _load_json(SCHEDULED_FILE)
        for s in scheduled:
            if s["id"] == schedule_id:
                return s
        return None

    @staticmethod
    def update_status(schedule_id: str, status: str, error: str = "") -> bool:
        scheduled = _load_json(SCHEDULED_FILE)
        for s in scheduled:
            if s["id"] == schedule_id:
                s["status"] = status
                if error:
                    s["error"] = error
                if status == "sent":
                    s["sent_at"] = datetime.now().isoformat()
                _save_json(SCHEDULED_FILE, scheduled)
                return True
        return False

    @staticmethod
    def cancel(schedule_id: str) -> bool:
        scheduled = _load_json(SCHEDULED_FILE)
        original_len = len(scheduled)
        scheduled = [s for s in scheduled if s["id"] != schedule_id]
        if len(scheduled) < original_len:
            _save_json(SCHEDULED_FILE, scheduled)
            return True
        return False

    @staticmethod
    def get_pending() -> list[dict]:
        scheduled = _load_json(SCHEDULED_FILE)
        now = datetime.now()
        return [
            s
            for s in scheduled
            if s["status"] == "pending"
            and datetime.fromisoformat(s["scheduled_at"]) <= now
        ]


class GmailStats:
    @staticmethod
    def record_sent(to: str, success: bool = True) -> None:
        stats = _load_json(STATS_FILE)
        today = datetime.now().strftime("%Y-%m-%d")

        if "sent" not in stats:
            stats["sent"] = {"daily": {}, "total": 0, "by_recipient": {}}

        if today not in stats["sent"]["daily"]:
            stats["sent"]["daily"][today] = 0
        stats["sent"]["daily"][today] += 1
        stats["sent"]["total"] += 1

        to_lower = to.lower()
        if to_lower not in stats["sent"]["by_recipient"]:
            stats["sent"]["by_recipient"][to_lower] = 0
        stats["sent"]["by_recipient"][to_lower] += 1

        _save_json(STATS_FILE, stats)

    @staticmethod
    def record_received(from_email: str) -> None:
        stats = _load_json(STATS_FILE)
        today = datetime.now().strftime("%Y-%m-%d")

        if "received" not in stats:
            stats["received"] = {"daily": {}, "total": 0, "by_sender": {}}

        if today not in stats["received"]["daily"]:
            stats["received"]["daily"][today] = 0
        stats["received"]["daily"][today] += 1
        stats["received"]["total"] += 1

        from_lower = from_email.lower()
        if from_lower not in stats["received"]["by_sender"]:
            stats["received"]["by_sender"][from_lower] = 0
        stats["received"]["by_sender"][from_lower] += 1

        _save_json(STATS_FILE, stats)

    @staticmethod
    def get_stats(days: int = 7) -> dict:
        stats = _load_json(STATS_FILE)
        now = datetime.now()
        cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")

        result = {
            "period_days": days,
            "sent": {"total": 0, "daily": {}},
            "received": {"total": 0, "daily": {}},
            "top_senders": [],
            "top_recipients": [],
        }

        sent = stats.get("sent", {})
        result["sent"]["total"] = sent.get("total", 0)
        for date, count in sent.get("daily", {}).items():
            if date >= cutoff:
                result["sent"]["daily"][date] = count
                result["sent"]["total"] += count

        received = stats.get("received", {})
        result["received"]["total"] = received.get("total", 0)
        for date, count in received.get("daily", {}).items():
            if date >= cutoff:
                result["received"]["daily"][date] = count
                result["received"]["total"] += count

        by_sender = sent.get("by_recipient", {})
        result["top_recipients"] = sorted(
            by_sender.items(), key=lambda x: x[1], reverse=True
        )[:5]

        by_recipient = received.get("by_sender", {})
        result["top_senders"] = sorted(
            by_recipient.items(), key=lambda x: x[1], reverse=True
        )[:5]

        return result


from datetime import timedelta
