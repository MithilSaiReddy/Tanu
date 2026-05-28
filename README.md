# Tanu

**Floating desktop AI assistant** — a lightweight, always-on companion powered by
the [bujji](https://github.com/anomalyco/bujji) agent framework and wrapped in a
[Tauri v2](https://v2.tauri.app) desktop window.

[![Docs](https://img.shields.io/badge/docs-mkdocs-blue)](https://mithilsaireddy.github.io/Tanu/)

---

## Features

- **Dual-mode window** — compact 60×60 floating orb ⇄ 400×600 chat panel
- **Always-on-top** — stays visible over all apps, toggle with Ctrl+Shift+T
- **Native drag** — OS-level window movement, auto-clamped to screen bounds
- **Position memory** — remembers window position per mode across restarts
- **Streaming responses** — real-time token-by-token LLM output via SSE
- **Tool system** — web search, file ops, shell, Gmail, todos, and more
- **Gmail integration** — OAuth2 flow, read inbox, search, send emails
- **LLM agnostic** — works with OpenAI, OpenRouter, Ollama, Anthropic, Mistral
- **Hotkey** — Ctrl+Shift+T toggles between float and chat mode

---

## Quick Start

### Prerequisites

- **Python** ≥ 3.10
- **Rust** ≥ 1.77 — [rustup](https://rustup.rs)
- **Tauri CLI** — `cargo install tauri-cli --version "^2"`
- Platform dependencies — see [Installation](docs/content/getting-started/installation.md) for your OS

### Setup

```bash
git clone --recurse-submodules https://github.com/MithilSaiReddy/Tanu
cd Tanu

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cd src/ui
cargo tauri build
cd ../..
```

### Run

```bash
python3 main.py desk
```

The floating orb appears. Click it to open chat, press Ctrl+Shift+T to toggle.

### Gmail

```bash
pip install google-auth google-auth-oauthlib google-api-python-client
```

See the [Gmail setup guide](docs/content/guide/gmail-integration.md) for OAuth
configuration.

---

## Commands

| Command | Description |
|---------|-------------|
| `python3 main.py desk` | Launch desktop app (server + Tauri) |
| `python3 main.py serve` | Web UI only (http://localhost:7337) |
| `python3 main.py tanu` | Voice assistant mode |
| `python3 main.py agent` | Terminal chat |
| `python3 main.py onboard` | First-time configuration wizard |
| `python3 main.py status` | Show current config & status |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│             Tauri v2 Desktop App            │
│  ┌───────────────────────────────────────┐  │
│  │ Frontend (vanilla HTML/CSS/JS)       │  │
│  │ invoke() ←→ Rust backend (lib.rs)    │  │
│  └───────────────────────────────────────┘  │
└─────────────────────┬───────────────────────┘
                      │ fetch()
                      ▼
┌─────────────────────────────────────────────┐
│          Python Server (localhost:7337)      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ /api/chat │  │/api/gmail│  │ API cfg  │  │
│  │ (SSE)    │  │ (OAuth)  │  │ routes   │  │
│  └──────────┘  └──────────┘  └──────────┘  │
│  ┌───────────────────────────────────────┐  │
│  │ AgentLoop + ToolRegistry              │  │
│  │ LLM (OpenRouter/OpenAI/Ollama)        │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

The Tauri shell is thin — all AI logic, tools, and OAuth live in the Python
server. The WebView is just a client that calls `localhost:7337`.

---

## Project Structure

```
Tanu/
├── main.py                     # CLI entry points
├── src/
│   ├── tanu/
│   │   ├── config.py           # Config loader (injects tool_paths)
│   │   ├── tools/              # Custom tools
│   │   │   ├── gmail.py        # Gmail OAuth + inbox/send/search
│   │   │   ├── speak_tool.py   # Text-to-speech
│   │   │   ├── tanu_query.py   # Direct agent query
│   │   │   └── ...
│   │   └── plugins/voice/      # Voice assistant
│   └── ui/                     # Tauri desktop app
│       ├── src/                # Frontend (HTML/CSS/JS)
│       └── src-tauri/          # Rust backend (lib.rs)
├── bujji/                      # Agent framework (submodule)
├── docs/                       # MkDocs documentation
├── workspace/                  # Runtime data (gitignored)
├── config/                     # Local config (gitignored)
└── .github/workflows/          # CI/CD
```

---

## Documentation

Full MkDocs documentation is available at:
**https://mithilsaireddy.github.io/Tanu/**

Or build locally:

```bash
cd docs
source ../venv/bin/activate
pip install mkdocs mkdocs-material
mkdocs serve
```

---

## Gmail Integration

Tanu supports full Gmail access via OAuth 2.0:

1. Enable Gmail API in [Google Cloud Console](https://console.cloud.google.com/)
2. Create a **Desktop app** OAuth client with `http://localhost` redirect URI
3. Add the credential JSON to `~/.bujji/config.json` under `tools.gmail.client_creds`
4. In the app: gear icon → Gmail → **Connect** → **Open Google Auth Page**
5. Authorize → copy code from URL bar → **Verify**

The LLM can then read inbox, search, send, and get emails. See the
[full guide](docs/content/guide/gmail-integration.md) for details.

---

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make changes (see [Building](docs/content/development/building.md))
4. Submit a PR

See [Contributing](docs/content/development/contributing.md) for details.

---

## License

MIT
