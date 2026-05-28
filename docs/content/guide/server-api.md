# Server API

The Python server runs on `http://localhost:7337` and exposes a REST API with
Server-Sent Events (SSE) for streaming chat responses.

## API Reference

### `GET /api/status`

Server health check.

**Response:** `200 OK`
```json
{ "ok": true, "version": "0.1.0" }
```

### `POST /api/chat`

Send a message and receive a streaming response.

**Request:**
```json
{
  "message": "What's in my inbox?",
  "session_id": "tanu-desktop",
  "stream": true
}
```

**Response:** `200 OK` with SSE stream (`text/event-stream`)

```
data: {"type":"token","content":"Let"}

data: {"type":"token","content":" me"}

data: {"type":"token","content":" check..."}

data: {"type":"done","content":"Let me check your inbox..."}
```

Event types:

| Type | Description |
|------|-------------|
| `token` | A streamed text token (append to message) |
| `done` | Stream complete; `content` has final text |
| `error` | An error occurred |
| `tool_start` | Tool execution started (`name` field) |
| `tool_done` | Tool execution finished |

### `GET /api/config`

Get the current server configuration (secrets masked).

**Response:** `200 OK`
```json
{
  "ok": true,
  "config": {
    "providers": {
      "openrouter": { "api_key": "sk-or-abcd…" }
    },
    "tools": { ... }
  }
}
```

### `POST /api/config`

Update configuration values (deep-merge).

**Request:**
```json
{ "tools": { "gmail": { "client_creds": "{\"installed\":{...}}" } } }
```

**Response:** `200 OK`
```json
{ "ok": true }
```

### Gmail Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/gmail/auth-url` | Start OAuth — returns `auth_url` |
| POST | `/api/gmail/auth-complete` | Exchange authorization code for token |
| GET | `/api/gmail/status` | Check if token exists |
| GET | `/api/gmail/disconnect` | Delete saved token |

See [Gmail Integration](gmail-integration.md) for details.

## SSE Streaming Details

The chat endpoint uses `Transfer-Encoding: chunked` with SSE formatting.
Each line starts with `data: ` followed by a JSON object.

The frontend reads the stream using the Fetch API:

```javascript
const resp = await fetch(`${SERVER_URL}/api/chat`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message, session_id }),
});
const reader = resp.body.getReader();
// ... read chunks, split on \n, parse data: JSON ...
```
