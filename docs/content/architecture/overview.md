# Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Tauri v2 Desktop App                  │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Frontend (vanilla HTML/CSS/JS)                  │   │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │   │
│  │  │ Float    │  │ Chat     │  │ Settings       │  │   │
│  │  │ Circle   │  │ Panel    │  │ Panel (Gmail)  │  │   │
│  │  └──────────┘  └──────────┘  └───────────────┘  │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Rust Backend (lib.rs)                           │   │
│  │  toggle_mode / set_chat / set_floating           │   │
│  │  start_native_drag / get_mode / open_url_in_browser│  │
│  │  clamp_to_screen()                               │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         │  JS invoke()        │  fetch()
         ▼                     ▼
┌─────────────────────────────────────────────────────────┐
│               Python Server (localhost:7337)             │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ /api/chat│  │/api/gmail│  │ /api/config           │  │
│  │ (stream) │  │(OAuth)   │  │ /api/status           │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Agent Loop (bujji)                              │   │
│  │  ToolRegistry → tools/{web,file,gmail,...}       │   │
│  │  LLM Provider (OpenRouter/OpenAI/Ollama)         │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Design Principles

1. **Lightweight** — The frontend is vanilla HTML/CSS/JS with no framework. The
   Rust backend is minimal (window management only). Heavy lifting is in Python.

2. **Always-on-top** — The window stays above all other applications. Two modes:
   a 60×60 floating orb (minimal footprint) and a 400×600 chat panel.

3. **Server-driven** — All AI logic, tool execution, and OAuth flows live in the
   Python server. The Tauri shell is just a WebView that talks to `localhost:7337`.

4. **Extensible tools** — Any Python module in `src/tanu/tools/` with a
   `@register_tool` decorator is auto-discovered and becomes available to the LLM.

## Key Paths

| Path | Purpose |
|------|---------|
| `src/ui/` | Tauri v2 project (frontend + Rust) |
| `bujji/` | Agent framework (git submodule) |
| `src/tanu/tools/` | Custom tools (Gmail, speak, query, etc.) |
| `src/tanu/config.py` | Config loader (injects `tool_paths`) |
| `main.py` | Entry points: `desk`, `serve`, `tanu`, `agent` |
| `config/` | Local configuration files (gitignored) |
| `workspace/` | Runtime data: identity files, tokens, cron |
| `docs/` | MkDocs technical documentation |
