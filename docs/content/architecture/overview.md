# Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  python main.py desk                                        │
│  ┌──────────────────────┐  ┌──────────────────────────────┐ │
│  │ Python Server        │  │ Pygame Client                │ │
│  │ (subprocess, :7337)  │  │ (in-process)                 │ │
│  │                      │  │                              │ │
│  │ aiohttp HTTP + WS    │  │ WebSocket client             │ │
│  │ /ws/chat ────────────┤◄─┤ streams tokens + tool events  │ │
│  │                      │  │                              │ │
│  │ AgentLoop + Tools    │  │ Character                    │ │
│  │ LLM (OpenRouter/..)  │  │ idle ↔ listening ↔ thinking  │ │
│  └──────────────────────┘  └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

The Python server runs as a subprocess. The Pygame client connects via
WebSocket for real-time bidirectional communication.

## Design Principles

1. **Separation of concerns** — The Python server handles all AI logic, tool
   execution, and OAuth flows. The desktop client is purely a UI layer with
   animated character rendering.

2. **WebSocket-first** — All chat communication uses WebSocket (`/ws/chat`)
   for low-latency bidirectional streaming. HTTP endpoints remain for status
   checks and Gmail OAuth.

3. **Animated character** — The Pygame client draws a procedurally animated
   face that transitions between states: idle, listening, thinking, speaking.

4. **Server-driven** — All AI logic, tool execution, and OAuth flows live in
   the Python server. The client connects to `ws://localhost:7337/ws/chat`.

5. **Extensible tools** — Any Python module in `src/tanu/tools/` with a
   `@register_tool` decorator is auto-discovered and becomes available to the LLM.

## Key Paths

| Path | Purpose |
|------|---------|
| `main.py` | Entry points: `desk`, `serve`, `tanu`, `agent` |
| `src/tanu/desktop/` | Pygame client (character UI + WebSocket client) |
| `src/tanu/desktop/ws_client.py` | WebSocket client thread (auto-reconnect) |
| `src/tanu/desktop/character.py` | Animated character state machine |
| `src/tanu/desktop/app.py` | Main UI loop (input + WS + chat widgets) |
| `src/tanu/` | Python package: agent framework, server, tools, voice, connections |
| `setup.sh / setup.ps1` | Dev environment setup scripts |
| `config/` | Local configuration files (gitignored) |
| `workspace/` | Runtime data: identity files, tokens, cron |
| `docs/` | MkDocs technical documentation |
