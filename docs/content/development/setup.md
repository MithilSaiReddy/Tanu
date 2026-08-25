# Development Setup

## Prerequisites

See [Installation](../getting-started/installation.md) for system requirements.

## Quick Dev Environment

### One-Command Setup (Recommended)

```bash
git clone https://github.com/MithilSaiReddy/Tanu
cd Tanu
bash setup.sh
```

Or on Windows PowerShell:

```powershell
git clone https://github.com/MithilSaiReddy/Tanu
cd Tanu
.\setup.ps1
```

The setup script handles: system dependencies, Python venv + dependencies, and config.

### Manual Setup

```bash
git clone https://github.com/MithilSaiReddy/Tanu
cd Tanu

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Gmail dependencies (optional)
pip install google-auth google-auth-oauthlib google-api-python-client
```

## Running in Development

### Desktop App

```bash
python3 main.py desk
```

This starts the Python server (subprocess) and opens the Pygame window (in-process).

### Server-only

```bash
python3 main.py serve
```

## Code Layout

```
Tanu/
├── main.py                 # Entry points (desk, serve, tanu, onboard)
├── src/
│   └── tanu/               # Tanu Python package (agent, server, tools, voice)
│       ├── config.py       # Config loader (injects tool_paths)
│       ├── server.py       # aiohttp HTTP + WebSocket server
│       ├── agent.py        # AgentLoop, Heartbeat, Cron
│       ├── tools/          # Built-in + custom tools (gmail, tasks, reminders, etc.)
│       ├── connections/    # Telegram / Discord channels
│       ├── plugins/
│       │   └── voice/      # Voice assistant plugin
│       └── desktop/        # Pygame desktop client
│           ├── app.py      # Main UI loop
│           ├── character.py # Animated character state machine
│           ├── widgets.py  # Chat widgets
│           └── ws_client.py # WebSocket client thread
├── docs/                   # MkDocs documentation
├── scripts/                # launch / packaging helpers
├── setup.sh / setup.ps1    # Dev environment setup
├── config/                 # Local config (gitignored)
├── workspace/              # Runtime data (gitignored)
└── build/                  # Packaging output (gitignored)
```

## Testing

```bash
# Python
python3 -m pytest tests/
```

## Common Development Tasks

### Add a new API endpoint

1. Edit `src/tanu/server.py` — add route to `app.router`
2. Register the handler function
3. Restart the server

### Modify the desktop client

1. Edit files in `src/tanu/desktop/`
2. Restart `python3 main.py desk` to see changes

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
