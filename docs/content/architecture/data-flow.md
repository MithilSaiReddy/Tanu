# Data Flow

## Chat Flow

```
User types message
       │
       ▼
main.js ──fetch(POST /api/chat)──► Python Server
       │                              │
       │                              ▼
       │                        AgentLoop.run()
       │                              │
       │                              ├─► LLM API (OpenRouter/OpenAI/Ollama)
       │                              │       │
       │                              │       ▼
       │                              │   Tool call requested?
       │                              │       │
       │                              │   ┌───┴───┐
       │                              │   YES     NO
       │                              │   │        │
       │                              │   ▼        │
       │                              │ ToolRegistry.execute()
       │                              │   │        │
       │                              │   ▼        │
       │                              │ Result→LLM │
       │                              │   │        │
       │                              │   └────────┘
       │                              │       │
       │                              ▼       ▼
       │                        Stream tokens via SSE
       │                              │
       │◄────── SSE (text/event-stream) ──────┤
       │                              │
       ▼                              │
main.js renders tokens                │
  into #messages div                  │
       │                              │
       ▼                              │
[done] event ──────────────────────────┘
```

## Mode Switching Flow

```
User presses Ctrl+Shift+T  OR  clicks float circle / close button
       │
       ▼
Rust lib.rs ──emit("mode-changed")──► Frontend
       │                              │
       │                              ▼
       │                        switchMode("chat"/"float")
       │                              │
       ▼                              ▼
set_always_on_top(true)         body.className = "mode-*"
clamp_to_screen()               msgInput.focus()/cancelStream()
```

## Gmail OAuth Flow

```
User clicks "Connect" in Settings
       │
       ▼
main.js ──fetch(GET /api/gmail/auth-url)──► Server
       │                                        │
       │                                        ▼
       │                                   flow = InstalledAppFlow(...)
       │                                   flow.redirect_uri = "..."
       │                                   auth_url = flow.authorization_url()
       │                                   _gmail_current_flow = flow  (cached)
       │                                        │
       │◄── { auth_url } ───────────────────────┘
       │
       ▼
User clicks "Open Google Auth Page"
       │
       ▼
invoke("open_url_in_browser", { url }) ──► System browser opens Google consent
       │                                        │
       │                                        ▼
       │                                   User authorizes
       │                                        │
       │                                        ▼
       │                              Google redirects to http://localhost/?code=...
       │                                        │
       ▼                                        │
User copies code from URL bar ──────────────────┘
       │
       ▼
main.js ──fetch(POST /api/gmail/auth-complete, { code })──► Server
       │                                                        │
       │                                                        ▼
       │                                                   flow.fetch_token(code)
       │                                                   token → tanu/gmail_token.json
       │                                                        │
       │◄── { ok: true } ───────────────────────────────────────┘
       │
       ▼
UI shows "Connected ✓"
```

## Window Drag & Clamp Flow

```
User pointerdown on float circle / chat header
       │
       ▼
main.js tracks mouse movement > 3px threshold
       │
       ▼
invoke("start_native_drag")
       │
       ▼
Rust: window.start_dragging()
       │
       ▼
clamp_to_screen(window):
  get current_monitor() bounds
  get window.outer_position()
  clamp x ∈ [MARGIN, monitor_width  - window_width  - MARGIN]
  clamp y ∈ [MARGIN, monitor_height - window_height - MARGIN]
  window.set_position(clamped)
```
