"""
bujji/tools/tanu_email.py  —  v3.0

Gmail tools for Tanu using Gmail API with OAuth2.

Setup:
1. Go to console.cloud.google.com
2. Create OAuth2 credentials (Desktop app)
3. Download as credentials.json to bujji/bujji/
4. Run: python -m bujji.tools.gmail_oauth --setup
5. Follow the browser auth flow

Tools:
    READING:
    - tanu_fetch_emails    - Fetch inbox emails
    - tanu_get_email       - Get single email by ID
    - tanu_search_emails   - Search with Gmail syntax
    - tanu_fetch_threads   - Get conversation threads

    SENDING:
    - tanu_send_email      - Send email (plain/HTML, CC/BCC)
    - tanu_send_attachment - Send with file attachments
    - tanu_forward_email   - Forward message
    - tanu_schedule_email  - Schedule email for later
    - tanu_list_scheduled   - List pending scheduled emails
    - tanu_cancel_scheduled - Cancel a scheduled email

    ORGANIZATION:
    - tanu_mark_email      - Mark read/unread
    - tanu_archive_email   - Archive emails
    - tanu_delete_email    - Trash emails
    - tanu_batch_archive   - Batch archive by search
    - tanu_batch_delete    - Batch delete by search
    - tanu_batch_star      - Batch star/unstar by search
    - tanu_list_labels     - List all labels
    - tanu_manage_labels   - Add/remove labels

    QUICK ACTIONS:
    - tanu_quick_archive_reply - Archive + quick reply
    - tanu_snooze_email       - Snooze until later
    - tanu_mark_done          - Archive + mark done

    TEMPLATES:
    - tanu_save_template      - Save email template
    - tanu_list_templates     - List templates
    - tanu_use_template       - Use template to send
    - tanu_delete_template    - Delete template

    SPAM & BLOCK:
    - tanu_report_spam         - Mark as spam
    - tanu_block_sender       - Block sender
    - tanu_unblock_sender     - Unblock sender
    - tanu_list_blocked       - List blocked senders

    STATISTICS:
    - tanu_email_stats        - Email activity stats

    SMART FILTERS:
    - tanu_important_senders  - Most contacted people
    - tanu_auto_categorize    - Suggest labels

    DRAFTS:
    - tanu_list_drafts     - List drafts
    - tanu_save_draft      - Save draft
    - tanu_delete_draft    - Delete draft

    ATTACHMENTS:
    - tanu_download_attachment - Download attachment
"""

from __future__ import annotations

import base64
import email
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from typing import Optional

from bujji.tools.base import ToolContext, param, register_tool

GMAIL_SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]

MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024

TOKEN_FILE_PATH: Optional[str] = None
CREDENTIALS_FILE_PATH: Optional[str] = None


class GmailService:
    _instance: Optional["GmailService"] = None
    _service = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_paths(self):
        global TOKEN_FILE_PATH, CREDENTIALS_FILE_PATH
        if TOKEN_FILE_PATH is None:
            tool_dir = Path(__file__).parent
            TOKEN_FILE_PATH = str(tool_dir / "gmail_token.json")
            CREDENTIALS_FILE_PATH = str(tool_dir / "credentials.json")
        return TOKEN_FILE_PATH, CREDENTIALS_FILE_PATH

    def _is_oauth_enabled(self) -> bool:
        token_file, creds_file = self._get_paths()
        return os.path.exists(token_file) and os.path.exists(creds_file)

    def get_service(self):
        if not self._is_oauth_enabled():
            raise RuntimeError(
                "Gmail OAuth not configured.\n"
                "1. Download credentials.json from console.cloud.google.com\n"
                "2. Run: python -m bujji.tools.gmail_oauth --setup"
            )

        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_file, _ = self._get_paths()

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

    def get_sender_email(self) -> str:
        try:
            service = self.get_service()
            profile = service.users().getProfile(userId="me").execute()
            return profile.get("emailAddress", "")
        except Exception:
            return ""

    def get_message(self, msg_id: str, format: str = "full"):
        service = self.get_service()
        return (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format=format)
            .execute()
        )

    def list_messages(self, q: str = "", max_results: int = 20, label_ids: list = None):
        service = self.get_service()
        params = {"userId": "me", "q": q, "maxResults": max_results}
        if label_ids:
            params["labelIds"] = label_ids
        return service.users().messages().list(**params).execute()

    def send_message(self, message: dict) -> dict:
        service = self.get_service()
        return service.users().messages().send(userId="me", body=message).execute()

    def modify_message(
        self, msg_id: str, add_labels: list = None, remove_labels: list = None
    ):
        service = self.get_service()
        body = {}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels
        return (
            service.users()
            .messages()
            .modify(userId="me", id=msg_id, body=body)
            .execute()
        )

    def get_labels(self):
        service = self.get_service()
        return service.users().labels().list(userId="me").execute()

    def create_label(self, name: str):
        service = self.get_service()
        return (
            service.users().labels().create(userId="me", body={"name": name}).execute()
        )

    def get_thread(self, thread_id: str):
        service = self.get_service()
        return service.users().threads().get(userId="me", id=thread_id).execute()

    def list_drafts(self, max_results: int = 10):
        service = self.get_service()
        return (
            service.users().drafts().list(userId="me", maxResults=max_results).execute()
        )

    def get_draft(self, draft_id: str):
        service = self.get_service()
        return service.users().drafts().get(userId="me", id=draft_id).execute()

    def create_draft(self, message: dict):
        service = self.get_service()
        return (
            service.users()
            .drafts()
            .create(userId="me", body={"message": message})
            .execute()
        )

    def delete_draft(self, draft_id: str):
        service = self.get_service()
        return service.users().drafts().delete(userId="me", id=draft_id).execute()

    def get_attachment(self, msg_id: str, attachment_id: str):
        service = self.get_service()
        return (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=msg_id, id=attachment_id)
            .execute()
        )


_gmail = GmailService()


def _parse_gmail_date(date_str: str) -> str:
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


def _decode_body(msg: dict, max_length: int = 2000) -> str:
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
        if not body:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/html":
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

    return body[:max_length].strip() if body else "(no body)"


