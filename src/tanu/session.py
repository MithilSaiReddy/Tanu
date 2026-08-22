"""
tanu/session.py  —  v2  (NEW)

SessionManager — keeps one AgentLoop alive per user/channel.

Problem with v1
───────────────
The Telegram handler called `AgentLoop(cfg)` on every single message.
That means:
  • New LLMProvider object every time (no warm state)
  • Skills re-read from disk on each message even if unchanged
  • "History" was just a list passed around by the caller — easy to lose

SessionManager fixes all of this by mapping a session_id → AgentLoop
and keeping those objects alive for the lifetime of the gateway process.

Usage
─────
mgr = SessionManager(cfg)

# In Telegram handler:
agent = mgr.get("telegram:123456789")   # created once, reused forever
result = agent.run(text, history=mgr.history("telegram:123456789"))
mgr.append("telegram:123456789", "user", text)
mgr.append("telegram:123456789", "assistant", result)
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from tanu.agent import AgentLoop
from tanu.runtime import runtime_from_config

class SessionManager:
    """
    Thread-safe registry of AgentLoop instances keyed by session_id.

    session_id convention:
        "cli"                   → interactive CLI
        "telegram:<chat_id>"    → one Telegram chat
        "discord:<channel_id>"  → one Discord channel
        "web:<uuid>"            → one browser tab
    """

    def __init__(self, cfg: dict):
        self.cfg      = cfg
        self._agents:  dict[str, AgentLoop]   = {}
        self._history: dict[str, list]        = {}
        self._last_used: dict[str, float]      = {}
        runtime_cfg = cfg.get("runtime", {})
        self.max_history = max(4, min(int(runtime_cfg.get("max_history_messages", 24)), 80))
        self.max_sessions = max(1, min(int(runtime_cfg.get("max_sessions", 6)), 32))
        self.idle_seconds = max(60, int(runtime_cfg.get("session_idle_seconds", 1800)))
        self.event_bus, self.memory_budget = runtime_from_config(cfg)
        self._lock = threading.RLock()

    # ── Agents ────────────────────────────────────────────────────────────

    def get(
        self,
        session_id:      str,
        send_message_fn: Optional[Callable[[str], None]] = None,
        callbacks:       Optional[dict]                  = None,
    ) -> AgentLoop:
        """Return the AgentLoop for this session, creating it if needed.
        Always updates callbacks so each request gets fresh ones."""
        with self._lock:
            self._evict_idle_locked(exclude=session_id)
            if self.memory_budget.pressure() == "soft":
                self._evict_oldest_locked(exclude=session_id)
            if session_id not in self._agents:
                while len(self._agents) >= self.max_sessions:
                    self._evict_oldest_locked(exclude=session_id)
                if self.memory_budget.pressure() == "hard":
                    self.memory_budget.trim()
                    if self.memory_budget.pressure() == "hard":
                        raise MemoryError("Tanu memory hard limit reached")
                self._agents[session_id] = AgentLoop(
                    self.cfg,
                    send_message_fn = send_message_fn,
                    callbacks       = callbacks or {},
                    event_bus       = self.event_bus,
                    memory_budget   = self.memory_budget,
                )
                self.event_bus.publish("session.created", {"session_id": session_id}, source="session")
            else:
                agent = self._agents[session_id]
                if callbacks:
                    agent.callbacks = callbacks
                    agent.tools.callbacks = {
                        "on_tool_start": callbacks.get("on_tool_start"),
                        "on_tool_done":  callbacks.get("on_tool_done"),
                    }
            self._last_used[session_id] = time.monotonic()
            return self._agents[session_id]

    def update_callbacks(self, session_id: str, callbacks: dict) -> None:
        """
        Attach new callbacks to an existing session (e.g. when a new web
        request comes in for the same session_id).
        """
        with self._lock:
            if session_id in self._agents:
                self._agents[session_id].callbacks = callbacks
                self._last_used[session_id] = time.monotonic()

    def close(self, session_id: str) -> None:
        """Remove a session and its history."""
        with self._lock:
            self._agents.pop(session_id, None)
            self._history.pop(session_id, None)
            self._last_used.pop(session_id, None)
            self.event_bus.publish("session.closed", {"session_id": session_id}, source="session")

    # ── History ───────────────────────────────────────────────────────────

    def history(self, session_id: str) -> list:
        """Return a copy of the message history for this session."""
        with self._lock:
            return list(self._history.get(session_id, []))

    def append(self, session_id: str, role: str, content: str) -> None:
        """Append one message to the session history (auto-trims to MAX_HISTORY)."""
        with self._lock:
            hist = self._history.setdefault(session_id, [])
            hist.append({"role": role, "content": content})
            if len(hist) > self.max_history:
                # Keep system message if present, then trim oldest turns
                if hist and hist[0]["role"] == "system":
                    self._history[session_id] = [hist[0]] + hist[-(self.max_history - 1):]
                else:
                    self._history[session_id] = hist[-self.max_history:]
            self._last_used[session_id] = time.monotonic()

    def clear(self, session_id: str) -> None:
        """Wipe history for a session without destroying the agent."""
        with self._lock:
            self._history.pop(session_id, None)

    def sessions(self) -> list[str]:
        """Return list of active session IDs."""
        with self._lock:
            return list(self._agents)

    def _evict_idle_locked(self, exclude: str = "") -> None:
        cutoff = time.monotonic() - self.idle_seconds
        for session_id, last_used in list(self._last_used.items()):
            if session_id != exclude and last_used < cutoff:
                self._evict_locked(session_id, "idle")

    def _evict_oldest_locked(self, exclude: str = "") -> None:
        candidates = [
            (last_used, session_id)
            for session_id, last_used in self._last_used.items()
            if session_id != exclude and session_id in self._agents
        ]
        if candidates:
            _, session_id = min(candidates)
            self._evict_locked(session_id, "memory")

    def _evict_locked(self, session_id: str, reason: str) -> None:
        if self._agents.pop(session_id, None) is not None:
            self._history.pop(session_id, None)
            self._last_used.pop(session_id, None)
            self.event_bus.publish(
                "session.evicted",
                {"session_id": session_id, "reason": reason},
                source="session",
            )
