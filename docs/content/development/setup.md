# Development Setup

## Prerequisites

See [Installation](../getting-started/installation.md) for system requirements.

## Quick Dev Environment

### One-Command Setup (Recommended)

```bash
git clone --recurse-submodules https://github.com/MithilSaiReddy/Tanu
cd Tanu
bash setup.sh
```

Or on Windows PowerShell:

```powershell
git clone --recurse-submodules https://github.com/MithilSaiReddy/Tanu
cd Tanu
.\setup.ps1
```

The setup script handles: system dependencies, Rust + Tauri CLI, Python venv + dependencies, submodules, and config.

### Manual Setup

```bash
git clone --recurse-submodules https://github.com/MithilSaiReddy/Tanu
cd Tanu

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Gmail dependencies (optional)
pip install google-auth google-auth-oauthlib google-api-python-client
```

## Running in Development

### Desktop App (with hot-reload frontend)

```bash
# Terminal 1: start Python server
python3 main.py serve

# Terminal 2: start Tauri with hot-reload
cd src/ui
cargo tauri dev
```

The Tauri app connects to `http://localhost:7337`.

### Desktop App (release binary)

```bash
python3 main.py desk
```

This starts both the Python server and the Tauri binary.

### Server-only

```bash
python3 main.py serve
```

## Code Layout

```
Tanu/
├── main.py                 # Entry points (desk, serve, tanu, agent, onboard)
├── scripts/
│   └── build_server.py     # PyInstaller entry point for server sidecar
├── src/
│   ├── tanu/               # Tanu Python package
│   │   ├── config.py       # Config loader (injects tool_paths)
│   │   ├── tools/          # Custom tools (gmail, tasks, reminders, etc.)
│   │   └── plugins/
│   │       └── voice/      # Voice assistant plugin
│   └── ui/                 # Tauri v2 desktop app
│       ├── src/            # Frontend (HTML/CSS/JS)
│       └── src-tauri/      # Rust backend (lib.rs)
├── bujji/                  # Agent framework (git submodule)
├── docs/                   # MkDocs documentation
├── build.sh / build.ps1   # Build scripts (produce binary/)
├── setup.sh / setup.ps1   # Dev environment setup
├── config/                 # Local config (gitignored)
├── workspace/              # Runtime data (gitignored)
└── binary/                 # Build output (gitignored)
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

### Build and preview documentation

```bash
cd docs
source ../venv/bin/activate
pip install mkdocs mkdocs-material
mkdocs serve
```

Open `http://localhost:8000` to preview. The `docs/site/` output directory is
gitignored. To deploy to GitHub Pages, push to `main` and use the GitHub
Actions workflow (see [Contributing](../development/contributing.md#deploying-documentation)).
