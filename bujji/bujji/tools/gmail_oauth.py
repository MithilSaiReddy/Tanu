"""
bujji/tools/gmail_oauth.py

Gmail OAuth2 authentication helper.
Handles token generation and refresh.

Setup:
1. Create OAuth2 credentials at console.cloud.google.com
2. Download credentials.json to bujji/bujji/credentials.json
3. Run: python -m bujji.tools.gmail_oauth --setup
4. Follow the auth flow in browser
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]

TOKEN_FILE = Path(__file__).parent / "gmail_token.json"
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"


def get_credentials_path() -> Path | None:
    """Find credentials.json in common locations."""
    locations = [
        Path(__file__).parent / "credentials.json",
        Path.home() / ".bujji" / "credentials.json",
        Path.home() / ".config" / "bujji" / "credentials.json",
    ]
    for loc in locations:
        if loc.exists():
            return loc
    return None


def load_token() -> dict | None:
    """Load stored OAuth token."""
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return None


def save_token(token: dict) -> None:
    """Save OAuth token."""
    TOKEN_FILE.write_text(json.dumps(token, indent=2))


def get_authenticated_user():
    """Get authenticated Gmail service using stored token."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    token = load_token()

    if token:
        creds = Credentials(
            token=token.get("token"),
            refresh_token=token.get("refresh_token"),
            token_uri=token.get("token_uri"),
            client_id=token.get("client_id"),
            client_secret=token.get("client_secret"),
            scopes=token.get("scopes", SCOPES),
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_token(_creds_to_dict(creds))
        else:
            return None

    return build("gmail", "v1", credentials=creds)


def _creds_to_dict(creds) -> dict:
    """Convert Credentials to dict for storage."""
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }


def setup_oauth() -> bool:
    """Run OAuth2 flow to get initial credentials."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds_path = get_credentials_path()
    if not creds_path:
        print("ERROR: credentials.json not found!")
        print("1. Go to https://console.cloud.google.com")
        print("2. Create OAuth2 credentials (Desktop app)")
        print("3. Download as credentials.json")
        print("4. Place it in:", Path(__file__).parent)
        return False

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)

    token_dict = _creds_to_dict(creds)
    save_token(token_dict)

    print("SUCCESS! OAuth token saved to:", TOKEN_FILE)
    return True


def check_setup() -> dict:
    """Check if OAuth is properly set up."""
    creds_path = get_credentials_path()
    token = load_token()

    return {
        "credentials_found": creds_path is not None,
        "token_found": TOKEN_FILE.exists(),
        "token_valid": token is not None,
    }


def main():
    if "--setup" in sys.argv or "setup" in sys.argv:
        print("Setting up Gmail OAuth2...")
        success = setup_oauth()
        sys.exit(0 if success else 1)

    status = check_setup()
    print("Gmail OAuth Status:")
    print(f"  credentials.json: {'✓' if status['credentials_found'] else '✗'}")
    print(f"  token.json: {'✓' if status['token_found'] else '✗'}")

    if not status["credentials_found"]:
        print("\nTo set up:")
        print("1. Go to https://console.cloud.google.com")
        print("2. Create OAuth2 credentials (Desktop app)")
        print("3. Download as credentials.json to:", Path(__file__).parent)
        print("4. Run: python -m bujji.tools.gmail_oauth --setup")


if __name__ == "__main__":
    main()
