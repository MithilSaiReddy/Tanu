# Tanu

**Desktop AI assistant** — a lightweight, always-on companion powered by the [bujji](https://github.com/anomalyco/bujji) agent framework with a [Godot 4](https://godotengine.org) animated character UI.

[![Docs](https://img.shields.io/badge/docs-mkdocs-blue)](https://mithilsaireddy.github.io/Tanu/)

---

## Quick Start

```bash
git clone --recurse-submodules https://github.com/MithilSaiReddy/Tanu
cd Tanu
bash setup.sh           # installs everything
bash build.sh           # exports the Godot desktop app
python3 main.py onboard # configure your LLM provider
```

Then run `python3 main.py desk` — the server starts and the Godot character window opens.

See [Installation](docs/content/getting-started/installation.md) for prerequisites and manual setup.

---

## Commands

| Command | Description |
|---------|-------------|
| `bash setup.sh` | One-command dev environment setup |
| `bash build.sh` | Export Godot desktop binary into `build/` |
| `python3 main.py desk` | Launch desktop app (spawns server + Godot) |
| `python3 main.py serve` | Web UI only (http://localhost:7337) |
| `python3 main.py onboard` | First-time LLM configuration |
| `python3 main.py tanu` | Voice assistant mode |
| `python3 main.py status` | Show config & status |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  python main.py desk                                │
│  ┌──────────────────────┐  ┌─────────────────────┐  │
│  │ Python Server        │  │ Godot 4 Client      │  │
│  │ (subprocess, :7337)  │  │ (subprocess)        │  │
│  │ AgentLoop + Tools    │◄─┤ WebSocket client    │  │
│  │ + LLM                │  │ Animated character  │  │
│  │                      │  │ + chat UI           │  │
│  │  HTTP + WebSocket    │  │                     │  │
│  └──────────────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

The Python server runs as a subprocess spawned by `python main.py desk`. The Godot client connects via WebSocket on `ws://localhost:7337/ws/chat` for real-time streaming chat.

---

## Project Structure

```
Tanu/
├── main.py                  # CLI entry points
├── src/
│   ├── tanu/                # Tanu Python package (config, tools, plugins)
│   └── godot/               # Godot 4 project (character UI + WebSocket client)
├── bujji/                   # Agent framework (git submodule)
├── docs/                    # MkDocs documentation
├── build.sh / build.ps1    # Build scripts (produce build/)
├── setup.sh / setup.ps1    # Dev environment setup scripts
├── config/                  # Local configuration (gitignored)
├── workspace/               # Runtime data (gitignored)
└── build/                   # Godot binary output (gitignored)
```

---

## Documentation

Full MkDocs documentation at **[https://mithilsaireddy.github.io/Tanu/](https://mithilsaireddy.github.io/Tanu/)**  
Or build locally: `pip install mkdocs mkdocs-material && mkdocs serve` in `docs/`.

---

## License

MIT