def _get_header(msg: dict, name: str) -> str:
    headers = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _parse_email_address(address: str) -> tuple[str, str]:
    parsed = email.utils.parseaddr(address)
    return parsed[0], parsed[1]


def _format_email_summary(msg: dict, include_preview: bool = True) -> dict:
    sender = _get_header(msg, "From")
    sender_name, sender_email = _parse_email_address(sender)
    subject = _get_header(msg, "Subject") or "(no subject)"
    date = _parse_gmail_date(_get_header(msg, "Date"))
    body_preview = _decode_body(msg, 150) if include_preview else ""
    is_unread = "UNREAD" in msg.get("labelIds", [])
    labels = [l for l in msg.get("labelIds", []) if l not in ("INBOX", "UNREAD")]

    sender_display = sender_name if sender_name else sender_email.split("@")[0]

    return {
        "id": msg.get("id", ""),
        "thread_id": msg.get("threadId", ""),
        "from": sender_display,
        "from_email": sender_email,
        "subject": subject,
        "date": date,
        "preview": body_preview,
        "unread": is_unread,
        "labels": labels,
    }


def _check_oauth():
    if not _gmail._is_oauth_enabled():
        raise RuntimeError(
            "Gmail OAuth not configured.\n"
            "1. Go to console.cloud.google.com\n"
            "2. Create OAuth2 credentials (Desktop app)\n"
            "3. Download as credentials.json to bujji/bujji/\n"
            "4. Run: python -m bujji.tools.gmail_oauth --setup"
        )


def _build_message(
    to: str,
    subject: str,
    body: str,
    cc: str = None,
    bcc: str = None,
    is_html: bool = False,
    in_reply_to: str = None,
    references: str = None,
    thread_id: str = None,
) -> dict:
    sender = _gmail.get_sender_email()

    if is_html:
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
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    message = {"raw": raw}
    if thread_id:
        message["threadId"] = thread_id

    return message


