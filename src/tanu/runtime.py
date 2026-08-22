"""Bounded in-process coordination and memory controls for Tanu."""

from __future__ import annotations

import gc
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class RuntimeEvent:
    sequence: int
    topic: str
    source: str
    payload: dict
    created_at: float


class LocalEventBus:
    """Thread-safe, bounded event bus shared by agents, tools, and skills."""

    def __init__(self, max_events: int = 128, max_payload_chars: int = 4096):
        self._events = deque(maxlen=max(16, min(int(max_events), 512)))
        self._max_payload_chars = max(256, min(int(max_payload_chars), 16_384))
        self._subscribers: dict[str, list[Callable[[RuntimeEvent], None]]] = defaultdict(list)
        self._lock = threading.RLock()
        self._sequence = 0

    def publish(self, topic: str, payload: Optional[dict] = None, source: str = "runtime") -> RuntimeEvent:
        topic = str(topic or "").strip().lower()
        if not topic or len(topic) > 80:
            raise ValueError("Event topic must contain 1-80 characters")

        safe_payload = self._bounded_payload(payload or {})
        with self._lock:
            self._sequence += 1
            event = RuntimeEvent(self._sequence, topic, source[:80], safe_payload, time.time())
            self._events.append(event)
            callbacks = [
                *self._subscribers.get(topic, ()),
                *self._subscribers.get("*", ()),
            ]

        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                continue
        return event

    def subscribe(self, topic: str, callback: Callable[[RuntimeEvent], None]) -> Callable[[], None]:
        with self._lock:
            self._subscribers[topic].append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._subscribers.get(topic, ()):
                    self._subscribers[topic].remove(callback)

        return unsubscribe

    def recent(self, topic: str = "", limit: int = 20) -> list[dict]:
        limit = max(1, min(int(limit), 50))
        with self._lock:
            events = list(self._events)
        if topic:
            events = [event for event in events if event.topic == topic]
        return [asdict(event) for event in events[-limit:]]

    def _bounded_payload(self, payload: dict) -> dict:
        result = {}
        remaining = self._max_payload_chars
        for key, value in payload.items():
            if remaining <= 0:
                break
            text = str(value)
            text = text[:remaining]
            result[str(key)[:80]] = text
            remaining -= len(text)
        return result


class MemoryBudget:
    """Best-effort process-tree RSS budget with soft-pressure cleanup."""

    def __init__(self, soft_limit_mb: int = 600, hard_limit_mb: int = 800):
        hard = max(256, int(hard_limit_mb))
        soft = max(128, min(int(soft_limit_mb), hard - 32))
        self.soft_limit_mb = soft
        self.hard_limit_mb = hard

    def current_mb(self, include_children: bool = True) -> float:
        try:
            import psutil

            process = psutil.Process(os.getpid())
            rss = process.memory_info().rss
            if include_children:
                for child in process.children(recursive=True):
                    try:
                        rss += child.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            return rss / (1024 * 1024)
        except (ImportError, OSError):
            try:
                import resource

                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                if os.uname().sysname == "Darwin":
                    return rss / (1024 * 1024)
                return rss / 1024
            except Exception:
                return 0.0

    def pressure(self, include_children: bool = True) -> str:
        current = self.current_mb(include_children=include_children)
        if current >= self.hard_limit_mb:
            return "hard"
        if current >= self.soft_limit_mb:
            return "soft"
        return "normal"

    def trim(self) -> float:
        gc.collect()
        return self.current_mb()


class MemoryWatchdog:
    """Low-overhead watchdog that reports pressure and enforces a hard cap."""

    def __init__(
        self,
        budget: MemoryBudget,
        on_pressure: Optional[Callable[[str, float], None]] = None,
        interval_seconds: float = 2.0,
    ):
        self.budget = budget
        self.on_pressure = on_pressure
        self.interval_seconds = max(0.5, float(interval_seconds))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_pressure = "normal"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="MemoryWatchdog")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            current = self.budget.current_mb()
            pressure = self.budget.pressure()
            if pressure != "normal":
                current = self.budget.trim()
                pressure = self.budget.pressure()
            if pressure != self._last_pressure and self.on_pressure:
                self.on_pressure(pressure, current)
            self._last_pressure = pressure


def runtime_from_config(cfg: dict) -> tuple[LocalEventBus, MemoryBudget]:
    runtime_cfg = cfg.get("runtime", {})
    memory_cfg = runtime_cfg.get("memory", {})
    bus = LocalEventBus(
        max_events=runtime_cfg.get("event_history", 128),
        max_payload_chars=runtime_cfg.get("max_event_payload_chars", 4096),
    )
    budget = MemoryBudget(
        soft_limit_mb=memory_cfg.get("soft_limit_mb", 600),
        hard_limit_mb=memory_cfg.get("hard_limit_mb", 800),
    )
    return bus, budget
