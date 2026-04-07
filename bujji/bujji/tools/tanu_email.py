"""
bujji/tools/tanu_email.py

Gmail tools for Tanu using Gmail API with OAuth2.

Setup:
1. Go to console.cloud.google.com
2. Create OAuth2 credentials (Desktop app)
3. Download as credentials.json to bujji/bujji/credentials.json
4. Run: python -m bujji.tools.gmail_oauth --setup
5. Follow the browser auth flow

Tools:
    tanu_fetch_emails  - Fetch recent emails from inbox
    tanu_send_email    - Send a new email
    tanu_reply_email   - Reply to an email
    tanu_mark_email    - Mark email as read/unread
"""

from __future__ import annotations

import base64
import email
from datetime import datetime
from typing import Optional

from bujji.tools.base import ToolContext, param, register_tool

GMAIL_SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]

TOKEN_FILE_PATH: Optional[str] = None
CREDENTIALS_FILE_PATH: Optional[str] = None


def _get_paths():
    """Get token and credentials file paths."""
    global TOKEN_FILE_PATH, CREDENTIALS_FILE_PATH
    if TOKEN_FILE_PATH is None:
        from pathlib import Path

        tool_dir = Path(__file__).parent
        TOKEN_FILE_PATH = str(tool_dir / "gmail_token.json")
        CREDENTIALS_FILE_PATH = str(tool_dir / "credentials.json")
    return TOKEN_FILE_PATH, CREDENTIALS_FILE_PATH


def _is_oauth_enabled() -> bool:
    """Check if OAuth2 is configured."""
    token_file, creds_file = _get_paths()
    import os

    return os.path.exists(token_file) and os.path.exists(creds_file)


def _get_gmail_service():
    """Get authenticated Gmail service."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    import os

    token_file, _ = _get_paths()

    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError(
                "Gmail OAuth not configured.\n"
                "1. Download credentials.json from console.cloud.google.com\n"
                "2. Run: python -m bujji.tools.gmail_oauth --setup"
            )

    return build("gmail", "v1", credentials=creds)


def _get_sender_email() -> str:
    """Get the authenticated user's email."""
    try:
        service = _get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "")
    except Exception:
        return ""


def _parse_gmail_date(date_str: str) -> str:
    """Parse Gmail date to readable format."""
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(date_str)
        now = datetime.now()
        diff = now - dt

        if diff.days == 0:
            return dt.strftime("%I:%M %p")
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 7:
            return dt.strftime("%A")
        else:
            return dt.strftime("%b %d")
    except Exception:
        return ""


def _decode_body(msg: dict) -> str:
    """Extract body from Gmail message."""
    payload = msg.get("payload", {})
    body = ""

    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode(
                        "utf-8", errors="replace"
                    )
                    break
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    return body[:500].strip() if body else "(no body)"


def _get_header(msg: dict, name: str) -> str:
    """Get header from Gmail message."""
    headers = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


