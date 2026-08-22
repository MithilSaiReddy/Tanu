# Architecture Overview

Tanu is local-first. Audio, wake-word support, speech recognition, speech
synthesis, memory, tools, skills, scheduling, and the desktop UI run on the
computer. Only the configured LLM provider and explicitly enabled connectors
such as Gmail or web search use the network.

```text
┌──────────────────────── Desktop process ─────────────────────────┐
│ Godot UI ◄──── loopback WebSocket ────► Python server            │
│     │                                      │                     │
│     └────────── 600/800 MB watchdog ───────┘                     │
└──────────────────────────────────────────────────────────────────┘
                                               │
                    ┌──────────────────────────┴──────────────────┐
                    │ Local runtime                              │
                    │ SessionManager · MemoryBudget · EventBus   │
                    └──────────────┬──────────────────────────────┘
                                   │
              ┌────────────────────┼─────────────────────┐
              ▼                    ▼                     ▼
       Agent + LLM client    Tools and skills      Voice pipeline
       bounded context       bounded events        VAD → Moonshine
       streamed responses    workspace sandbox     Piper → speakers
              │
              ▼
       Configured LLM API
       (the main AI network boundary)
```

## Component communication

`LocalEventBus` is the shared coordination layer. Agents, tools, skills, and
runtime services publish small typed events without a network broker or extra
process. Its history and payloads are bounded, so communication cannot grow
memory indefinitely.

Python tools receive the bus through `ToolContext`. Markdown-driven skills can
use the `publish_event` and `read_events` tools to hand state to another skill.
Runtime lifecycle events include `turn.started`, `turn.completed`,
`tool.started`, `tool.completed`, `skills.changed`, and session events. Recent
events are observable through `GET /api/events`.

The event bus is intentionally ephemeral. Durable user facts belong in
`USER.md` or `MEMORY.md`; durable task state belongs in its specific workspace
store.

## Memory policy

The default target is a 600 MB soft limit and an 800 MB hard limit for the
desktop process tree:

- At soft pressure, garbage collection runs and idle sessions are evicted.
- At hard pressure, new agent/tool work is refused and desktop mode shuts down
  safely instead of continuing toward an operating-system out-of-memory event.
- Sessions, histories, tool output, event history, streaming queues, voice
  queues, sub-agent iterations, and parallel tool workers are all bounded.
- Piper is loaded once and reused. Only one Moonshine transcription worker is
  active.

Actual baseline RAM varies by operating system, audio drivers, Godot renderer,
and selected speech models. The watchdog enforces the configured process-tree
limit when `psutil` can inspect all child processes.

## Design principles

1. Local by default; network connectors are explicit.
2. Bounded queues and histories instead of unbounded accumulation.
3. One in-process event bus instead of Redis, RabbitMQ, or another daemon.
4. Streaming across LLM, TTS, and WebSocket boundaries.
5. Workspace-scoped tools with clear security boundaries.

## Key paths

| Path | Purpose |
|------|---------|
| `src/tanu/runtime.py` | Local event bus, memory budget, watchdog |
| `src/tanu/agent.py` | Bounded agent/tool loop |
| `src/tanu/session.py` | Reused, capped sessions and histories |
| `src/tanu/tools/events.py` | Skill-facing local event tools |
| `src/tanu/plugins/voice/deskbot.py` | Local STT/TTS pipeline |
| `src/tanu/server.py` | Loopback HTTP/WebSocket API |
| `src/godot/` | Godot desktop UI |
