"""
tanu/notifier.py — Cross-platform desktop notifications for Tanu.

Uses plyer when available, with graceful fallbacks:
  - Linux:  notify-send (libnotify)
  - macOS:  osascript (AppleScript)
  - Windows: plyer (requires pywin32)
"""

from __future__ import annotations

import logging
import platform
import subprocess
import sys
from typing import Optional

LOG = logging.getLogger(__name__)

_has_plyer = False
try:
    from plyer import notification as plyer_notification
    _has_plyer = True
except ImportError:
    pass


def notify(
    title: str,
    message: str,
    urgency: str = "normal",
    timeout: int = 5,
    app_name: str = "Tanu",
) -> bool:
    """Show a desktop notification. Returns True if delivered."""
    if not title or not message:
        return False

    system = platform.system()

    if _has_plyer:
        try:
            plyer_notification.notify(
                title=title,
                message=message,
                app_name=app_name,
                timeout=timeout,
            )
            return True
        except Exception as exc:
            LOG.debug(f"plyer notification failed: {exc}")

    if system == "Linux":
        try:
            urgency_flag = {
                "low": "--urgency=low",
                "normal": "--urgency=normal",
                "critical": "--urgency=critical",
            }.get(urgency, "--urgency=normal")

            subprocess.run(
                ["notify-send", urgency_flag, title, message],
                timeout=timeout,
                capture_output=True,
            )
            return True
        except FileNotFoundError:
            LOG.debug("notify-send not available")
        except Exception as exc:
            LOG.debug(f"notify-send failed: {exc}")

    elif system == "Darwin":
        try:
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(
                ["osascript", "-e", script],
                timeout=timeout,
                capture_output=True,
            )
            return True
        except FileNotFoundError:
            LOG.debug("osascript not available")
        except Exception as exc:
            LOG.debug(f"osascript failed: {exc}")

    elif system == "Windows":
        LOG.debug("Windows notification requires plyer (pip install plyer)")

    return False


def notify_reminder(message: str) -> bool:
    """Shorthand: show a reminder notification."""
    return notify(
        title="Reminder",
        message=message,
        urgency="critical",
        timeout=10,
    )


def notify_email(sender: str, subject: str) -> bool:
    """Shorthand: show an email notification."""
    return notify(
        title="New Email",
        message=f"{sender}: {subject}",
        timeout=6,
    )
