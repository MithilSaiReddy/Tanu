# Gmail Integration

Tanu can read, search, and send Gmail emails via OAuth 2.0. The integration
spans two layers:

| Layer | File | Role |
|-------|------|------|
| Server OAuth endpoints | `src/tanu/server.py` | Generate auth URL, exchange code → token |
| Tool implementations | `src/tanu/tools/gmail.py` | Functions the LLM calls (inbox, send, search, get) |

---

## Prerequisites

- A Google Cloud project with the **Gmail API** enabled
- Python packages: `google-auth`, `google-auth-oauthlib`, `google-api-python-client`

```bash
pip install google-auth google-auth-oauthlib google-api-python-client
```

---

## Google Cloud Console Setup

### 1. Enable the Gmail API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (or [create a new one](https://console.cloud.google.com/projectcreate))
3. Navigate to **APIs & Services → Library**
4. Search for "Gmail API" → click **Enable**

### 2. Configure the OAuth Consent Screen

1. **APIs & Services → OAuth consent screen**
2. Choose **External** (unless you're a Google Workspace user)
3. Fill in the required fields (app name, support email, developer contact)
4. **Scopes**: Add `.../auth/gmail.modify` and `.../auth/gmail.send` (or use the
   "Add scope by manual entry" option)
5. **Test users**: Add your own Gmail address (required for External publishing
   stage while the app is unverified)
6. Save and continue through the remaining steps

### 3. Create an OAuth 2.0 Client ID

1. **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. **Application type**: **Desktop app**
4. **Name**: `Tanu` (or any name you prefer)
5. **Redirect URIs**: Add `http://localhost` (this must match exactly)
6. Click **Create**
7. Download the JSON file — it looks like this:

```json
{
  "installed": {
    "client_id": "532976198320-xxxxx.apps.googleusercontent.com",
    "project_id": "your-project-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "GOCSPX-xxxxx",
    "redirect_uris": ["http://localhost"]
  }
}
```

> **Keep this file secure.** It's the equivalent of a password for your app's
> Gmail access. Never commit it to git.

---

## Configure Credentials in Tanu

Add the full credential JSON as a **string** in your config under `tools.gmail.client_creds`:

```json
{
  "tools": {
    "gmail": {
      "client_creds": "{\"installed\":{\"client_id\":\"532976198320-xxxxx.apps.googleusercontent.com\",\"project_id\":\"your-project-id\",\"auth_uri\":\"https://accounts.google.com/o/oauth2/auth\",\"token_uri\":\"https://oauth2.googleapis.com/token\",\"auth_provider_x509_cert_url\":\"https://www.googleapis.com/oauth2/v1/certs\",\"client_secret\":\"GOCSPX-xxxxx\",\"redirect_uris\":[\"http://localhost\"]}}"
    }
  }
}
```

The value is the **entire downloaded JSON** serialized as a single string (the
JSON inside the string is escaped). Both the server OAuth endpoints and the
Gmail tool functions read from this same config key.

Where to edit this:

- **Direct file**: Edit `~/.tanu/config.json` (copy from `config/config.json`)
- **Server API**: Use `POST /api/config` endpoint

---

## OAuth Flow (Step by Step)

The Gmail OAuth flow is performed via the server API endpoints:

```
  ⚙ Settings
  ┌─────────────────────────────────────┐
  │ Connections                         │
  │                                     │
  │ Gmail                    Disconnect │
  │ Connected ✓                         │
  │                                     │
  │   [Connect]  [Disconnect]           │
  └─────────────────────────────────────┘
```

### 1. Connect

Click **Connect** in the Gmail card. This calls:

```
GET /api/gmail/auth-url
```

The server:
1. Reads `tools.gmail.client_creds` from config
2. Creates a `google_auth_oauthlib.flow.InstalledAppFlow`
3. Sets `flow.redirect_uri = "http://localhost"` (from the client config)
4. Generates an authorization URL (with PKCE code challenge)
5. **Caches the flow object** in memory (`_gmail_current_flow`) — this preserves
   the `code_verifier` needed for step 4
6. Returns the URL to the frontend

```json
{ "ok": true, "auth_url": "https://accounts.google.com/o/oauth2/auth?..." }
```

### 2. Open Auth Page

Click **Open Google Auth Page**. The server returns the auth URL. Open it in
your system browser:

```bash
# The auth URL will be printed in the terminal, or you can open it manually
```

### 3. Authorize

- Select the Google account you added as a test user
- Review the permissions (`gmail.modify`, `gmail.send`)
- Click **Continue**

### 4. Copy the Code

Google redirects to:

```
http://localhost/?state=...&code=4/0AeoWuM-xxxxx&scope=...
```

The browser shows a **blank page** (nothing is listening on port 80). This is
expected. **Copy the entire URL** from the browser's address bar.

### 5. Verify (Token Exchange)

Paste the URL (or just the `code` parameter value) into the input field and
click **Verify**. The frontend calls:

```
POST /api/gmail/auth-complete
{ "code": "4/0AeoWuM-xxxxx" }
```

The server:
1. Retrieves the **cached flow object** (which holds the `code_verifier` from
   step 1)
2. Calls `flow.fetch_token(code=...)` — this sends the `code_verifier` to
   Google's token endpoint, proving this exchange belongs to the original
   authorization request
3. Saves the token to `workspace/tanu/gmail_token.json`
4. Clears the cached flow

```json
{ "ok": true }
```

The UI shows **Connected ✓**.

> **Why caching is required**: Modern Google OAuth uses **PKCE** (Proof Key for
> Code Exchange). The auth URL includes a `code_challenge` derived from a random
> `code_verifier` stored in the flow object. When exchanging the code for a
> token, the same `code_verifier` must be sent. If a new flow object were
> created for the exchange step, it would have a different verifier, causing
> `invalid_grant`. The server solves this by keeping the original flow in
> `_gmail_current_flow`.

---

## Token Lifecycle

| Event | Location | Description |
|-------|----------|-------------|
| OAuth success | `workspace/tanu/gmail_token.json` | Token saved by server's `_gmail_auth_complete` |
| Auto-refresh | (same file) | Google client library refreshes automatically when expired |
| UI status check | `GET /api/gmail/status` | Server checks if token file exists |
| Disconnect | (file deleted) | Server deletes the token file |

The token is a JSON blob containing `access_token`, `refresh_token`,
`client_id`, `client_secret`, `scopes`, and expiry info. It's auto-refreshed
by the Google library — no manual refresh needed.

---

## Available Tool Functions

Once connected, the LLM can call these tools (with your permission):

| Tool | Description |
|------|-------------|
| `gmail_list_inbox(max_results=10)` | List recent inbox messages — returns subject, sender, date, snippet |
| `gmail_send(to, subject, body)` | Send an email |
| `gmail_search(query, max_results=10)` | Search emails by query string |
| `gmail_get_email(message_id)` | Get full email content by message ID |

Usage example in chat:

```
You: what's in my inbox?
Tanu: Let me check...
      ────────────────────────────────────
      Here are your recent emails:
      1. "Meeting tomorrow" — Alice (2h ago)
      2. "Invoice attached" — Bob (5h ago)
      ...
```

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `400 invalid_request` on auth URL | `redirect_uri` was `None` (library bug) | Server now sets `flow.redirect_uri` explicitly — **restart `desk`** |
| `invalid_grant` on Verify | PKCE `code_verifier` mismatch | Server now caches the flow — **restart `desk`** |
| "Gmail tools not found" / "I don't have access" | `tool_paths` not injected — tools not discovered | Run via `python3 main.py desk` which uses `tanu.config.load_config()` |
| Server not running | Python server not running | Ensure `python3 main.py desk` is running |
| Token expired and not refreshing | Corrupted token file | Click **Disconnect** → reconnect |
| Browser shows connection refused | Nothing listening on port 80 | **Normal** — copy the code from the URL bar anyway |

---

## Internal Implementation Details

### Server OAuth Code (`src/tanu/server.py`)

```python
# Module-level cache (holds PKCE code_verifier between requests)
_gmail_current_flow = None

def _gmail_auth_url(self):
    global _gmail_current_flow
    client_config = json.loads(client_creds)
    flow = InstalledAppFlow.from_client_config(client_config, GMAIL_SCOPES)
    flow.redirect_uri = client_config["installed"]["redirect_uris"][0]  # explicit!
    auth_url, _ = flow.authorization_url(prompt="consent")
    _gmail_current_flow = flow  # ← cache for PKCE
    return {"ok": True, "auth_url": auth_url}

def _gmail_auth_complete(self, body):
    global _gmail_current_flow
    flow = _gmail_current_flow  # ← reuse cached flow (same code_verifier)
    flow.fetch_token(code=code)
    # save token...
    _gmail_current_flow = None
```

### Tool Token Loading (`src/tanu/tools/gmail.py`)

```python
def _get_credentials(cfg):
    token_path = workspace_path(cfg) / "tanu" / "gmail_token.json"
    if not token_path.exists():
        return None
    return Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)
```

### Tool Discovery (`main.py` → `tanu/config.py`)

The `desk` and `serve` commands use `tanu.config.load_config()` which
**automatically injects** the `tool_paths` entry:

```python
# src/tanu/config.py
cfg.setdefault("tool_paths", []).append({
    "path": str(get_base_dir() / "src" / "tanu" / "tools"),
    "package": "tanu.tools",
})
```

This makes `ToolRegistry` discover `src/tanu/tools/gmail.py` and register
all Gmail tool functions. Without this, the LLM would have no Gmail tools
available.
