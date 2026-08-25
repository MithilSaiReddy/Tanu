# Tanu

**Desktop AI assistant** — a lightweight, always-on companion with a self-contained Python agent framework (server, tools, voice — all under `src/tanu/`) and a [Pygame](https://pyga.me/) animated character UI.

[![Docs](https://img.shields.io/badge/docs-mkdocs-blue)](https://mithilsaireddy.github.io/Tanu/)

---

## Quick Start

```bash
git clone https://github.com/MithilSaiReddy/Tanu
cd Tanu
bash setup.sh           # installs everything
python3 main.py onboard # configure your LLM provider
```

Then run `python3 main.py desk` — the server starts and the Pygame character window opens.

See [Installation](docs/content/getting-started/installation.md) for prerequisites and manual setup.

---

## Commands

| Command | Description |
|---------|-------------|
| `bash setup.sh` | One-command dev environment setup |
| `python3 main.py desk` | Launch desktop app (spawns server + Pygame UI) |
| `python3 main.py serve` | Web UI only (http://localhost:7337) |
| `python3 main.py onboard` | First-time LLM configuration |
| `python3 main.py tanu` | Voice assistant mode |
| `python3 main.py status` | Show config & status |
| `python3 main.py update` | Pull latest from GitHub (`--check` to peek, `--stash` to keep local edits) |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  python main.py desk                                │
│  ┌──────────────────────┐  ┌─────────────────────┐  │
│  │ Python Server        │  │ Pygame Client       │  │
│  │ (subprocess, :7337)  │  │ (in-process)        │  │
│  │ AgentLoop + Tools    │◄─┤ WebSocket client    │  │
│  │ + LLM                │  │ Animated character  │  │
│  │                      │  │ + chat UI           │  │
│  │  HTTP + WebSocket    │  │                     │  │
│  └──────────────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

The Python server runs as a subprocess spawned by `python main.py desk`. The Pygame client connects via WebSocket on `ws://localhost:7337/ws/chat` for real-time streaming chat.

---

## Project Structure

```
Tanu/
├── main.py                  # CLI entry points
├── src/
│   └── tanu/                # Tanu package (agent framework, server, tools,
│       └── desktop/         #   voice, and the Pygame character UI)
├── docs/                    # MkDocs documentation
├── scripts/                 # launch / packaging helpers
├── setup.sh / setup.ps1     # Dev environment setup scripts
├── config/                  # Local configuration (gitignored)
├── workspace/               # Runtime data (gitignored)
└── build/                   # Packaging output (gitignored)
```

---

## Documentation

Full MkDocs documentation at **[https://mithilsaireddy.github.io/Tanu/](https://mithilsaireddy.github.io/Tanu/)**  
Or build locally: `pip install mkdocs mkdocs-material && mkdocs serve` in `docs/`.

---

## License

MIT
