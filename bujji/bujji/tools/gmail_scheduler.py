"""
bujji/tools/gmail_scheduler.py

Background scheduler for sending scheduled emails.
Run with: python -m bujji.tools.gmail_scheduler
Or import and call Scheduler.start()
"""

from __future__ import annotations

import base64
import threading
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional

from bujji.tools.gmail_storage import GmailScheduled, GmailStats

GMAIL_SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]

TOKEN_FILE = Path(__file__).parent / "gmail_token.json"
MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024


class GmailScheduler:
    _instance: Optional["GmailScheduler"] = None
    _thread: Optional[threading.Thread] = None
    _running = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_service(self):
        import os

        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists(str(TOKEN_FILE)):
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), GMAIL_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(str(TOKEN_FILE), "w") as f:
                    f.write(creds.to_json())
            else:
                return None

        return build("gmail", "v1", credentials=creds)

    def _get_sender_email(self) -> str:
        try:
            service = self._get_service()
            if not service:
                return ""
            profile = service.users().getProfile(userId="me").execute()
            return profile.get("emailAddress", "")
        except Exception:
            return ""

    def _build_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = None,
        bcc: str = None,
        html: bool = False,
        attachments: list = None,
    ) -> dict:
        from email.mime.text import MIMEText

        sender = self._get_sender_email()

        if attachments:
            msg = MIMEMultipart("mixed")
            msg["From"] = sender
            msg["To"] = to.strip()
            msg["Subject"] = subject.strip()
            if cc:
                msg["Cc"] = cc.strip()

            if html:
                msg.attach(MIMEText(body, "plain"))
                msg.attach(MIMEText(body, "html"))
            else:
                msg.attach(MIMEText(body, "plain"))

            for filepath in attachments:
                p = Path(filepath)
                if not p.exists():
                    continue
                if p.stat().st_size > MAX_ATTACHMENT_SIZE:
                    continue
                with open(p, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={p.name}",
                )
                msg.attach(part)
        else:
            if html:
                msg = MIMEMultipart("alternative")
                msg.attach(MIMEText(body, "plain"))
                msg.attach(MIMEText(body, "html"))
            else:
                msg = MIMEText(body, "plain")
            msg["From"] = sender
            msg["To"] = to.strip()
            msg["Subject"] = subject.strip()
            if cc:
                msg["Cc"] = cc.strip()

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        return {"raw": raw}

    def _send_scheduled(self, schedule: dict) -> bool:
        try:
            service = self._get_service()
            if not service:
                GmailScheduled.update_status(
                    schedule["id"], "failed", "Not authenticated"
                )
                return False

            message = self._build_message(
                to=schedule["to"],
                subject=schedule["subject"],
                body=schedule["body"],
                cc=schedule.get("cc"),
                bcc=schedule.get("bcc"),
                html=schedule.get("html", False),
                attachments=schedule.get("attachments"),
            )

            service.users().messages().send(userId="me", body=message).execute()
            GmailScheduled.update_status(schedule["id"], "sent")
            GmailStats.record_sent(schedule["to"], success=True)
            print(
                f"[SCHEDULER] Sent scheduled email {schedule['id']} to {schedule['to']}"
            )
            return True

        except Exception as e:
            GmailScheduled.update_status(schedule["id"], "failed", str(e))
            print(f"[SCHEDULER] Failed to send {schedule['id']}: {e}")
            return False

    def _check_and_send(self) -> None:
        pending = GmailScheduled.get_pending()
        for schedule in pending:
            self._send_scheduled(schedule)

    def _loop(self) -> None:
        while self._running:
            self._check_and_send()
            time.sleep(30)

    def start(self, daemon: bool = True) -> None:
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=daemon)
        self._thread.start()
        print("[SCHEDULER] Started background scheduler")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[SCHEDULER] Stopped")

    def status(self) -> dict:
        pending = GmailScheduled.get_pending()
        all_scheduled = GmailScheduled.list()
        return {
            "running": self._running,
            "pending_count": len(pending),
            "total_scheduled": len(all_scheduled),
            "next_check_seconds": 30,
        }


_scheduler: Optional[GmailScheduler] = None


def get_scheduler() -> GmailScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = GmailScheduler()
    return _scheduler


def start_scheduler() -> None:
    get_scheduler().start()


def stop_scheduler() -> None:
    if _scheduler:
        _scheduler.stop()


if __name__ == "__main__":
    import sys

    if "--once" in sys.argv:
        print("[SCHEDULER] Running single check...")
        get_scheduler()._check_and_send()
    else:
        print("[SCHEDULER] Starting background scheduler (Ctrl+C to stop)")
        try:
            start_scheduler()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[SCHEDULER] Shutting down...")
            stop_scheduler()
