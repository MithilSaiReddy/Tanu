# Tanu

**Desktop AI assistant** — a lightweight, always-on companion powered by the [bujji](https://github.com/anomalyco/bujji) agent framework and wrapped in a [Tauri v2](https://v2.tauri.app) desktop window.

[![Docs](https://img.shields.io/badge/docs-mkdocs-blue)](https://mithilsaireddy.github.io/Tanu/)

---

## Quick Start

```bash
git clone --recurse-submodules https://github.com/MithilSaiReddy/Tanu
cd Tanu
bash setup.sh           # installs everything
bash build.sh           # builds the desktop app binary
python3 main.py onboard # configure your LLM provider
```

Then run `python3 main.py desk` — the floating orb appears. Click it to open chat, press Ctrl+Shift+T to toggle.

See [Installation](docs/content/getting-started/installation.md) for prerequisites and manual setup.

---

## Commands

| Command | Description |
|---------|-------------|
| `bash setup.sh` | One-command dev environment setup |
| `bash build.sh` | Build Tauri desktop binary into `build/` |
| `python3 main.py desk` | Launch desktop app (spawns server + Tauri) |
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
│  │ Python Server        │  │ Tauri Desktop       │  │
│  │ (subprocess, :7337)  │  │ (subprocess)        │  │
│  │ AgentLoop + Tools    │◄─┤ Rust backend        │  │
│  │ + LLM                │  │ spawns & manages    │  │
│  └──────────┬───────────┘  │ window + tray +     │  │
│             │ fetch/SSE    │ hotkey              │  │
│             ▼              └─────────────────────┘  │
│  ┌──────────────────────┐                            │
│  │ Vanilla JS Frontend  │                            │
│  │ (HTML/CSS/JS)        │                            │
│  └──────────────────────┘                            │
└─────────────────────────────────────────────────────┘
```

The Python server runs as a subprocess spawned by `python main.py desk`. The Tauri Rust backend also spawns a server subprocess when launched directly. The frontend communicates with the server over HTTP/SSE on `localhost:7337`.

---

## Project Structure

```
Tanu/
├── main.py                  # CLI entry points
├── src/
│   ├── tanu/                # Tanu Python package (config, tools, plugins)
│   └── ui/                  # Tauri v2 desktop app (frontend + Rust)
├── bujji/                   # Agent framework (git submodule)
├── docs/                    # MkDocs documentation
├── build.sh / build.ps1    # Build scripts (produce build/)
├── setup.sh / setup.ps1    # Dev environment setup scripts
├── config/                  # Local configuration (gitignored)
├── workspace/               # Runtime data (gitignored)
└── build/                   # Tauri binary output (gitignored)
```

---

## Documentation

Full MkDocs documentation at **[https://mithilsaireddy.github.io/Tanu/](https://mithilsaireddy.github.io/Tanu/)**  
Or build locally: `pip install mkdocs mkdocs-material && mkdocs serve` in `docs/`.

---

## License

MIT
