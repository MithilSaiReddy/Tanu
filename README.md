# Tanu

**Desktop AI assistant** — a lightweight, always-on companion with a self-contained Python agent framework (server, tools, voice — all under `src/tanu/`) and a [Godot 4](https://godotengine.org) animated character UI.

Local-first runtime: speech, memory, skills, tools, and UI stay on-device. A
bounded local event bus coordinates components, with a default 600 MB soft /
800 MB hard process-tree memory budget. Only the configured LLM and explicitly
enabled online integrations use the network.

[![Docs](https://img.shields.io/badge/docs-mkdocs-blue)](https://mithilsaireddy.github.io/Tanu/)

---

## Quick Start

```bash
git clone --branch checking-branch --single-branch https://github.com/MithilSaiReddy/Tanu
cd Tanu
python3 scripts/verify.py # zero-download source and unit checks
bash setup.sh           # installs everything
bash build.sh           # exports the Godot desktop app
python3 main.py onboard # configure your LLM provider
```

Then run `python3 main.py desk` — the server starts and the Godot character window opens.

See [Installation](docs/content/getting-started/installation.md) for prerequisites and manual setup.

Before promoting a build, follow the isolated tester checklist in
[TESTING.md](TESTING.md). It never reads or writes the tester's real Tanu
configuration. `python3 scripts/verify.py --full` also boots the local API,
checks its endpoints and verifies that the test process tree stays below the
configured 800 MB hard limit.

---

## Commands

| Command | Description |
|---------|-------------|
| `bash setup.sh` | One-command dev environment setup |
| `bash build.sh` | Export Godot desktop binary into `build/` |
| `python3 main.py desk` | Launch desktop app (spawns server + Godot) |
| `python3 main.py serve` | Local HTTP/WebSocket API (http://localhost:7337) |
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
│   ├── tanu/                # Tanu package (agent framework, server, tools, voice)
│   └── godot/               # Godot 4 project (character UI + WebSocket client)
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
