"""
tanu/tools/gmail.py — Gmail integration for bujji/Tanu.

Tools:
    gmail_authenticate   - Two-step OAuth setup
    gmail_send           - Send an email
    gmail_list_inbox     - List recent inbox emails
    gmail_search         - Search emails by query
    gmail_get_email      - Get full email content by ID
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from bujji.tools.base import ToolContext, param, register_tool

LOG = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

TOKEN_FILE = "tanu/gmail_token.json"


def _ensure_deps() -> str | None:
    """Check Gmail dependencies are installed. Returns error string or None."""
    try:
        import google.auth  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
        import googleapiclient  # noqa: F401
    except ImportError:
        return (
            "Gmail dependencies not installed.\n"
            "Run: pip install google-auth google-auth-oauthlib google-api-python-client\n"
            "Or:  pip install -e '.[gmail]'"
        )
    return None


def _load_token(workspace: Path) -> tuple:
    """Load credentials from workspace token file."""
    token_path = workspace / TOKEN_FILE
    if not token_path.exists():
        return None, "Gmail not authenticated. Run `gmail_authenticate` first."

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                token_path.write_text(creds.to_json())
            else:
                return None, (
                    "Gmail credentials expired and can't be refreshed. "
                    "Run `gmail_authenticate` again."
                )

        return creds, None
    except Exception as e:
        return None, f"Failed to load Gmail credentials: {e}"


def _build_service(creds):
    """Build Gmail API service from credentials."""
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds)


def _format_header(headers: list[dict], name: str, fallback: str = "?") -> str:
    for h in headers:
        if h["name"] == name:
            return h["value"]
    return fallback


def _decode_body(payload: dict) -> str:
    """Decode email body from a MIME payload."""
    import base64

    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode(errors="replace")
            elif "parts" in part:
                result = _decode_body(part)
                if result:
                    return result

    data = payload.get("body", {}).get("data", "")
    if data:
        return base64.urlsafe_b64decode(data).decode(errors="replace")
    return ""


def _get_message_summary(service, msg_id: str) -> str:
    """Get a one-line summary of a message."""
    meta = service.users().messages().get(
        userId="me", id=msg_id, format="metadata",
        metadataHeaders=["From", "Subject", "Date"],
    ).execute()

    headers = meta.get("payload", {}).get("headers", [])
    fr = _format_header(headers, "From")
    subj = _format_header(headers, "Subject", "(no subject)")
    date = _format_header(headers, "Date")
    return f"  [{msg_id[:8]}] {date} — {fr}: {subj}"


@register_tool(
    description=(
        "Authenticate with Gmail. Run without a `code` to get an auth URL, "
        "then visit the URL, grant access, and run again with the code to complete setup."
    ),
    params=[
        param("code", "Authorization code from Google (omit to get auth URL)", required=False),
    ],
)
def gmail_authenticate(code: str = "", _ctx: ToolContext = None) -> str:
    err = _ensure_deps()
    if err:
        return err

    client_creds = _ctx.cred("gmail.client_creds", required=False)
    if not client_creds:
        return (
            "Gmail client credentials not configured.\n\n"
            "1. Go to https://console.cloud.google.com/apis/credentials\n"
            "2. Create an OAuth 2.0 Client ID (Desktop application type)\n"
            "3. Download the JSON, then add it to config under:\n"
            "   tools.gmail.client_creds\n\n"
            "   In config.json:\n"
            "   {\"tools\": {\"gmail\": {\"client_creds\": \"<paste the full JSON>\"}}}\n\n"
            "   Or set it in the web UI: Settings → Tools → Gmail → client_creds"
        )

    from google_auth_oauthlib.flow import InstalledAppFlow

    try:
        client_config = json.loads(client_creds)
    except json.JSONDecodeError:
        return "Invalid JSON in tools.gmail.client_creds. Paste the entire OAuth client JSON."

    if not code:
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        auth_url, _ = flow.authorization_url(prompt="consent")
        return (
            "Step 1/2 — Authorize Gmail access\n\n"
            f"Visit this URL:\n{auth_url}\n\n"
            "After granting access, Google will show an authorization code. "
            "Copy it and run:\n\n"
            '    gmail_authenticate(code="<paste-code-here>")'
        )

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    flow.fetch_token(code=code)

    token_path = _ctx.workspace / TOKEN_FILE
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(flow.credentials.to_json())

    return (
        "Gmail authenticated successfully!\n\n"
        "You can now use:\n"
        "  - gmail_send(to, subject, body)\n"
        "  - gmail_list_inbox(max_results)\n"
        "  - gmail_search(query, max_results)\n"
        "  - gmail_get_email(email_id)"
    )


@register_tool(
    description="Send an email via Gmail.",
    params=[
        param("to", "Recipient email address"),
        param("subject", "Email subject"),
        param("body", "Email body text (plain text)"),
    ],
)
def gmail_send(to: str, subject: str, body: str, _ctx: ToolContext = None) -> str:
    err = _ensure_deps()
    if err:
        return err

    if not to or "@" not in to:
        return f"Invalid email address: {to}"

    creds, err_msg = _load_token(_ctx.workspace)
    if err_msg:
        return err_msg

    try:
        import base64
        from email.message import EmailMessage

        from googleapiclient.errors import HttpError

        service = _build_service(creds)

        message = EmailMessage()
        message.set_content(body)
        message["To"] = to
        message["Subject"] = subject

        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()

        sent = service.users().messages().send(
            userId="me", body={"raw": encoded}
        ).execute()

        return f"Email sent to {to} (id: {sent['id']})"
    except HttpError as e:
        details = e.error_details if hasattr(e, "error_details") else str(e)
        return f"Gmail API error: {details}"
    except Exception as e:
        return f"Failed to send email: {e}"


@register_tool(
    description="List recent emails in the Gmail inbox.",
    params=[
        param("max_results", "Number of emails to return (max 50)", type="integer", default=10),
    ],
)
def gmail_list_inbox(max_results: int = 10, _ctx: ToolContext = None) -> str:
    err = _ensure_deps()
    if err:
        return err

    creds, err_msg = _load_token(_ctx.workspace)
    if err_msg:
        return err_msg

    try:
        service = _build_service(creds)

        max_results = min(max_results, 50)
        results = service.users().messages().list(
            userId="me", maxResults=max_results, q="in:inbox"
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            return "Inbox is empty."

        lines = [f"Inbox ({len(messages)} email{'s' if len(messages) != 1 else ''}):"]
        for msg in messages:
            lines.append(_get_message_summary(service, msg["id"]))

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to list inbox: {e}"


@register_tool(
    description="Search Gmail emails matching a query.",
    params=[
        param("query", "Gmail search query (same as Gmail search box syntax)"),
        param("max_results", "Number of results to return (max 50)", type="integer", default=10),
    ],
)
def gmail_search(query: str, max_results: int = 10, _ctx: ToolContext = None) -> str:
    err = _ensure_deps()
    if err:
        return err

    if not query:
        return "Search query required."

    creds, err_msg = _load_token(_ctx.workspace)
    if err_msg:
        return err_msg

    try:
        service = _build_service(creds)

        max_results = min(max_results, 50)
        results = service.users().messages().list(
            userId="me", maxResults=max_results, q=query
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            return f"No emails found matching: {query}"

        lines = [f"Results for '{query}' ({len(messages)} email{'s' if len(messages) != 1 else ''}):"]
        for msg in messages:
            lines.append(_get_message_summary(service, msg["id"]))

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to search emails: {e}"


@register_tool(
    description="Get the full content of a specific Gmail email by its message ID.",
    params=[
        param("email_id", "The Gmail message ID to retrieve (shown in list/search results)"),
    ],
)
def gmail_get_email(email_id: str, _ctx: ToolContext = None) -> str:
    err = _ensure_deps()
    if err:
        return err

    if not email_id:
        return "email_id is required."

    creds, err_msg = _load_token(_ctx.workspace)
    if err_msg:
        return err_msg

    try:
        service = _build_service(creds)

        msg = service.users().messages().get(
            userId="me", id=email_id, format="full"
        ).execute()

        headers = msg.get("payload", {}).get("headers", [])
        body = _decode_body(msg.get("payload", {}))

        parts = [
            f"From: {_format_header(headers, 'From')}",
            f"To: {_format_header(headers, 'To', '(no recipients)')}",
            f"Date: {_format_header(headers, 'Date')}",
            f"Subject: {_format_header(headers, 'Subject', '(no subject)')}",
        ]

        if body:
            trimmed = body[:5000]
            parts.append(f"\n{trimmed}")
            if len(body) > 5000:
                parts.append("\n[… body truncated at 5000 chars …]")

        return "\n".join(parts)
    except Exception as e:
        return f"Failed to retrieve email: {e}"
