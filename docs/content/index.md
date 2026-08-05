# Tanu

**Desktop AI assistant** — a lightweight, always-on companion powered by the
a self-contained agent framework with a
[Godot 4](https://godotengine.org) animated character UI.

|                   |                                                    |
|-------------------|----------------------------------------------------|
| **Frontend**      | Godot 4 (GDScript, WebSocket client)              |
| **Backend**       | Python — aiohttp server with WebSocket endpoint    |
| **LLM Provider**  | OpenAI / OpenRouter / Ollama / any OpenAI-compatible |
| **Voice**         | Deskbot integration (optional)                     |
| **Input**         | Wake word detection (always listening)             |

## Features

- **Animated character** — procedurally drawn face with idle, listening, thinking, and speaking states
- **Streaming responses** — real-time token-by-token LLM output over WebSocket
- **Always-on-top** — stays visible over all applications
- **Tool system** — web search, file operations, shell, Gmail, todos, and more
- **Gmail integration** — OAuth2 flow, read inbox, search, send emails
- **WebSocket protocol** — low-latency bidirectional communication

## Quick Links

- [Installation](getting-started/installation.md) — system deps, setup script
- [Configuration](getting-started/configuration.md) — LLM providers, API keys
- [Quick Start](getting-started/quickstart.md) — configure, build, launch
- [Building](development/building.md) — build.sh pipeline, binary output
- [Setup](development/setup.md) — dev environment setup
- [Architecture Overview](architecture/overview.md) — server + Godot client model
