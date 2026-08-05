# Components

## Godot 4 Desktop Client (`src/godot/`)

The desktop client is a Godot 4 project written in GDScript.

### Autoloads

| File | Role |
|------|------|
| `autoload/ws.gd` | WebSocket client singleton — auto-reconnects, emits signals for connected/disconnected/message_received |

### Scripts

| File | Role |
|------|------|
| `scripts/main.gd` | Main scene controller — wires UI signals, handles input, processes WS messages, updates UI |
| `scripts/character.gd` | Animated character state machine — idle, listening, thinking, speaking, error states |

### Scene Structure

```
Main (Control)
├── Background (ColorRect)        — dark background
├── Character (Node2D)            — animated face (procedural drawing)
└── UI (MarginContainer)
    └── VBox
        ├── TopBar (HBoxContainer)
        │   ├── ConnectionDot     — green/red status indicator
        │   └── StatusLabel       — "Ready", "Thinking...", "Speaking..."
        ├── ResponseLabel         — RichTextLabel for streaming responses
        └── InputRow (HBoxContainer)
            ├── InputField        — LineEdit for user input
            └── SendButton        — Button to send message
```

### WebSocket Protocol

The client connects to `ws://localhost:7337/ws/chat` and exchanges JSON messages:

**Client → Server:**
```json
{"type": "chat", "message": "hello", "session_id": "godot:main"}
{"type": "status"}
{"type": "config"}
```

**Server → Client:**
```json
{"type": "state", "state": "thinking"}
{"type": "token", "content": "Hi"}
{"type": "tool_start", "name": "gmail_list_inbox", "args": {}}
{"type": "tool_done", "name": "gmail_list_inbox", "result": "..."}
{"type": "response", "content": "Here are your emails..."}
{"type": "done"}
{"type": "error", "content": "Something went wrong"}
{"type": "status", "provider": "mistral", "model": "mistral-medium-latest"}
```

---

## Python Server (`main.py` + `src/tanu/`)

### Entry Points (`main.py`)

| Command | Description |
|---------|-------------|
| `python3 main.py desk` | Launch server + Godot desktop app |
| `python3 main.py serve` | Launch server only (web UI + WebSocket) |
| `python3 main.py tanu` | Voice assistant mode |
| `python3 main.py tanu --text` | Text-only terminal assistant |
| `python3 main.py onboard` | First-time configuration wizard |

The `desk` command:
1. Starts the Python server in a subprocess via `multiprocessing.Process`
2. Launches the Godot binary
3. Cleans up both processes on Ctrl+C or exit

**Config loading**: Both `desk` and `serve` use `tanu.config.load_config()`,
which merges on-disk config over defaults and injects `tool_paths` for
custom tool discovery.

### Server (`src/tanu/server.py`)

HTTP + WebSocket server on `localhost:7337`:

| Method | Route | Purpose |
|--------|-------|---------|
| WS | `/ws/chat` | Real-time streaming chat (JSON messages) |
| GET | `/api/status` | Server health check |
| POST | `/api/chat` | Stream LLM response (SSE, legacy) |
| GET | `/api/config` | Get current config (secrets masked) |
| POST | `/api/config` | Update config (deep-merge) |
| GET | `/api/gmail/auth-url` | Generate Google OAuth URL |
| POST | `/api/gmail/auth-complete` | Exchange authorization code for token |
| GET | `/api/gmail/status` | Check if Gmail token file exists |
| GET | `/api/gmail/disconnect` | Delete Gmail token file |

### Agent Framework (`src/tanu/agent.py`)

The `AgentLoop` class orchestrates LLM calls and tool execution:

1. Takes user message + conversation history
2. Calls LLM with system prompt (includes tool schemas from `ToolRegistry`)
3. If LLM requests a tool call → executes it via `ToolRegistry`
4. Returns tool result to LLM → continues until final response
5. Streams response tokens back via WebSocket

---

## Tool System

See [Tool System](../guide/tool-system.md) for details.

### Built-in tools (`src/tanu/tools/`)

File operations, shell, web search, memory, todos, sub-agents, utilities.

### Custom tools (`src/tanu/tools/`)

| Tool | Description |
|------|-------------|
| `gmail.py` | Gmail OAuth, read inbox, send, search, get emails |
| `speak_tool.py` | Text-to-speech output |
| `tanu_query.py` | Direct agent query |
| `tanu_reminder.py` | Reminder scheduler |
| `tanu_task.py` | Task management |
