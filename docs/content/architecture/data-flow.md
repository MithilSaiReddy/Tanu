# Data Flow

## Chat and tool flow

```text
Godot UI
  │ local WebSocket message
  ▼
aiohttp server
  │ bounded stream queue
  ▼
SessionManager ──► reuses or evicts a bounded AgentLoop session
  │
  ├─ publishes turn.started
  ▼
LLM request ──► streamed tokens ──► Godot UI
  │
  ├─ no tool requested ──► publishes turn.completed
  │
  └─ tool requested
       │
       ├─ publishes tool.started
       ├─ executes at most 3 tools concurrently
       ├─ publishes tool.completed
       └─ returns result to LLM; final response also streams
```

## Skill communication

```text
Skill or tool A
  │ publish_event("task.ready", "...")
  ▼
LocalEventBus (bounded in memory)
  ├─► runtime subscribers
  ├─► read_events() for skill or tool B
  └─► GET /api/events for local diagnostics
```

Use events for short-lived coordination, not for large documents. Event
payloads default to 4,096 characters and history defaults to 128 entries.

## Voice flow

```text
Microphone frames
  ▼
WebRTC VAD
  │ adaptive 350 ms end-of-speech threshold
  ▼
Bounded transcription queue
  │ audio callback immediately resumes
  ▼
Moonshine worker ──► transcript ──► AgentLoop
                                      │ streamed text
                                      ▼
                              sentence buffer
                                      │
                                      ▼
                             Piper chunk stream
                                      │
                                      ▼
                                   speakers
```

Moonshine processing no longer blocks the microphone callback. Piper writes
audio chunks as they are generated, and streamed sentences are not queued a
second time after the response finishes.

## Memory-pressure flow

```text
MemoryWatchdog samples parent + child RSS every 2 seconds
  ├─ below 600 MB ─► normal operation
  ├─ 600–799 MB   ─► collect garbage + evict idle sessions
  └─ 800 MB+      ─► reject new work / safely stop desktop process tree
```

Limits are configurable under `runtime.memory` in `~/.tanu/config.json`.
