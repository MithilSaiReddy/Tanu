# Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  python main.py desk                                        │
│  ┌──────────────────────┐  ┌──────────────────────────────┐ │
│  │ Python Server        │  │ Godot 4 Client               │ │
│  │ (subprocess, :7337)  │  │ (subprocess)                 │ │
│  │                      │  │                              │ │
│  │ aiohttp HTTP + WS    │  │ WebSocket client (ws.gd)     │ │
│  │ /ws/chat ────────────┤◄─┤ streams tokens + tool events  │ │
│  │                      │  │                              │ │
│  │ AgentLoop + Tools    │  │ Character (character.gd)     │ │
│  │ LLM (OpenRouter/..)  │  │ idle ↔ listening ↔ thinking  │ │
│  └──────────────────────┘  └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

The Python server runs as a subprocess. The Godot client connects via
WebSocket for real-time bidirectional communication.

## Design Principles

1. **Separation of concerns** — The Python server handles all AI logic, tool
   execution, and OAuth flows. The Godot client is purely a UI layer with
   animated character rendering.

2. **WebSocket-first** — All chat communication uses WebSocket (`/ws/chat`)
   for low-latency bidirectional streaming. HTTP endpoints remain for status
   checks and Gmail OAuth.

3. **Animated character** — The Godot client draws a procedurally animated
   face that transitions between states: idle, listening, thinking, speaking.

4. **Server-driven** — All AI logic, tool execution, and OAuth flows live in
   the Python server. The Godot client connects to `ws://localhost:7337/ws/chat`.

5. **Extensible tools** — Any Python module in `src/tanu/tools/` with a
   `@register_tool` decorator is auto-discovered and becomes available to the LLM.

## Key Paths

| Path | Purpose |
|------|---------|
| `main.py` | Entry points: `desk`, `serve`, `tanu`, `agent` |
| `src/godot/` | Godot 4 project (character UI + WebSocket client) |
| `src/godot/autoload/ws.gd` | WebSocket client singleton |
| `src/godot/scripts/character.gd` | Animated character state machine |
| `src/godot/scripts/main.gd` | Scene controller (input + WS + UI) |
| `src/tanu/` | Python package: agent framework, server, tools, voice, connections |
| `build.sh / build.ps1` | Build scripts (produce build/) |
| `setup.sh / setup.ps1` | Dev environment setup scripts |
| `build/` | Godot binary output (gitignored) |
| `config/` | Local configuration files (gitignored) |
| `workspace/` | Runtime data: identity files, tokens, cron |
| `docs/` | MkDocs technical documentation |
