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

The setup script handles: system dependencies, Python venv + dependencies, submodules, and config.

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

### Desktop App (with Godot editor)

```bash
# Terminal 1: start Python server
python3 main.py serve

# Terminal 2: open Godot project (has live scene editing)
godot --path src/godot
```

The Godot editor connects to `ws://localhost:7337/ws/chat`.

### Desktop App (release binary)

```bash
python3 main.py desk
```

This starts both the Python server and the Godot binary.

### Server-only

```bash
python3 main.py serve
```

## Code Layout

```
Tanu/
├── main.py                 # Entry points (desk, serve, tanu, onboard)
├── src/
│   ├── tanu/               # Tanu Python package
│   │   ├── config.py       # Config loader (injects tool_paths)
│   │   ├── tools/          # Custom tools (gmail, tasks, reminders, etc.)
│   │   └── plugins/
│   │       └── voice/      # Voice assistant plugin
│   └── godot/              # Godot 4 project
│       ├── project.godot   # Godot project config
│       ├── autoload/
│       │   └── ws.gd       # WebSocket client singleton
│       ├── scripts/
│       │   ├── main.gd     # Main scene controller
│       │   └── character.gd # Animated character state machine
│       └── scenes/
│           └── main.tscn   # Main scene layout
├── bujji/                  # Agent framework (git submodule)
├── docs/                   # MkDocs documentation
├── build.sh / build.ps1   # Build scripts (produce build/)
├── setup.sh / setup.ps1   # Dev environment setup
├── config/                 # Local config (gitignored)
├── workspace/              # Runtime data (gitignored)
└── build/                  # Build output (gitignored)
```

## Testing

```bash
# Python
python3 -m pytest tests/
```

## Common Development Tasks

### Add a new API endpoint

1. Edit `bujji/bujji/server.py` — add route to `app.router`
2. Register the handler function
3. Restart the server

### Modify the Godot client

1. Edit files in `src/godot/`
2. Run the Godot editor: `godot --path src/godot`
3. Changes to GDScript files are picked up on scene reload

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
