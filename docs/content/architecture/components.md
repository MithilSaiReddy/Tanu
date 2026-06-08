# Components

## Tauri Desktop App (`src/ui/`)

The desktop app is a Tauri v2 project with two layers:

### Rust Layer (`src-tauri/src/lib.rs`)

The Rust backend manages the native window. Key commands exposed via `invoke()`:

| Command | Description |
|---------|-------------|
| `toggle_mode` | Switch between float (60×60) and chat (400×600) |
| `set_chat` | Resize & reposition to chat mode |
| `set_floating` | Resize & reposition to float mode |
| `start_native_drag` | Begin OS-level window drag, then clamp position to screen bounds |
| `get_mode` | Returns current mode ("chat" or "floating") |
| `open_url_in_browser` | Opens a URL in the system browser via `tauri-plugin-opener` |

**Position persistence** is handled via `Mutex<Option<(i32, i32)>>` per mode,
stored in Tauri's `AppState`. Each mode remembers its last position across
switches.

**Window clamping** (`clamp_to_screen()` — line 31 of `lib.rs`) ensures the
window never goes off-screen by checking `current_monitor()` bounds and pinning
the window position ≥ 10px inside the monitor edges. Called after every drag and
mode switch.

**Always-on-top** (`set_always_on_top(true)` — line 40, 82 of `lib.rs`) is
called explicitly on every mode switch, not just at startup. This prevents
window managers from dropping the always-on-top flag.

**Server sidecar**: In `.setup()`, Rust spawns the Python server as a Tauri sidecar
(`tauri-plugin-shell`). It polls `http://localhost:7337/api/status` every 500ms
and shows the window once the server is ready. On quit, the sidecar process is killed.

The sidecar binary (`binaries/tanu-{target-triple}`) is built with PyInstaller
from `scripts/build_server.py` and bundled via `externalBin` in `tauri.conf.json`.

Plugins:
- `tauri-plugin-opener` — opens Gmail auth URLs in the system browser
- `tauri-plugin-global-shortcut` — registers Ctrl+Shift+T hotkey
- `tauri-plugin-shell` — spawns and manages the Python server sidecar

### Frontend Layer (`src/`)

Vanilla HTML/CSS/JS — no framework. Files:

| File | Role |
|------|------|
| `index.html` | Single-page shell with float circle, chat panel, settings panel |
| `main.js` | All logic: mode switching, drag handlers, SSE chat stream, Gmail OAuth UI |
| `styles.css` | Float/chat mode styling, animations, settings panel, connector cards |
| `assets/1.svg` | Logo used in both the float circle and chat header |

Communication:
- **`invoke()`** via `window.__TAURI__.core` for native operations (mode, drag, URL open)
- **`fetch()`** to `http://localhost:7337` for all server operations (chat stream, status, Gmail OAuth)

### Gmail OAuth UI Flow

The settings panel (gear icon in chat header) contains the Gmail connector card:

1. **Connect** → `GET /api/gmail/auth-url` → gets auth URL from server
2. **Open Google Auth Page** → `invoke("open_url_in_browser", { url })` → system browser opens
3. User authorizes → Google redirects to `http://localhost/?code=...`
4. User copies code from URL bar → pastes in input field
5. **Verify** → `POST /api/gmail/auth-complete { code }` → token saved
6. UI shows **Connected ✓**

The frontend auto-extracts the `code` parameter if the user pastes the full
redirect URL (handled by `extractCode()` in `main.js`).

---

## Python Server (`main.py` + `bujji/`)

### Entry Points (`main.py`)

| Command | Description |
|---------|-------------|
| `python3 main.py desk` | Launch server + Tauri desktop app |
| `python3 main.py serve` | Launch server only (web UI) |
| `python3 main.py tanu` | Voice assistant mode |
| `python3 main.py tanu --text` | Text-only terminal assistant |
| `python3 main.py agent` | Terminal chat with agent |
| `python3 main.py onboard` | First-time configuration wizard |

The `desk` command (line 179 of `main.py`):
1. Starts the Python server in a subprocess via `multiprocessing.Process`
2. Stops any previous `tanu` systemd unit
3. Launches the Tauri binary via `systemd-run --user --unit tanu --wait`
4. Cleans up both processes on Ctrl+C or exit

In the bundled app (built via `build.sh`), the Python server is compiled into a
standalone binary (PyInstaller) and bundled as a Tauri sidecar. The Rust backend
spawns it automatically on startup — no separate `main.py desk` needed.
The sidecar entry point is `scripts/build_server.py`.

**Config loading**: Both `desk` and `serve` use `tanu.config.load_config()`
(instead of `bujji.config.load_config()`) to ensure `tool_paths` is injected
for custom tool discovery.

### Server (`bujji/bujji/server.py`)

HTTP server on `localhost:7337` with these API routes:

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/status` | Server health check |
| POST | `/api/chat` | Stream LLM response (SSE) |
| GET | `/api/config` | Get current config (secrets masked) |
| POST | `/api/config` | Update config (deep-merge) |
| GET | `/api/gmail/auth-url` | Generate Google OAuth URL |
| POST | `/api/gmail/auth-complete` | Exchange authorization code for token |
| GET | `/api/gmail/status` | Check if Gmail token file exists |
| GET | `/api/gmail/disconnect` | Delete Gmail token file |

#### Gmail OAuth Internals

The server caches the OAuth flow object globally to preserve the PKCE
`code_verifier` between the auth URL and token exchange requests:

```python
_gmail_current_flow: Optional[object] = None
```

This solves the `invalid_grant` error that occurs when a new `InstalledAppFlow`
is created for the token exchange (which would have a different `code_verifier`).

### Agent Framework (`bujji/bujji/agent.py`)

The `AgentLoop` class orchestrates LLM calls and tool execution:

1. Takes user message + conversation history
2. Calls LLM with system prompt (includes tool schemas from `ToolRegistry`)
3. If LLM requests a tool call → executes it via `ToolRegistry`
4. Returns tool result to LLM → continues until final response
5. Streams response tokens back via SSE

The system prompt (line 108 of `agent.py`) now lists Gmail among available tools:

```
• Gmail: read inbox, search, send, get emails
```

---

## Tool System

See [Tool System](../guide/tool-system.md) for details.

### Built-in tools (`bujji/bujji/tools/`)

File operations, shell, web search, memory, todos, sub-agents, utilities.

### Custom tools (`src/tanu/tools/`)

| Tool | Description |
|------|-------------|
| `gmail.py` | Gmail OAuth, read inbox, send, search, get emails |
| `speak_tool.py` | Text-to-speech output |
| `tanu_query.py` | Direct agent query |
| `tanu_reminder.py` | Reminder scheduler |
| `tanu_task.py` | Task management |

---

## Window Manager Integration

- Uses **`systemd-run --user --unit tanu --wait`** to launch the Tauri binary
  outside the snap mount namespace, avoiding the snap glibc vs system glibc
  libpthread conflict (`__libc_pthread_init` symbol mismatch)
- The `GDK_BACKEND=x11` and `LD_LIBRARY_PATH` workarounds are no longer needed
- Before each launch, the previous `tanu` systemd unit is stopped and
  `reset-failed` is called to prevent duplicate windows
