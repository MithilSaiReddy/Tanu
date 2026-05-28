# Gmail Integration

Tanu can read, search, and send Gmail emails via OAuth 2.0.

## Architecture

The Gmail integration has two parts that work together:

1. **Server-side OAuth** (`server.py` endpoints) — handles the OAuth 2.0 web flow,
   saves the token to `workspace/tanu/gmail_token.json`
2. **Tool implementation** (`src/tanu/tools/gmail.py`) — functions the LLM can call
   (`gmail_list_inbox`, `gmail_send`, `gmail_search`, `gmail_get_email`)

Both read the same token file and share the same credentials.

## Setup

### 1. Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use existing)
3. Enable the **Gmail API**
4. Configure the **OAuth consent screen** (External → add your email as a test user)
5. Create an **OAuth 2.0 Client ID** (Application type: Desktop app)
6. Add `http://localhost` as a redirect URI
7. Download the JSON credential file

### 2. Configure Credentials in Tanu

Add the credential JSON as a string to your config:

```json
{
  "tools": {
    "gmail": {
      "client_creds": "{\"installed\":{\"client_id\":\"...\",\"project_id\":\"...\",...}}"
    }
  }
}
```

The credential JSON is the full content of the file downloaded from Google Cloud
Console, serialized as a single JSON string.

### 3. Install Dependencies

```bash
pip install google-auth google-auth-oauthlib google-api-python-client
```

## OAuth Flow

The flow is handled entirely through the Tauri settings UI:

1. **Connect** — Click the gear icon (⚙) in the chat header → Gmail card → **Connect**
2. **Authorize** — Click **Open Google Auth Page** → your browser opens to Google's consent screen
3. **Authorize** — Select your Google account and grant permissions
4. **Copy Code** — After authorizing, Google redirects to `http://localhost/?code=...`
   (the page will be blank — copy the full URL from the browser's address bar)
5. **Verify** — Paste the URL (or just the code) into the input field and click **Verify**
6. **Connected** — The UI shows "Connected ✓" and the token is saved

## Token Storage

The OAuth token is saved to `workspace/tanu/gmail_token.json`. It's auto-refreshed
by the Google client library when expired. Delete it manually or click **Disconnect**
in settings to revoke access.

## Available Tool Functions

The LLM can call these functions with your permission:

| Tool | Description |
|------|-------------|
| `gmail_list_inbox` | List recent inbox messages (returns subject, sender, date, snippet) |
| `gmail_send` | Send an email (to, subject, body) |
| `gmail_search` | Search emails by query |
| `gmail_get_email` | Get full email content by ID |

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `400 invalid_request` at auth URL | `redirect_uri` missing from flow | Server now sets it explicitly — restart `desk` |
| `invalid_grant` on token exchange | PKCE code_verifier mismatch | Server caches the flow — restart `desk` |
| "Gmail tools not found" by LLM | `tool_paths` not loaded | Run via `python3 main.py desk` (uses `tanu.config`) |
| Token expired | Token auto-refresh failed | Click **Disconnect** → reconnect |