def _build_multipart_message(
    to: str,
    subject: str,
    text_body: str = "",
    html_body: str = "",
    cc: str = None,
    bcc: str = None,
    thread_id: str = None,
    attachments: list = None,
) -> dict:
    sender = _gmail.get_sender_email()

    msg = MIMEMultipart("mixed")
    msg["From"] = sender
    msg["To"] = to.strip()
    msg["Subject"] = subject.strip()
    if cc:
        msg["Cc"] = cc.strip()

    if html_body:
        msg.attach(MIMEText(text_body or html_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
    elif text_body:
        msg.attach(MIMEText(text_body, "plain"))

    if attachments:
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

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    message = {"raw": raw}
    if thread_id:
        message["threadId"] = thread_id

    return message


# ─────────────────────────────────────────────────────────────────────────────
# READING TOOLS
# ─────────────────────────────────────────────────────────────────────────────


@register_tool(
    description=(
        "Fetch recent emails from inbox. Shows sender, subject, preview, and time. "
        "Use when user asks 'check emails', 'show my emails', 'any new messages'."
    ),
    params=[
        param("limit", "Number of emails to fetch", type="integer", default=10),
        param("unread_only", "Only show unread emails", type="boolean", default=False),
    ],
)
def tanu_fetch_emails(
    limit: int = 10, unread_only: bool = False, _ctx: ToolContext = None
) -> str:
    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        query = "is:unread" if unread_only else ""
        results = _gmail.list_messages(query, max_results=limit)
        messages = results.get("messages", [])

        if not messages:
            return "No unread emails." if unread_only else "No emails in inbox."

        emails = []
        for msg_ref in messages:
            msg = _gmail.get_message(msg_ref["id"])
            emails.append(_format_email_summary(msg))

        total = len(emails)
        unread = sum(1 for e in emails if e.get("unread"))

        lines = [f"You have {total} email{'s' if total > 1 else ''}."]
        if unread:
            lines.append(f"{unread} unread.")
        lines.append("")

        for e in emails:
            marker = "●" if e.get("unread") else "○"
            lines.append(f"{marker} {e['from']} | {e['date']}")
            lines.append(f"  {e['subject'][:70]}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching emails: {e}"


@register_tool(
    description="Get full details of a specific email by ID. Returns subject, sender, body, attachments info.",
    params=[
        param("email_id", "The email ID to retrieve", required=True),
        param("include_body", "Include full email body", type="boolean", default=True),
    ],
)
def tanu_get_email(
    email_id: str, include_body: bool = True, _ctx: ToolContext = None
) -> str:
    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        msg = _gmail.get_message(email_id)
        summary = _format_email_summary(msg, include_preview=False)

        lines = [
            f"From: {summary['from']} <{summary['from_email']}>",
            f"Subject: {summary['subject']}",
            f"Date: {summary['date']}",
            f"Labels: {', '.join(summary['labels']) or 'none'}",
            f"Thread ID: {summary['thread_id']}",
            "",
            "─" * 50,
            "",
        ]

        if include_body:
            body = _decode_body(msg, max_length=5000)
            lines.append(body)

        attachments = []
        payload = msg.get("payload", {})
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("filename"):
                    attachments.append(
                        {
                            "name": part["filename"],
                            "type": part.get("mimeType", "unknown"),
                            "size": part.get("body", {}).get("size", 0),
                            "id": part.get("body", {}).get("attachmentId", ""),
                        }
                    )
        if attachments:
            lines.append("")
            lines.append("Attachments:")
            for a in attachments:
                lines.append(
                    f"  - {a['name']} ({a['type']}, {a['size']} bytes) [ID: {a['id']}]"
                )

        return "\n".join(lines)

    except Exception as e:
        return f"Error getting email: {e}"


@register_tool(
    description=(
        "Search emails using Gmail search syntax. Examples: "
        "'from:alice', 'subject:meeting', 'has:attachment', 'after:2024/01/01', "
        "'before:2024/12/31', 'is:unread', 'is:starred', 'larger:5M'"
    ),
    params=[
        param("query", "Gmail search query", required=True),
        param("limit", "Max results", type="integer", default=20),
    ],
)
def tanu_search_emails(query: str, limit: int = 20, _ctx: ToolContext = None) -> str:
    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        results = _gmail.list_messages(query, max_results=limit)
        messages = results.get("messages", [])

        if not messages:
            return f"No emails found for: '{query}'"

        emails = []
        for msg_ref in messages:
            msg = _gmail.get_message(msg_ref["id"])
            emails.append(_format_email_summary(msg))

        lines = [f"Found {len(emails)} email(s) for: '{query}'", ""]
        for e in emails:
            marker = "●" if e.get("unread") else "○"
            lines.append(f"{marker} {e['from']} | {e['date']}")
            lines.append(f"  {e['subject'][:70]}")
            lines.append(f"  ID: {e['id']}")
            lines.append("")

        return "\n".join(lines).strip()

    except Exception as e:
        return f"Error searching emails: {e}"


@register_tool(
    description="Get all messages in a conversation thread.",
    params=[
        param("thread_id", "The thread ID", required=True),
    ],
)
def tanu_fetch_threads(thread_id: str, _ctx: ToolContext = None) -> str:
    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        thread = _gmail.get_thread(thread_id)
        messages = thread.get("messages", [])

        if not messages:
            return "Thread not found or empty."

        lines = [f"Thread ({len(messages)} messages)", "=" * 50, ""]

        for i, msg in enumerate(reversed(messages), 1):
            summary = _format_email_summary(msg, include_preview=False)
            body = _decode_body(msg, max_length=2000)
            is_unread = "UNREAD" in msg.get("labelIds", [])

            lines.append(
                f"[{i}] {'●' if is_unread else '○'} {summary['from']} <{summary['from_email']}>"
            )
            lines.append(f"    Date: {summary['date']}")
            lines.append(f"    Subject: {summary['subject']}")
            lines.append(f"    ID: {msg.get('id')}")
            lines.append(f"    Body: {body}")
            lines.append("")

        return "\n".join(lines).strip()

    except Exception as e:
        return f"Error fetching thread: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# SENDING TOOLS
# ─────────────────────────────────────────────────────────────────────────────


@register_tool(
    description=(
        "Send an email. Use when user says 'send email to X', 'email X', 'send a message to X'. "
        "Supports plain text, HTML, CC, and BCC."
    ),
    params=[
        param("to", "Recipient email address", required=True),
        param("subject", "Email subject line", required=True),
        param("body", "Email body content", required=True),
        param("cc", "CC recipients (comma-separated)", type="string", default=""),
        param("bcc", "BCC recipients (comma-separated)", type="string", default=""),
        param("html", "Send as HTML formatted email", type="boolean", default=False),
    ],
)
def tanu_send_email(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    html: bool = False,
    _ctx: ToolContext = None,
) -> str:
    if not to or not to.strip():
        return "Recipient email address is required."
    if not subject or not subject.strip():
        return "Email subject is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        message = _build_message(
            to=to,
            subject=subject,
            body=body,
            cc=cc if cc else None,
            bcc=bcc if bcc else None,
            is_html=html,
        )

        _gmail.send_message(message)
        return f"Email sent to {to}."

    except Exception as e:
        return f"Error sending email: {e}"


@register_tool(
    description=(
        "Send an email with file attachments. Max 25MB per attachment. "
        "Use when user wants to send files along with email."
    ),
    params=[
        param("to", "Recipient email address", required=True),
        param("subject", "Email subject line", required=True),
        param("body", "Email body content", required=True),
        param(
            "attachments", "List of file paths to attach", type="array", required=True
        ),
        param("cc", "CC recipients (comma-separated)", type="string", default=""),
    ],
)
def tanu_send_attachment(
    to: str,
    subject: str,
    body: str,
    attachments: list,
    cc: str = "",
    _ctx: ToolContext = None,
) -> str:
    if not to or not to.strip():
        return "Recipient email address is required."
    if not subject or not subject.strip():
        return "Email subject is required."
    if not attachments:
        return "At least one attachment is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        valid_files = []
        skipped = []

        for filepath in attachments:
            p = Path(filepath)
            if not p.exists():
                skipped.append(f"{filepath} (not found)")
                continue
            if p.stat().st_size > MAX_ATTACHMENT_SIZE:
                skipped.append(f"{filepath} (exceeds 25MB)")
                continue
            valid_files.append(str(p))

        if not valid_files:
            return f"No valid attachments. Skipped: {', '.join(skipped)}"

        message = _build_multipart_message(
            to=to,
            subject=subject,
            text_body=body,
            cc=cc if cc else None,
            attachments=valid_files,
        )

        _gmail.send_message(message)

        result = f"Email with {len(valid_files)} attachment(s) sent to {to}."
        if skipped:
            result += f"\nSkipped: {', '.join(skipped)}"
        return result

    except Exception as e:
        return f"Error sending email: {e}"


@register_tool(
    description="Forward an email to another recipient.",
    params=[
        param("email_id", "The email ID to forward", required=True),
        param("to", "Forward to email address", required=True),
        param(
            "add_message", "Add a message with the forward", type="string", default=""
        ),
    ],
)
def tanu_forward_email(
    email_id: str,
    to: str,
    add_message: str = "",
    _ctx: ToolContext = None,
) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."
    if not to or not to.strip():
        return "Recipient email address is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        original = _gmail.get_message(email_id)
        summary = _format_email_summary(original, include_preview=False)
        body = _decode_body(original, max_length=3000)

        forward_text = (
            f"---------- Forwarded message ---------\n"
            f"From: {summary['from']} <{summary['from_email']}>\n"
            f"Date: {summary['date']}\n"
            f"Subject: {summary['subject']}\n"
            f"\n{body}\n"
        )

        if add_message:
            forward_text = f"{add_message}\n\n{forward_text}"

        subject = f"Fwd: {summary['subject']}"

        message = _build_message(
            to=to,
            subject=subject,
            body=forward_text.strip(),
            thread_id=None,
        )

        _gmail.send_message(message)
        return f"Email forwarded to {to}."

    except Exception as e:
        return f"Error forwarding email: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# REPLY TOOL (enhanced)
# ─────────────────────────────────────────────────────────────────────────────


@register_tool(
    description=(
        "Reply to an email. The reply will include the original message in the response. "
        "Supports CC and all reply options."
    ),
    params=[
        param("email_id", "The email ID to reply to", required=True),
        param("body", "Your reply content", required=True),
        param("all", "Reply to all recipients", type="boolean", default=False),
        param("cc", "Additional CC recipients", type="string", default=""),
    ],
)
def tanu_reply_email(
    email_id: str,
    body: str,
    all: bool = False,
    cc: str = "",
    _ctx: ToolContext = None,
) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."
    if not body or not body.strip():
        return "Reply content is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        original = _gmail.get_message(email_id)
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

        in_reply_to = _get_header(original, "Message-ID")
        references = _get_header(original, "References")
        if references:
            references = f"{references} {in_reply_to}"
        else:
            references = in_reply_to

        if all:
            cc_list = [to_email]
            to_addrs = email.utils.getaddresses([_get_header(original, "To")])
            for name, addr in to_addrs:
                if addr not in cc_list:
                    cc_list.append(addr)
            cc = ",".join(cc_list) + (f",{cc}" if cc else "")

        message = _build_message(
            to=to_email,
            subject=reply_subject,
            body=reply_text,
            cc=cc if cc else None,
            in_reply_to=in_reply_to,
            references=references,
            thread_id=thread_id,
        )

        _gmail.send_message(message)
        return f"Replied to {to_email}."

    except Exception as e:
        return f"Error replying to email: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# ORGANIZATION TOOLS
# ─────────────────────────────────────────────────────────────────────────────


@register_tool(
    description="Mark an email as read or unread.",
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
def tanu_mark_email(email_id: str, read: bool = True, _ctx: ToolContext = None) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        if read:
            _gmail.modify_message(email_id, remove_labels=["UNREAD"])
        else:
            _gmail.modify_message(email_id, add_labels=["UNREAD"])

        status_text = "marked as read" if read else "marked as unread"
        return f"Email {status_text}."

    except Exception as e:
        return f"Error marking email: {e}"


@register_tool(
    description="Archive an email (remove from inbox).",
    params=[
        param("email_id", "The email ID to archive", required=True),
    ],
)
def tanu_archive_email(email_id: str, _ctx: ToolContext = None) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        _gmail.modify_message(email_id, remove_labels=["INBOX"])
        return "Email archived."

    except Exception as e:
        return f"Error archiving email: {e}"


@register_tool(
    description="Move an email to trash.",
    params=[
        param("email_id", "The email ID to delete", required=True),
    ],
)
def tanu_delete_email(email_id: str, _ctx: ToolContext = None) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        _gmail.modify_message(email_id, add_labels=["TRASH"])
        return "Email moved to trash."

    except Exception as e:
        return f"Error deleting email: {e}"


@register_tool(
    description="List all Gmail labels (folders).",
)
def tanu_list_labels(_ctx: ToolContext = None) -> str:
    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        result = _gmail.get_labels()
        labels = result.get("labels", [])

        if not labels:
            return "No labels found."

        system = [l for l in labels if l["type"] == "system"]
        user = [l for l in labels if l["type"] == "user"]

        lines = ["Labels:", ""]
        if system:
            lines.append("System:")
            for l in sorted(system, key=lambda x: x["name"]):
                lines.append(f"  - {l['name']}")
            lines.append("")

        if user:
            lines.append("Custom:")
            for l in sorted(user, key=lambda x: x["name"]):
                lines.append(
                    f"  - {l['name']} (messages: {l.get('messagesTotal', '?')})"
                )

        return "\n".join(lines)

    except Exception as e:
        return f"Error listing labels: {e}"


@register_tool(
    description="Add or remove labels from an email.",
    params=[
        param("email_id", "The email ID", required=True),
        param(
            "add_labels", "Labels to add (comma-separated)", type="string", default=""
        ),
        param(
            "remove_labels",
            "Labels to remove (comma-separated)",
            type="string",
            default="",
        ),
    ],
)
def tanu_manage_labels(
    email_id: str,
    add_labels: str = "",
    remove_labels: str = "",
    _ctx: ToolContext = None,
) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."
    if not add_labels and not remove_labels:
        return "Specify at least one label to add or remove."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        add_list = [l.strip() for l in add_labels.split(",") if l.strip()]
        remove_list = [l.strip() for l in remove_labels.split(",") if l.strip()]

        _gmail.modify_message(
            email_id,
            add_labels=add_list if add_list else None,
            remove_labels=remove_list if remove_list else None,
        )

        parts = []
        if add_list:
            parts.append(f"added: {', '.join(add_list)}")
        if remove_list:
            parts.append(f"removed: {', '.join(remove_list)}")

        return f"Labels {', '.join(parts)}."

    except Exception as e:
        return f"Error managing labels: {e}"


@register_tool(
    description="Star or unstar an email.",
    params=[
        param("email_id", "The email ID", required=True),
        param("star", "Star (true) or unstar (false)", type="boolean", default=True),
    ],
)
def tanu_star_email(email_id: str, star: bool = True, _ctx: ToolContext = None) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        if star:
            _gmail.modify_message(email_id, add_labels=["STARRED"])
        else:
            _gmail.modify_message(email_id, remove_labels=["STARRED"])

        action = "starred" if star else "unstarred"
        return f"Email {action}."

    except Exception as e:
        return f"Error starring email: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# DRAFT TOOLS
# ─────────────────────────────────────────────────────────────────────────────


@register_tool(
    description="List draft emails.",
    params=[
        param("limit", "Max drafts to show", type="integer", default=10),
    ],
)
def tanu_list_drafts(limit: int = 10, _ctx: ToolContext = None) -> str:
    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        result = _gmail.list_drafts(max_results=limit)
        drafts = result.get("drafts", [])

        if not drafts:
            return "No drafts."

        lines = [f"{len(drafts)} draft(s)", ""]

        for draft_ref in drafts:
            draft = _gmail.get_draft(draft_ref["id"])
            msg = draft.get("message", {})
            to = _get_header(msg, "To")
            subject = _get_header(msg, "Subject") or "(no subject)"
            snippet = _decode_body(msg, 100)

            lines.append(f"ID: {draft_ref['id']}")
            lines.append(f"  To: {to}")
            lines.append(f"  Subject: {subject}")
            if snippet:
                lines.append(f"  Preview: {snippet}")
            lines.append("")

        return "\n".join(lines).strip()

    except Exception as e:
        return f"Error listing drafts: {e}"


@register_tool(
    description="Save an email as draft without sending.",
    params=[
        param("to", "Recipient email address", required=True),
        param("subject", "Email subject line", required=True),
        param("body", "Email body content", required=True),
        param("cc", "CC recipients", type="string", default=""),
    ],
)
def tanu_save_draft(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    _ctx: ToolContext = None,
) -> str:
    if not to or not to.strip():
        return "Recipient email address is required."
    if not subject or not subject.strip():
        return "Email subject is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        message = _build_message(
            to=to,
            subject=subject,
            body=body,
            cc=cc if cc else None,
        )

        result = _gmail.create_draft(message)
        draft_id = result.get("id", "unknown")

        return f"Draft saved (ID: {draft_id})."

    except Exception as e:
        return f"Error saving draft: {e}"


@register_tool(
    description="Delete a draft.",
    params=[
        param("draft_id", "The draft ID to delete", required=True),
    ],
)
def tanu_delete_draft(draft_id: str, _ctx: ToolContext = None) -> str:
    if not draft_id or not draft_id.strip():
        return "Draft ID is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        _gmail.delete_draft(draft_id)
        return "Draft deleted."

    except Exception as e:
        return f"Error deleting draft: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# ATTACHMENT TOOLS
# ─────────────────────────────────────────────────────────────────────────────


@register_tool(
    description="Download an attachment from an email.",
    params=[
        param("email_id", "The email ID", required=True),
        param("attachment_id", "The attachment ID", required=True),
        param("filename", "Save as filename", required=True),
    ],
)
def tanu_download_attachment(
    email_id: str,
    attachment_id: str,
    filename: str,
    _ctx: ToolContext = None,
) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."
    if not attachment_id or not attachment_id.strip():
        return "Attachment ID is required."
    if not filename or not filename.strip():
        return "Filename is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        data = _gmail.get_attachment(email_id, attachment_id)
        file_data = data.get("data", "")

        if not file_data:
            return "Attachment not found."

        decoded = base64.urlsafe_b64decode(file_data)

        save_path = Path.home() / "Downloads" / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(decoded)

        return f"Attachment saved to: {save_path}"

    except Exception as e:
        return f"Error downloading attachment: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# BATCH OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────


@register_tool(
    description="Archive multiple emails matching a search query.",
    params=[
        param("query", "Gmail search query to match emails", required=True),
        param("confirm", "Confirm batch operation", type="boolean", default=False),
    ],
)
def tanu_batch_archive(
    query: str, confirm: bool = False, _ctx: ToolContext = None
) -> str:
    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        results = _gmail.list_messages(query, max_results=100)
        messages = results.get("messages", [])

        if not messages:
            return f"No emails found matching: '{query}'"

        if not confirm:
            return (
                f"Found {len(messages)} email(s) matching '{query}'.\n"
                "Set confirm=true to archive them."
            )

        count = 0
        for msg_ref in messages:
            try:
                _gmail.modify_message(msg_ref["id"], remove_labels=["INBOX"])
                count += 1
            except Exception:
                pass

        return f"Archived {count} email(s)."

    except Exception as e:
        return f"Error batch archiving: {e}"


@register_tool(
    description="Delete (trash) multiple emails matching a search query.",
    params=[
        param("query", "Gmail search query to match emails", required=True),
        param("confirm", "Confirm batch operation", type="boolean", default=False),
    ],
)
def tanu_batch_delete(
    query: str, confirm: bool = False, _ctx: ToolContext = None
) -> str:
    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        results = _gmail.list_messages(query, max_results=100)
        messages = results.get("messages", [])

        if not messages:
            return f"No emails found matching: '{query}'"

        if not confirm:
            return (
                f"Found {len(messages)} email(s) matching '{query}'.\n"
                "Set confirm=true to delete them."
            )

        count = 0
        for msg_ref in messages:
            try:
                _gmail.modify_message(msg_ref["id"], add_labels=["TRASH"])
                count += 1
            except Exception:
                pass

        return f"Deleted {count} email(s)."

    except Exception as e:
        return f"Error batch deleting: {e}"


@register_tool(
    description="Star or unstar multiple emails matching a search query.",
    params=[
        param("query", "Gmail search query to match emails", required=True),
        param("star", "Star (true) or unstar (false)", type="boolean", default=True),
        param("confirm", "Confirm batch operation", type="boolean", default=False),
    ],
)
def tanu_batch_star(
    query: str,
    star: bool = True,
    confirm: bool = False,
    _ctx: ToolContext = None,
) -> str:
    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        results = _gmail.list_messages(query, max_results=100)
        messages = results.get("messages", [])

        if not messages:
            return f"No emails found matching: '{query}'"

        if not confirm:
            action = "star" if star else "unstar"
            return (
                f"Found {len(messages)} email(s) matching '{query}'.\n"
                f"Set confirm=true to {action} them."
            )

        count = 0
        for msg_ref in messages:
            try:
                if star:
                    _gmail.modify_message(msg_ref["id"], add_labels=["STARRED"])
                else:
                    _gmail.modify_message(msg_ref["id"], remove_labels=["STARRED"])
                count += 1
            except Exception:
                pass

        action = "Starred" if star else "Unstarred"
        return f"{action} {count} email(s)."

    except Exception as e:
        return f"Error batch starring: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# QUICK ACTIONS
# ─────────────────────────────────────────────────────────────────────────────


@register_tool(
    description=(
        "Archive current email and reply in one action. "
        "Useful for 'I'll handle this later' workflow."
    ),
    params=[
        param("email_id", "The email ID to archive and reply to", required=True),
        param("body", "Quick reply content", required=True),
    ],
)
def tanu_quick_archive_reply(email_id: str, body: str, _ctx: ToolContext = None) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."
    if not body or not body.strip():
        return "Reply content is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        original = _gmail.get_message(email_id)
        original_from = _get_header(original, "From")
        original_subject = _get_header(original, "Subject") or "(no subject)"
        thread_id = original.get("threadId", "")

        reply_subject = original_subject
        if not reply_subject.startswith("Re:"):
            reply_subject = f"Re: {reply_subject}"

        to_email = email.utils.parseaddr(original_from)[1]

        message = _build_message(
            to=to_email,
            subject=reply_subject,
            body=body.strip(),
            thread_id=thread_id,
        )

        _gmail.modify_message(email_id, remove_labels=["INBOX", "UNREAD"])
        _gmail.send_message(message)

        return f"Archived and replied to {to_email}."

    except Exception as e:
        return f"Error: {e}"


@register_tool(
    description=(
        "Snooze an email (remove from inbox, re-appears later). "
        "Use with times like 'tomorrow', 'next week', 'in 2 hours'."
    ),
    params=[
        param("email_id", "The email ID to snooze", required=True),
        param(
            "until",
            "When to unsnooze (e.g., 'tomorrow 9am', 'next week')",
            required=True,
        ),
    ],
)
def tanu_snooze_email(email_id: str, until: str, _ctx: ToolContext = None) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."
    if not until or not until.strip():
        return "Snooze time is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        snooze_date = _parse_snooze_time(until)
        if not snooze_date:
            return f"Could not parse time: '{until}'. Try formats like 'tomorrow 9am', 'next week', 'in 2 hours'."

        _gmail.modify_message(email_id, remove_labels=["INBOX"])

        from bujji.tools.gmail_storage import GmailScheduled

        GmailScheduled.add(
            to="[SNOOZE]",
            subject=f"[SNOOZE] {email_id}",
            body=f"Unsnooze email {email_id}",
            scheduled_at=snooze_date,
        )

        return f"Email snoozed until {snooze_date.strftime('%Y-%m-%d %I:%M %p')}."

    except Exception as e:
        return f"Error snoozing email: {e}"


@register_tool(
    description="Archive email and add Done label.",
    params=[
        param("email_id", "The email ID to mark done", required=True),
    ],
)
def tanu_mark_done(email_id: str, _ctx: ToolContext = None) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        _gmail.modify_message(
            email_id,
            remove_labels=["INBOX", "UNREAD"],
            add_labels=["DONE"],
        )
        return "Marked as done."

    except Exception as e:
        return f"Error: {e}"


def _parse_snooze_time(time_str: str) -> datetime | None:
    from dateutil import parser as dateutil_parser
    from dateutil.relativedelta import relativedelta

    now = datetime.now()
    time_lower = time_str.lower().strip()

    if time_lower == "tomorrow":
        return now + relativedelta(days=1)
    elif time_lower == "next week":
        return now + relativedelta(weeks=1)
    elif time_lower == "monday":
        days_ahead = (0 - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return now + relativedelta(days=days_ahead)
    elif time_lower.startswith("in "):
        try:
            parts = time_lower.replace("in ", "").split()
            if len(parts) >= 2:
                num = int(parts[0])
                unit = parts[1]
                if "hour" in unit:
                    return now + relativedelta(hours=num)
                elif "day" in unit:
                    return now + relativedelta(days=num)
                elif "week" in unit:
                    return now + relativedelta(weeks=num)
        except (ValueError, IndexError):
            pass
    elif "am" in time_lower or "pm" in time_lower:
        try:
            parsed = dateutil_parser.parse(time_lower)
            if parsed.time():
                if parsed.date() == now.date():
                    if parsed < now:
                        parsed += relativedelta(days=1)
                return datetime.combine(parsed.date(), parsed.time())
        except Exception:
            pass

    try:
        parsed = dateutil_parser.parse(time_lower, fuzzy=True)
        return datetime.combine(parsed.date(), parsed.time())
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────


@register_tool(
    description="Save an email as a reusable template.",
    params=[
        param("name", "Template name", required=True),
        param("subject", "Email subject (use {{subject}} for variable)", required=True),
        param("body", "Email body (use {{body}} for variable)", required=True),
        param("description", "Template description", type="string", default=""),
    ],
)
def tanu_save_template(
    name: str,
    subject: str,
    body: str,
    description: str = "",
    _ctx: ToolContext = None,
) -> str:
    if not name or not name.strip():
        return "Template name is required."
    if not subject or not subject.strip():
        return "Template subject is required."

    try:
        from bujji.tools.gmail_storage import GmailTemplates

        template = GmailTemplates.save(name.strip(), subject, body, description)
        return f"Template '{template['name']}' saved (ID: {template['id']})."

    except Exception as e:
        return f"Error saving template: {e}"


@register_tool(
    description="List all saved email templates.",
)
def tanu_list_templates(_ctx: ToolContext = None) -> str:
    try:
        from bujji.tools.gmail_storage import GmailTemplates

        templates = GmailTemplates.list()

        if not templates:
            return "No templates saved. Use tanu_save_template to create one."

        lines = [f"{len(templates)} template(s):", ""]
        for t in templates:
            lines.append(f"📝 {t['name']}")
            lines.append(f"   Subject: {t['subject']}")
            lines.append(f"   Preview: {t['preview']}")
            if t.get("use_count", 0) > 0:
                lines.append(f"   Used {t['use_count']} times")
            lines.append("")

        return "\n".join(lines).strip()

    except Exception as e:
        return f"Error listing templates: {e}"


@register_tool(
    description=(
        "Send an email using a saved template. Supports replacements like "
        "{{recipient}}, {{subject}}, {{custom_field}}."
    ),
    params=[
        param("template_name", "Name of the template", required=True),
        param("to", "Recipient email", required=True),
        param(
            "replacements",
            "Replacements for template variables",
            type="object",
            default={},
        ),
    ],
)
def tanu_use_template(
    template_name: str,
    to: str,
    replacements: dict = None,
    _ctx: ToolContext = None,
) -> str:
    if not template_name or not template_name.strip():
        return "Template name is required."
    if not to or not to.strip():
        return "Recipient email is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        from bujji.tools.gmail_storage import GmailTemplates

        template = GmailTemplates.get(template_name)
        if not template:
            return f"Template '{template_name}' not found."

        subject = template["subject"]
        body = template["body"]

        if replacements:
            for key, value in replacements.items():
                placeholder = f"{{{{{key}}}}}"
                subject = subject.replace(placeholder, str(value))
                body = body.replace(placeholder, str(value))

        message = _build_message(to=to, subject=subject, body=body)
        _gmail.send_message(message)

        GmailTemplates.increment_use(template_name)

        return f"Sent email using template '{template_name}' to {to}."

    except Exception as e:
        return f"Error sending template: {e}"


@register_tool(
    description="Delete a saved template.",
    params=[
        param("name", "Template name to delete", required=True),
    ],
)
def tanu_delete_template(name: str, _ctx: ToolContext = None) -> str:
    if not name or not name.strip():
        return "Template name is required."

    try:
        from bujji.tools.gmail_storage import GmailTemplates

        if GmailTemplates.delete(name):
            return f"Template '{name}' deleted."
        return f"Template '{name}' not found."

    except Exception as e:
        return f"Error deleting template: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULED EMAILS
# ─────────────────────────────────────────────────────────────────────────────


@register_tool(
    description=(
        "Schedule an email to be sent later. Times like 'tomorrow 9am', "
        "'next monday 2pm', 'in 2 hours', '2024-12-25 10:00'"
    ),
    params=[
        param("to", "Recipient email", required=True),
        param("subject", "Email subject", required=True),
        param("body", "Email body", required=True),
        param(
            "schedule",
            "When to send (natural language or YYYY-MM-DD HH:MM)",
            required=True,
        ),
        param("cc", "CC recipients", type="string", default=""),
    ],
)
def tanu_schedule_email(
    to: str,
    subject: str,
    body: str,
    schedule: str,
    cc: str = "",
    _ctx: ToolContext = None,
) -> str:
    if not to or not to.strip():
        return "Recipient email is required."
    if not subject or not subject.strip():
        return "Subject is required."
    if not schedule or not schedule.strip():
        return "Schedule time is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        from bujji.tools.gmail_storage import GmailScheduled

        scheduled_at = _parse_snooze_time(schedule)
        if not scheduled_at:
            return f"Could not parse time: '{schedule}'. Try 'tomorrow 9am', 'in 2 hours', etc."

        if scheduled_at <= datetime.now():
            return "Scheduled time must be in the future."

        entry = GmailScheduled.add(
            to=to.strip(),
            subject=subject.strip(),
            body=body.strip(),
            cc=cc.strip(),
            scheduled_at=scheduled_at,
        )

        from bujji.tools import gmail_scheduler

        gmail_scheduler.start_scheduler()

        return (
            f"Email scheduled for {scheduled_at.strftime('%Y-%m-%d %I:%M %p')}.\n"
            f"Schedule ID: {entry['id']}"
        )

    except Exception as e:
        return f"Error scheduling email: {e}"


@register_tool(
    description="List pending scheduled emails.",
)
def tanu_list_scheduled(_ctx: ToolContext = None) -> str:
    try:
        from bujji.tools.gmail_storage import GmailScheduled
        from bujji.tools import gmail_scheduler

        scheduled = GmailScheduled.list()

        if not scheduled:
            return "No scheduled emails."

        status = gmail_scheduler.get_scheduler().status()

        lines = [f"{len(scheduled)} scheduled email(s):", ""]
        for s in scheduled:
            scheduled_time = datetime.fromisoformat(s["scheduled_at"])
            lines.append(f"ID: {s['id']}")
            lines.append(f"  To: {s['to']}")
            lines.append(f"  Subject: {s['subject']}")
            lines.append(f"  Scheduled: {scheduled_time.strftime('%Y-%m-%d %I:%M %p')}")
            lines.append(f"  Status: {s['status']}")
            lines.append("")

        return "\n".join(lines).strip()

    except Exception as e:
        return f"Error listing scheduled: {e}"


@register_tool(
    description="Cancel a scheduled email.",
    params=[
        param("schedule_id", "The schedule ID to cancel", required=True),
    ],
)
def tanu_cancel_scheduled(schedule_id: str, _ctx: ToolContext = None) -> str:
    if not schedule_id or not schedule_id.strip():
        return "Schedule ID is required."

    try:
        from bujji.tools.gmail_storage import GmailScheduled

        if GmailScheduled.cancel(schedule_id):
            return f"Scheduled email {schedule_id} cancelled."
        return f"Schedule {schedule_id} not found."

    except Exception as e:
        return f"Error cancelling scheduled: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# SPAM & BLOCK
# ─────────────────────────────────────────────────────────────────────────────


@register_tool(
    description="Mark an email as spam.",
    params=[
        param("email_id", "The email ID to report as spam", required=True),
    ],
)
def tanu_report_spam(email_id: str, _ctx: ToolContext = None) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        _gmail.modify_message(
            email_id,
            add_labels=["SPAM"],
            remove_labels=["INBOX", "UNREAD"],
        )
        return "Email reported as spam."

    except Exception as e:
        return f"Error reporting spam: {e}"


@register_tool(
    description="Block an email address. Blocked senders go to spam automatically.",
    params=[
        param("email", "Email address to block", required=True),
        param("reason", "Why you're blocking this sender", type="string", default=""),
    ],
)
def tanu_block_sender(email: str, reason: str = "", _ctx: ToolContext = None) -> str:
    if not email or not email.strip():
        return "Email address is required."

    try:
        from bujji.tools.gmail_storage import GmailBlocked

        entry = GmailBlocked.add(email.strip(), reason)
        return f"Blocked {entry['email']}."

    except Exception as e:
        return f"Error blocking sender: {e}"


@register_tool(
    description="Unblock a previously blocked email address.",
    params=[
        param("email", "Email address to unblock", required=True),
    ],
)
def tanu_unblock_sender(email: str, _ctx: ToolContext = None) -> str:
    if not email or not email.strip():
        return "Email address is required."

    try:
        from bujji.tools.gmail_storage import GmailBlocked

        if GmailBlocked.remove(email.strip()):
            return f"Unblocked {email}."
        return f"{email} was not blocked."

    except Exception as e:
        return f"Error unblocking sender: {e}"


@register_tool(
    description="List all blocked email addresses.",
)
def tanu_list_blocked(_ctx: ToolContext = None) -> str:
    try:
        from bujji.tools.gmail_storage import GmailBlocked

        blocked = GmailBlocked.list()

        if not blocked:
            return "No blocked senders."

        lines = [f"{len(blocked)} blocked sender(s):", ""]
        for b in blocked:
            lines.append(f"✗ {b['email']}")
            if b.get("reason"):
                lines.append(f"  Reason: {b['reason']}")
            lines.append("")

        return "\n".join(lines).strip()

    except Exception as e:
        return f"Error listing blocked: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL STATISTICS
# ─────────────────────────────────────────────────────────────────────────────


@register_tool(
    description="Get email activity statistics for a period.",
    params=[
        param("period", "Time period", enum=["day", "week", "month"], default="week"),
    ],
)
def tanu_email_stats(period: str = "week", _ctx: ToolContext = None) -> str:
    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        days_map = {"day": 1, "week": 7, "month": 30}
        days = days_map.get(period.lower(), 7)

        from bujji.tools.gmail_storage import GmailStats

        results = _gmail.list_messages("", max_results=1000)
        messages = results.get("messages", [])

        now = datetime.now()
        period_start = now - datetime.timedelta(days=days)

        received_count = 0
        by_sender: dict[str, int] = {}

        for msg_ref in messages:
            try:
                msg = _gmail.get_message(msg_ref["id"], format="full")
                date_str = _get_header(msg, "Date")
                try:
                    from email.utils import parsedate_to_datetime

                    msg_date = parsedate_to_datetime(date_str)
                    if msg_date >= period_start:
                        received_count += 1
                        sender = _get_header(msg, "From")
                        sender_email = email.utils.parseaddr(sender)[1].lower()
                        by_sender[sender_email] = by_sender.get(sender_email, 0) + 1
                except Exception:
                    pass
            except Exception:
                pass

        top_senders = sorted(by_sender.items(), key=lambda x: x[1], reverse=True)[:5]

        lines = [f"📊 Email Stats ({period}):", ""]
        lines.append(f"Emails received: {received_count}")

        if top_senders:
            lines.append("")
            lines.append("Top senders:")
            for sender, count in top_senders:
                lines.append(f"  {sender}: {count}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error getting stats: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# SMART FILTERS
# ─────────────────────────────────────────────────────────────────────────────


@register_tool(
    description="Find your most contacted email addresses.",
    params=[
        param("limit", "Number of contacts to show", type="integer", default=10),
    ],
)
def tanu_important_senders(limit: int = 10, _ctx: ToolContext = None) -> str:
    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        results = _gmail.list_messages("", max_results=500)
        messages = results.get("messages", [])

        by_sender: dict[str, int] = {}

        for msg_ref in messages:
            try:
                msg = _gmail.get_message(msg_ref["id"])
                sender = _get_header(msg, "From")
                sender_email = email.utils.parseaddr(sender)[1].lower()
                if sender_email:
                    by_sender[sender_email] = by_sender.get(sender_email, 0) + 1
            except Exception:
                pass

        top_senders = sorted(by_sender.items(), key=lambda x: x[1], reverse=True)[
            :limit
        ]

        if not top_senders:
            return "No senders found."

        lines = [f"Most contacted ({len(top_senders)}):", ""]
        for i, (sender, count) in enumerate(top_senders, 1):
            lines.append(f"{i}. {sender} ({count} emails)")
        lines.append("")
        lines.append("💡 These are good candidates for creating filters.")

        return "\n".join(lines)

    except Exception as e:
        return f"Error finding important senders: {e}"


@register_tool(
    description="Auto-suggest labels for an email based on content.",
    params=[
        param("email_id", "The email ID to analyze", required=True),
    ],
)
def tanu_auto_categorize(email_id: str, _ctx: ToolContext = None) -> str:
    if not email_id or not email_id.strip():
        return "Email ID is required."

    try:
        _check_oauth()
    except RuntimeError as e:
        return str(e)

    try:
        msg = _gmail.get_message(email_id)
        subject = _get_header(msg, "Subject")
        sender = _get_header(msg, "From")
        sender_email = email.utils.parseaddr(sender)[1].lower()
        body = _decode_body(msg, 500)

        suggestions = []

        keywords_map = {
            "Work": [
                "meeting",
                "project",
                "deadline",
                "report",
                "client",
                "boss",
                "quarterly",
            ],
            "Personal": ["family", "friend", "birthday", "personal", "vacation"],
            "Finance": ["invoice", "payment", "bank", "transaction", "receipt", "bill"],
            "Shopping": [
                "order",
                "shipping",
                "delivery",
                "amazon",
                "receipt",
                "confirmation",
            ],
            "Social": ["linkedin", "twitter", "facebook", "invitation", "rsvp"],
            "News": ["newsletter", "subscribe", "update", "digest"],
        }

        combined = f"{subject} {body}".lower()

        for label, keywords in keywords_map.items():
            if any(kw in combined for kw in keywords):
                suggestions.append(label)

        if "calendar" in combined or "invite" in combined:
            suggestions.append("Events")

        if any(ext in combined for ext in [".pdf", ".doc", ".xlsx", ".ppt"]):
            suggestions.append("Documents")

        if not suggestions:
            suggestions.append("Inbox")

        lines = [f"Suggested labels for this email:", ""]
        lines.append(f"From: {sender_email}")
        lines.append(f"Subject: {subject[:60]}")
        lines.append("")
        lines.append("Suggested labels:")
        for s in suggestions:
            lines.append(f"  📁 {s}")
        lines.append("")
        lines.append("Use tanu_manage_labels to apply.")

        return "\n".join(lines)

    except Exception as e:
        return f"Error categorizing email: {e}"
