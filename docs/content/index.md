# Tanu

**Floating desktop AI assistant** — a lightweight, always-on companion powered by the
[bujji](https://github.com/anomalyco/bujji) agent framework and wrapped in a
[Tauri v2](https://v2.tauri.app) desktop window.

|                   |                                                    |
|-------------------|----------------------------------------------------|
| **Frontend**      | Tauri v2 (Rust + vanilla HTML/CSS/JS)              |
| **Backend**       | Python — bujji server (localhost:7337)             |
| **LLM Provider**  | OpenAI / OpenRouter / Ollama / any OpenAI-compatible |
| **Voice**         | Deskbot integration (optional)                     |
| **Window modes**  | Floating orb (60×60) ↔ Chat panel (400×600)        |

## Features

- **Dual-mode window** — compact floating orb that expands into a full chat panel
- **Native drag** — moves via the window manager, clamped to screen bounds
- **Always-on-top** — stays visible over all applications (toggle via Ctrl+Shift+T)
- **Streaming responses** — real-time token-by-token LLM output
- **Tool system** — web search, file operations, shell, Gmail, todos, and more
- **Gmail integration** — OAuth2 flow, read inbox, search, send emails
- **Hotkey** — Ctrl+Shift+T toggles between floating orb and chat panel
- **Position memory** — remembers where you placed the window in each mode

## Quick Links

- [Installation](getting-started/installation.md)
- [Configuration](getting-started/configuration.md)
- [Quick Start](getting-started/quickstart.md)
- [Architecture Overview](architecture/overview.md)
