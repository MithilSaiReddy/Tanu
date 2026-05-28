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
| `start_native_drag` | Begin OS-level window drag, then clamp position |
| `get_mode` | Returns current mode ("chat" or "floating") |
| `open_url_in_browser` | Opens a URL in the system browser via `tauri-plugin-opener` |

Position persistence is handled in Rust via `Mutex<Option<(i32, i32)>>` per mode,
stored in Tauri's `AppState`.

Window clamping (`clamp_to_screen()`) ensures the window never goes off-screen
by checking `current_monitor()` bounds and pinning position ≥ 10px inside.

Plugins:
- `tauri-plugin-opener` — system browser for Gmail OAuth
- `tauri-plugin-global-shortcut` — Ctrl+Shift+T hotkey

### Frontend Layer (`src/`)

Vanilla HTML/CSS/JS — no framework. Files:

| File | Role |
|------|------|
| `index.html` | Single-page shell with float circle, chat panel, settings |
| `main.js` | All logic: mode switching, drag handlers, chat stream, Gmail OAuth UI |
| `styles.css` | Float/chat modes, animations, settings panel, connectors |
| `assets/1.svg` | Logo used in both float circle and chat header |

Communication:
- **`invoke()`** via `window.__TAURI__.core` for native operations (mode, drag, URL open)
- **`fetch()`** to `http://localhost:7337` for all server operations (chat, status, Gmail)

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

The `desk` command:
1. Starts the server in a subprocess via `multiprocessing.Process`
2. Launches the Tauri binary via `systemd-run --user --unit tanu --wait`
3. Cleans up both on exit

### Server (`bujji/bujji/server.py`)

HTTP server on `localhost:7337` with these API routes:

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/status` | Server health check |
| POST | `/api/chat` | Stream LLM response (SSE) |
| GET | `/api/config` | Get current config (masked) |
| POST | `/api/config` | Update config (deep-merge) |
| GET | `/api/gmail/auth-url` | Generate Google OAuth URL |
| POST | `/api/gmail/auth-complete` | Exchange code for token |
| GET | `/api/gmail/status` | Check if Gmail token exists |
| GET | `/api/gmail/disconnect` | Delete Gmail token |

### Agent Framework (`bujji/bujji/agent.py`)

The `AgentLoop` class orchestrates LLM calls and tool execution:

1. Takes user message + conversation history
2. Calls LLM with system prompt (includes tool schemas)
3. If LLM requests a tool call → executes it via `ToolRegistry`
4. Returns tool result to LLM → continues until final response
5. Streams response tokens back via SSE

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

## Window Manager Integration

- Uses `systemd-run --user` to escape the snap sandbox (needed when running
  from ptyxis or other snap-hosted terminals)
- The `GDK_BACKEND=x11` and `LD_LIBRARY_PATH` workarounds are no longer needed
  (the `systemd-run` approach avoids the snap glibc vs system glibc conflict)
