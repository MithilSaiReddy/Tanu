# Development Setup

## Prerequisites

See [Installation](../getting-started/installation.md) for system requirements.

## Quick Dev Environment

```bash
# 1. Clone with submodules
git clone --recurse-submodules https://github.com/MithilSaiReddy/Tanu
cd Tanu

# 2. Python virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Gmail dependencies (optional)
pip install google-auth google-auth-oauthlib google-api-python-client

# 4. Build Tauri debug binary
cd src/ui
cargo tauri build  # or `cargo tauri dev` for hot-reload
```

## Running in Development

### Desktop App (with hot-reload frontend)

```bash
cd src/ui
cargo tauri dev
```

This starts the Tauri app with a dev server for the frontend. The Python server
must be started separately:

```bash
python3 main.py serve
```

Then in the Tauri app, the frontend connects to `http://localhost:7337`.

### Desktop App (release binary)

```bash
python3 main.py desk
```

### Server-only

```bash
python3 main.py serve
```

## Code Layout

```
Tanu/
├── main.py                 # Entry points
├── config/
│   └── config.json         # Local config (gitignored)
├── src/
│   ├── tanu/
│   │   ├── __init__.py
│   │   ├── config.py       # Config loader (injects tool_paths)
│   │   ├── tools/          # Custom tools
│   │   │   ├── gmail.py
│   │   │   ├── speak_tool.py
│   │   │   ├── tanu_query.py
│   │   │   └── ...
│   │   └── plugins/
│   │       └── voice/      # Voice assistant plugin
│   └── ui/                 # Tauri desktop app
│       ├── src/            # Frontend (HTML/CSS/JS)
│       ├── src-tauri/      # Rust backend
│       └── ...
├── bujji/                  # Agent framework (submodule)
│   └── bujji/
│       ├── server.py       # HTTP server
│       ├── agent.py        # Agent loop
│       ├── tools/          # Built-in tools
│       └── ...
├── workspace/              # Runtime data (gitignored)
└── docs/                   # Documentation
```

## Testing

```bash
# Python
python3 -m pytest tests/

# Rust (Tauri tests)
cd src/ui/src-tauri && cargo test

# Frontend (if tests exist)
cd src/ui && npm test
```

## Common Development Tasks

### Add a new API endpoint

1. Edit `bujji/bujji/server.py` — add method to `BujjiServer`
2. Register the route in `_routes` dict
3. Restart the server

### Modify the frontend

1. Edit `src/ui/src/index.html`, `main.js`, or `styles.css`
2. Run `cargo tauri build` to rebuild the binary
3. Or use `cargo tauri dev` for hot-reload

### Modify the Rust backend

1. Edit `src/ui/src-tauri/src/lib.rs`
2. Add `#[tauri::command]` function
3. Register in `invoke_handler`
4. Add permission in `capabilities/default.json` if needed
5. Run `cargo tauri build`

### Add a new tool

See [Tool System](../guide/tool-system.md#writing-a-new-tool).