@register_tool(
    description=(
        "Fetch recent emails from inbox. Shows sender, subject, preview, and time. "
        "Use this when user asks 'check emails', 'show my emails', 'any new messages'."
    ),
    params=[
        param("limit", "Number of emails to fetch", type="integer", default=10),
        param("unread_only", "Only show unread emails", type="boolean", default=False),
    ],
)
def tanu_fetch_emails(
    limit: int = 10,
    unread_only: bool = False,
    _ctx: ToolContext = None,
) -> str:
    if not _is_oauth_enabled():
        return (
            "Gmail OAuth not configured.\n"
            "1. Go to console.cloud.google.com\n"
            "2. Create OAuth2 credentials (Desktop app)\n"
            "3. Download as credentials.json to bujji/bujji/\n"
            "4. Run: python -m bujji.tools.gmail_oauth --setup"
        )

    try:
        service = _get_gmail_service()

        query = "is:unread" if unread_only else ""

        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=limit)
            .execute()
        )

        messages = results.get("messages", [])

        if not messages:
            if unread_only:
                return "No unread emails."
            return "No emails in inbox."

        emails = []
        for msg_ref in messages:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="full")
                .execute()
            )

            sender = _get_header(msg, "From")
            sender_email = email.utils.parseaddr(sender)[1]
            sender_name = email.utils.parseaddr(sender)[0]
            subject = _get_header(msg, "Subject") or "(no subject)"
            date = _parse_gmail_date(_get_header(msg, "Date"))
            body_preview = _decode_body(msg)[:100]

            is_unread = "UNREAD" in msg.get("labelIds", [])

            sender_display = sender_name if sender_name else sender_email.split("@")[0]

            emails.append(
                {
                    "id": msg_ref["id"],
                    "from": sender_display,
                    "from_email": sender_email,
                    "subject": subject,
                    "date": date,
                    "preview": body_preview,
                    "unread": is_unread,
                }
            )

        total = len(emails)
        unread = sum(1 for e in emails if e.get("unread"))

        lines = [f"You have {total} email{'s' if total > 1 else ''}."]
        if unread:
            lines.append(f"{unread} unread.")
        lines.append("")

        for e in emails:
            marker = "●" if e.get("unread") else "○"
            lines.append(f"{marker} {e['from']} | {e['date']}")
            lines.append(f"  {e['subject'][:60]}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching emails: {e}"


@register_tool(
    description=(
        "Send an email. Use when user says 'send email to X', 'email X', 'send a message to X'."
    ),
    params=[
        param("to", "Recipient email address", required=True),
        param("subject", "Email subject line", required=True),
        param("body", "Email body content", required=True),
    ],
)
def tanu_send_email(
    to: str,
    subject: str,
    body: str,
    _ctx: ToolContext = None,
) -> str:
    if not to or not to.strip():
        return "Recipient email address is required."
    if not subject or not subject.strip():
        return "Email subject is required."

    if not _is_oauth_enabled():
        return (
            "Gmail OAuth not configured.\n"
            "1. Go to console.cloud.google.com\n"
            "2. Create OAuth2 credentials (Desktop app)\n"
            "3. Download as credentials.json to bujji/bujji/\n"
            "4. Run: python -m bujji.tools.gmail_oauth --setup"
        )

    try:
        service = _get_gmail_service()
        sender = _get_sender_email()

        message = {
            "raw": base64.urlsafe_b64encode(
                f"From: {sender}\r\n"
                f"To: {to.strip()}\r\n"
                f"Subject: {subject.strip()}\r\n\r\n"
                f"{body.strip()}".encode("utf-8")
            ).decode("ascii")
        }

        (service.users().messages().send(userId="me", body=message).execute())

        return f"Email sent to {to}."

    except Exception as e:
        return f"Error sending email: {e}"


@register_tool(
    description=(
        "Reply to an email. The reply will include the original message in the response."
    ),
    params=[
        param("email_id", "The email ID to reply to", required=True),
        param("body", "Your reply content", required=True),
        param("all", "Reply to all recipients", type="boolean", default=False),
    ],
)
def tanu_reply_email(
    email_id: str,
    body: str,
    all: bool = False,
    _ctx: ToolContext = None,
) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."
    if not body or not body.strip():
        return "Reply content is required."

    if not _is_oauth_enabled():
        return (
            "Gmail OAuth not configured.\n"
            "1. Go to console.cloud.google.com\n"
            "2. Create OAuth2 credentials (Desktop app)\n"
            "3. Download as credentials.json to bujji/bujji/\n"
            "4. Run: python -m bujji.tools.gmail_oauth --setup"
        )

    try:
        service = _get_gmail_service()
        sender = _get_sender_email()

        original = (
            service.users()
            .messages()
            .get(userId="me", id=email_id, format="full")
            .execute()
        )

        original_from = _get_header(original, "From")
        original_subject = _get_header(original, "Subject") or "(no subject)"
        original_date = _get_header(original, "Date")
        original_body = _decode_body(original)

        thread_id = original.get("threadId", "")

        reply_subject = original_subject
        if not reply_subject.startswith("Re:"):
            reply_subject = f"Re: {reply_subject}"

        to_email = email.utils.parseaddr(original_from)[1]

        reply_text = (
            f"\n\n--- Original ---\n"
            f"{original_subject}\n"
            f"Date: {original_date}\n\n"
            f"{original_body}\n\n"
            f"---\n"
            f"{body.strip()}"
        )

        message = {
            "raw": base64.urlsafe_b64encode(
                f"From: {sender}\r\n"
                f"To: {to_email}\r\n"
                f"Subject: {reply_subject}\r\n"
                f"In-Reply-To: {original.get('payload', {}).get('headers', [{}])[0].get('value', '')}\r\n"
                f"References: {original.get('payload', {}).get('headers', [{}])[0].get('value', '')}\r\n\r\n"
                f"{reply_text}".encode("utf-8")
            ).decode("ascii"),
            "threadId": thread_id,
        }

        (service.users().messages().send(userId="me", body=message).execute())

        return f"Replied to {to_email}."

    except Exception as e:
        return f"Error replying to email: {e}"


@register_tool(
    description=("Mark an email as read or unread."),
    params=[
        param("email_id", "The email ID to mark", required=True),
        param(
            "read",
            "Mark as read (true) or unread (false)",
            type="boolean",
            default=True,
        ),
    ],
)
def tanu_mark_email(
    email_id: str,
    read: bool = True,
    _ctx: ToolContext = None,
) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."

    if not _is_oauth_enabled():
        return (
            "Gmail OAuth not configured.\n"
            "1. Go to console.cloud.google.com\n"
            "2. Create OAuth2 credentials (Desktop app)\n"
            "3. Download as credentials.json to bujji/bujji/\n"
            "4. Run: python -m bujji.tools.gmail_oauth --setup"
        )

    try:
        service = _get_gmail_service()

        if read:
            body = {"removeLabelIds": ["UNREAD"]}
        else:
            body = {"addLabelIds": ["UNREAD"]}

        (
            service.users()
            .messages()
            .modify(userId="me", id=email_id, body=body)
            .execute()
        )

        status_text = "marked as read" if read else "marked as unread"
        return f"Email {status_text}."

    except Exception as e:
        return f"Error marking email: {e}"
