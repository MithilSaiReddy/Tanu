"""
tanu/agent.py  —  v3

AgentLoop, HeartbeatService, CronService.

v3 — long-running, context-aware agent loop
──────────────────────────────────────────
• IterationBudget   : thread-safe consume/refund counter; refund on tool error
• Context manager   : prune old tool outputs + optional structured summary
                      when the conversation crosses the configured threshold
• Provider failover : retry a failing turn on agents.defaults.fallback_providers
                      (429 / 5xx / connection errors)
• Parallel tools    : multiple tool_calls execute concurrently, results kept
                      in original order
• Cancellation      : cancel_event aborts a turn mid-stream (voice-friendly)
• Message sanitizer : enforces User → Assistant alternation defensively
• on_turn_done      : callback fired with (final_text, usage) after each turn

Key improvements over v2
────────────────────────
• Callbacks system  : on_token / on_tool_start / on_tool_done / on_error
  → consumed by CLI (stdout), web UI (SSE), and tests alike
• Skills hot-reload : SKILL.md files re-read on every .run() call;
  file mtimes are tracked so rebuilds only happen when something changed
• Structured system prompt : identity + skills injected in clearly-labelled
  sections so the LLM can distinguish values from instructions from memory
• Tool error feedback : if a tool returns [TOOL ERROR …] the LLM sees it
  and can try a different approach
• Safe skill loading : a broken SKILL.md never crashes the agent
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from tanu import context as ctxmod
from tanu.config import get_active_provider, workspace_path
from tanu.identity import load_identity_block
from tanu.llm    import LLMError, LLMProvider
from tanu.runtime import LocalEventBus, MemoryBudget, runtime_from_config
from tanu.tools  import ToolRegistry
from tanu.tools.memory import MemoryStore

LOGO = "🎙️"

# HTTP statuses that trigger automatic provider failover.
_FAILOVER_STATUS = {429, 500, 502, 503, 504}

# ─────────────────────────────────────────────────────────────────────────────
#  ITERATION BUDGET
# ─────────────────────────────────────────────────────────────────────────────

class IterationBudget:
    """Thread-safe iteration counter with consume()/refund() semantics."""

    def __init__(self, max_iterations: int):
        self.max       = max(int(max_iterations), 1)
        self._used     = 0
        self._lock     = threading.Lock()
        self.exhausted = threading.Event()

    def consume(self) -> bool:
        """Reserve one iteration. Returns False (and sets `exhausted`) when the cap is hit."""
        with self._lock:
            if self._used >= self.max:
                self.exhausted.set()
                return False
            self._used += 1
            return True

    def refund(self, n: int = 1) -> None:
        """Give back iterations (e.g. a tool call failed and cost nothing useful)."""
        with self._lock:
            self._used = max(0, self._used - n)
            if self._used < self.max:
                self.exhausted.clear()

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

# ─────────────────────────────────────────────────────────────────────────────
#  SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────────────────

class SkillsLoader:
    """
    Loads workspace/skills/*/SKILL.md files and caches them by mtime.
    Calling .get() returns fresh content if any file changed, otherwise cached.
    """

    def __init__(
        self,
        workspace: Path,
        event_bus: Optional[LocalEventBus] = None,
        max_skills: int = 32,
        max_skill_chars: int = 4000,
        max_total_chars: int = 12000,
    ):
        self._skills_dir = workspace / "skills"
        self._event_bus = event_bus
        self._max_skills = max(1, min(int(max_skills), 64))
        self._max_skill_chars = max(512, min(int(max_skill_chars), 16_000))
        self._max_total_chars = max(
            self._max_skill_chars,
            min(int(max_total_chars), 64_000),
        )
        self._cache:   dict[str, str]   = {}   # path → content
        self._mtimes:  dict[str, float] = {}   # path → mtime
        self._result:  str = ""

    def get(self) -> str:
        if not self._skills_dir.exists():
            return ""

        changed = False
        current_paths: set[str] = set()

        skill_files = []
        for skill_file in self._skills_dir.glob("*/SKILL.md"):
            skill_files.append(skill_file)
            if len(skill_files) >= self._max_skills:
                break

        for skill_file in sorted(skill_files):
            key   = str(skill_file)
            mtime = skill_file.stat().st_mtime
            current_paths.add(key)
            if self._mtimes.get(key) != mtime:
                try:
                    with skill_file.open(encoding="utf-8", errors="replace") as handle:
                        self._cache[key] = handle.read(self._max_skill_chars)
                    self._mtimes[key] = mtime
                    changed = True
                    print(f"[INFO] Skill loaded: {skill_file.parent.name}", file=sys.stderr)
                except Exception as e:
                    print(f"[WARN] Skill read error {skill_file}: {e}", file=sys.stderr)

        # Remove deleted skills
        removed = set(self._cache) - current_paths
        for k in removed:
            del self._cache[k]
            del self._mtimes[k]
            changed = True

        if changed or not self._result:
            parts = []
            for key in sorted(self._cache):
                name = Path(key).parent.name
                parts.append(f"### Skill: {name}\n{self._cache[key]}")
            self._result = "\n\n".join(parts)[:self._max_total_chars]
            if changed and self._event_bus:
                self._event_bus.publish(
                    "skills.changed",
                    {"count": len(self._cache)},
                    source="skills-loader",
                )

        return self._result


def build_system_prompt(cfg: dict, skills_loader: SkillsLoader, memory_store=None) -> str:
    ws       = workspace_path(cfg)
    identity = load_identity_block(ws)
    skills   = skills_loader.get()

    sections = [
            textwrap.dedent(f"""
            You are Tanu, an ultra-lightweight personal AI assistant.
            Your workspace is: {ws}

            You are helpful, concise, and efficient.  You have tools for:
            • Optional online web search     • File read / write / append / list / delete
            • Shell command execution         • Current date and time
            • User memory (USER.md)           • Sending messages to the user
            • Todo list (todo.md)             • Task breakdown and tracking
            • Optional Gmail tools when online integrations are enabled
            • Local skill events: publish_event / read_events

            Always use tools when they'd improve your answer.
            After tool results, synthesise them into a clear, concise reply.
            If a tool returns [TOOL ERROR …], explain the issue and try an alternative.
            Prefer action over lengthy explanation.  Complete the task, then summarise.
            Use local events for small hand-offs between skills. Keep durable facts in
            memory or task storage; do not place large documents in event payloads.

            ## Task Mode
            When a user request has multiple steps (e.g., "set up my dev environment",
            "build a website", "migrate files"), use create_todo() to break it into
            numbered subtasks. Work through them one at a time. When you finish a
            task, call next_todo(complete_previous=True) to mark it done and get
            the next one. The system will automatically continue through all tasks
            until completion — no need to ask the user for permission between steps.
            Only ask the user if: input is ambiguous, operation is dangerous, or
            a task has failed after 2 retries.
        """).strip()
    ]

    if identity:
        sections.append(f"# Identity\n\n{identity}")

    if memory_store is not None:
        memory_notes = memory_store.format_for_system_prompt("memory")
        user_profile = memory_store.format_for_system_prompt("user")
        if memory_notes or user_profile:
            block = []
            if user_profile:
                block.append(f"## User Profile\n{user_profile}")
            if memory_notes:
                block.append(f"## Persistent Memory (agent notes)\n{memory_notes}")
            sections.append("# Memory\n\n" + "\n\n".join(block))

    if skills:
        sections.append(f"# Active Skills\n\n{skills}")

    return "\n\n" + ("\n\n─────────────────────────────────────────────────────\n\n".join(sections)) + "\n"

# ─────────────────────────────────────────────────────────────────────────────
#  AGENT LOOP
# ─────────────────────────────────────────────────────────────────────────────

class AgentLoop:
    """
    The core agentic reasoning + tool-use loop.

    Callbacks dict (all optional)
    ─────────────────────────────
    on_token(text)                  → called for each streamed token
    on_tool_start(name, args)       → called before a tool executes
    on_tool_done(name, result)      → called after a tool executes
    on_error(message)               → called when something goes wrong

    Usage
    ─────
    agent = AgentLoop(cfg, callbacks={
        "on_token":      lambda t: print(t, end="", flush=True),
        "on_tool_start": lambda n, a: print(f"\\n🔧 {n}({a})"),
        "on_tool_done":  lambda n, r: print(f"  → {r[:80]}"),
    })
    result = agent.run("What's my disk usage?", stream=True)
    """

    def __init__(
        self,
        cfg:             dict,
        send_message_fn: Optional[Callable[[str], None]] = None,
        callbacks:       Optional[dict]                  = None,
        max_iterations:  Optional[int]                   = None,
        system_prompt_override: Optional[str]            = None,
        event_bus:       Optional[LocalEventBus]          = None,
        memory_budget:   Optional[MemoryBudget]           = None,
    ):
        self.cfg        = cfg
        self.callbacks  = callbacks or {}
        defaults        = cfg["agents"]["defaults"]

        # Per-agent iteration budget (subagents may override the default cap).
        cap = max_iterations if max_iterations is not None else defaults.get("max_tool_iterations", 20)
        self.max_iter = cap
        if event_bus is None or memory_budget is None:
            default_bus, default_budget = runtime_from_config(cfg)
            event_bus = event_bus or default_bus
            memory_budget = memory_budget or default_budget
        self.event_bus = event_bus
        self.memory_budget = memory_budget
        self.max_parallel_tools = max(
            1, min(int(cfg.get("runtime", {}).get("max_parallel_tools", 3)), 8)
        )

        # Sub-agents can inject a role-focused system prompt instead of the
        # default identity + skills prompt.
        self._system_prompt_override = system_prompt_override

        pname, api_key, api_base, model = get_active_provider(cfg)
        if not pname:
            raise RuntimeError(
                "No LLM provider configured.\n"
                "Run: python main.py onboard\n"
                "Or start the local API: python main.py serve"
            )

        self._provider_name = pname
        self.llm = LLMProvider(
            name        = pname,
            api_key     = api_key,
            api_base    = api_base,
            model       = model,
            max_tokens  = defaults.get("max_tokens", 8192),
            temperature = defaults.get("temperature", 0.7),
            max_retries = defaults.get("llm_retries", 5),
            connect_timeout = defaults.get("llm_connect_timeout_seconds", 8),
            read_timeout = defaults.get("llm_read_timeout_seconds", 60),
        )

        # Fallback chain — retried mid-turn on 429 / 5xx / connection errors.
        self._fallback_chain: list[LLMProvider] = []
        for fname in defaults.get("fallback_providers", []):
            fcfg = cfg.get("providers", {}).get(fname)
            if not fcfg:
                print(f"[WARN] Fallback provider '{fname}' not configured — skipping", file=sys.stderr)
                continue
            self._fallback_chain.append(LLMProvider(
                name        = fname,
                api_key     = fcfg.get("api_key", ""),
                api_base    = fcfg.get("api_base", ""),
                model       = fcfg.get("model") or defaults.get("model", ""),
                max_tokens  = defaults.get("max_tokens", 8192),
                temperature = defaults.get("temperature", 0.7),
                max_retries = defaults.get("llm_retries", 5),
                connect_timeout = defaults.get("llm_connect_timeout_seconds", 8),
                read_timeout = defaults.get("llm_read_timeout_seconds", 60),
            ))

        # Context management — prune old verbose tool outputs and, when
        # configured, summarize the middle of the conversation window.
        self._ctx            = defaults.get("context", {})
        self._compressing    = False
        self._previous_summary: Optional[str] = None
        self._compaction_note_added = False
        self._summarize_fn   = self._summary_call

        # Persistent memory — bounded MEMORY.md / USER.md stores with a frozen
        # system-prompt snapshot (stable prefix across turns). Writes during a
        # turn update disk immediately but not the snapshot.
        mem_cfg = defaults.get("memory", {})
        self.memory = MemoryStore(
            workspace          = workspace_path(cfg),
            memory_char_limit  = mem_cfg.get("memory_char_limit", 2200),
            user_char_limit    = mem_cfg.get("user_char_limit", 1375),
            scan_enabled       = mem_cfg.get("scan_enabled", True),
        )
        self.memory.load_from_disk()

        # Tool registry with tool-level callbacks wired in
        self.tools = ToolRegistry(
            cfg,
            send_message_fn = send_message_fn,
            callbacks       = {
                "on_tool_start": self.callbacks.get("on_tool_start"),
                "on_tool_done":  self.callbacks.get("on_tool_done"),
            },
            event_bus       = self.event_bus,
            memory_budget   = self.memory_budget,
        )

        # Skills loader — hot-reloads on every .run() call
        runtime_cfg = cfg.get("runtime", {})
        self._skills_loader = SkillsLoader(
            workspace_path(cfg),
            event_bus=self.event_bus,
            max_skills=runtime_cfg.get("max_skills", 32),
            max_skill_chars=runtime_cfg.get("max_skill_chars", 4000),
            max_total_chars=runtime_cfg.get("max_active_skill_chars", 12000),
        )

        print(
            f"[INFO] Agent ready — provider={pname}, model={model}, "
            f"tools={len(self.tools.schema())}, "
            f"max_iter={self.max_iter}, fallbacks={len(self._fallback_chain)}",
            file=sys.stderr,
        )

    def run(
        self,
        user_message: str,
        history:      Optional[list] = None,
        stream:       bool           = True,
        auto_continue: bool          = True,
        cancel_event: Optional[threading.Event] = None,
    ) -> Optional[str]:
        """
        Execute one conversational turn.
        When auto_continue=True, after the agent finishes its response the
        loop checks for pending todo items and automatically continues
        working through them — no user prompt needed between tasks.
        When cancel_event is set, the turn aborts and None is returned
        (callers already guard with `if result:`).
        Returns the final concatenated text, or None if cancelled.
        """
        if self.memory_budget.pressure() == "hard":
            self.event_bus.publish("memory.hard_limit", {}, source="agent")
            return "[ERROR] Memory hard limit reached; start a new turn after memory is released."

        self.event_bus.publish("turn.started", {"message_chars": len(user_message)}, source="agent")

        system_prompt = (
            self._system_prompt_override
            or build_system_prompt(self.cfg, self._skills_loader, memory_store=self.memory)
        )
        tools_schema  = self.tools.schema()

        # Internal message window — copies caller history so auto-continue
        # turns don't pollute the external session history.
        internal_hist = self._sanitize_message_list(history or [])
        current_msg   = user_message
        parts: list[str] = []

        budget = IterationBudget(self.max_iter)

        while True:
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(internal_hist)
            messages.append({"role": "user", "content": current_msg})

            final      = ""

            while budget.consume():
                if cancel_event is not None and cancel_event.is_set():
                    return None

                if self._ctx.get("enabled", True):
                    messages = self._maybe_compress(messages)

                use_stream = stream

                try:
                    resp = self._call_llm(messages, tools_schema, use_stream, cancel_event)
                except LLMError as e:
                    err = f"LLM call failed: {e}"
                    if self.callbacks.get("on_error"):
                        self.callbacks["on_error"](err)
                    return f"[ERROR] {err}"
                except Exception as e:
                    err = f"LLM call failed: {type(e).__name__}: {e}"
                    if self.callbacks.get("on_error"):
                        self.callbacks["on_error"](err)
                    return f"[ERROR] {err}"

                if resp is None or resp.get("cancelled"):
                    return None

                choice     = resp["choices"][0]
                msg        = choice["message"]
                messages.append(msg)
                tool_calls = msg.get("tool_calls") or []

                if not tool_calls:
                    final = (msg.get("content") or "").strip()
                    break

                results = self._execute_tool_calls(tool_calls, cancel_event)
                if results is None:
                    return None

                for tc, result in zip(tool_calls, results):
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": tc.get("id", "t0"),
                        "content":      result,
                    })
                    if result.startswith("[TOOL ERROR"):
                        budget.refund()
            else:
                return "[Max tool iterations reached — task may be incomplete]"

            parts.append(final)

            if self.callbacks.get("on_turn_done"):
                usage = resp.get("usage") if isinstance(resp, dict) else None
                self.callbacks["on_turn_done"](final, usage)

            if not auto_continue:
                break

            # ── Auto-continue: advance to next todo item ──
            next_result = self.tools.call("next_todo", {"complete_previous": True})
            if next_result.startswith("[TASK"):
                internal_hist.append({"role": "assistant", "content": final})
                current_msg = f"[Auto-continue] Continue with the next todo item:\n\n{next_result}"
                continue
            elif next_result.startswith("[DONE]"):
                parts.append(next_result)

            break

        result = "\n\n".join(parts) if len(parts) > 1 else (parts[0] if parts else "")
        self.event_bus.publish("turn.completed", {"response_chars": len(result)}, source="agent")
        return result

    # ── Loop helpers ─────────────────────────────────────────────────────────

    def _call_llm(
        self,
        messages:     list,
        tools_schema: list,
        use_stream:   bool,
        cancel_event: Optional[threading.Event],
    ) -> dict:
        """
        Make an LLM call, transparently failing over to the fallback chain
        on retryable errors. Raises LLMError if every provider fails.
        """
        providers = [self.llm] + self._fallback_chain
        last_exc  = None

        for llm in providers:
            try:
                return llm.chat(
                    messages,
                    tools      = tools_schema,
                    stream     = use_stream,
                    token_cb   = self.callbacks.get("on_token") if use_stream else None,
                    cancel_event = cancel_event,
                )
            except LLMError as e:
                last_exc = e
                if e.status not in _FAILOVER_STATUS:
                    raise  # auth / model / other — not worth failover
                if llm is not self.llm:
                    print(f"[WARN] Fallback provider '{llm.name}' also failed: {e}", file=sys.stderr)
                elif self._fallback_chain:
                    print(
                        f"[WARN] Provider '{self._provider_name}' failed ({e.status}) — "
                        f"trying fallback(s): {[p.name for p in self._fallback_chain]}",
                        file=sys.stderr,
                    )
                if self.callbacks.get("on_error"):
                    self.callbacks["on_error"](str(e))

        raise last_exc or LLMError(0, "All providers failed.")

    def _maybe_compress(self, messages: list) -> list:
        """
        Preflight window compression:
          1. prune verbose old tool outputs (free)
          2. if still over threshold and summarization is enabled,
             summarize the middle turns and splice in a compact summary
        """
        max_chars   = self._ctx.get("max_chars", 32000)
        threshold   = self._ctx.get("threshold", 0.5)
        trigger     = max_chars * threshold

        if ctxmod.estimate_chars(messages) < trigger:
            return messages
        if self._compressing:  # recursion guard
            return messages

        self._compressing = True
        try:
            messages = ctxmod.prune_old_tool_outputs(
                messages,
                protect_last_n = self._ctx.get("protect_last_n", 8),
                min_len        = 200,
            )

            if self._ctx.get("summarize", False) and ctxmod.estimate_chars(messages) >= trigger:
                boundary = ctxmod.pick_boundary(
                    messages,
                    trigger,
                    protect_last_n = self._ctx.get("protect_last_n", 8),
                )
                middle = messages[:boundary]
                tail   = messages[boundary:]

                summary = ctxmod.summarize_middle(
                    middle,
                    self._summarize_fn,
                    previous_summary = self._previous_summary,
                    max_summary_chars = self._ctx.get("max_summary_chars", 4000),
                )
                if summary:
                    self._previous_summary = summary
                    if not self._compaction_note_added:
                        note = (
                            "\n\n[Note: some earlier conversation turns have been "
                            "compacted. A structured summary is included below.]"
                        )
                        messages[0] = {
                            **messages[0],
                            "content": messages[0].get("content", "") + note,
                        }
                        self._compaction_note_added = True

                    summary_msg = {
                        "role": "user",
                        "content": (
                            "[CONTEXT COMPACTION] Earlier turns were compacted "
                            f"into this summary:\n\n{summary}"
                        ),
                    }
                    messages = messages[:1] + [summary_msg] + tail
                    messages = ctxmod.sanitize_tool_pairs(messages)

                    print(f"[INFO] Context compacted — {len(middle)} turns summarized", file=sys.stderr)
            return messages
        except Exception as e:
            print(f"[WARN] Context compression failed: {e}", file=sys.stderr)
            return messages
        finally:
            self._compressing = False

    def _summary_call(self, prompt_messages: list) -> Optional[str]:
        """Run the summarizer against the current LLM (no tools, not streamed)."""
        resp = self.llm.chat(prompt_messages, tools=None, stream=False)
        return (resp["choices"][0]["message"].get("content") or "").strip() or None

    def _execute_tool_calls(
        self,
        tool_calls:  list,
        cancel_event: Optional[threading.Event],
    ) -> Optional[list]:
        """
        Dispatch tool calls. Single call → direct; multiple calls → concurrent,
        results returned in the original order. Returns None if cancelled.
        """
        parsed: list[tuple[dict, str, dict]] = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            parsed.append((tc, name, args))

        if not parsed:
            return []
        if cancel_event is not None and cancel_event.is_set():
            return None
        if len(parsed) == 1:
            _, name, args = parsed[0]
            return [self.tools.call(name, args)]

        with ThreadPoolExecutor(max_workers=min(len(parsed), self.max_parallel_tools)) as ex:
            futures = [ex.submit(self.tools.call, name, args) for _, name, args in parsed]
            return [f.result() for f in futures]

    @staticmethod
    def _sanitize_message_list(messages: list) -> list:
        """
        Defensive role-alternation sanitizer. Drops empty assistant turns and
        collapses consecutive same-role messages (system/user/assistant).
        """
        out: list = []
        for m in messages:
            role = m.get("role")
            if role not in ("system", "user", "assistant", "tool"):
                continue
            if role == "assistant":
                content = m.get("content")
                if (content is None or not str(content).strip()) and not m.get("tool_calls"):
                    continue
            prev = out[-1] if out else None
            if prev is not None and prev.get("role") == role and role != "tool":
                continue
            out.append(dict(m))
        return out

# ─────────────────────────────────────────────────────────────────────────────
#  HEARTBEAT SERVICE
# ─────────────────────────────────────────────────────────────────────────────

class HeartbeatService:
    """
    Reads workspace/HEARTBEAT.md every `interval_minutes` and runs its
    contents as an agent prompt.

    Example HEARTBEAT.md:
        - Check disk space; warn in USER.md if above 80%
        - Append today's date + weather summary to journal.md
    """

    def __init__(self, agent: AgentLoop, workspace: Path, interval_minutes: int = 30):
        self.agent    = agent
        self.hb_file  = workspace / "HEARTBEAT.md"
        self.interval = interval_minutes * 60
        self._stop    = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()
        print(
            f"[INFO] Heartbeat started — interval={self.interval // 60}min, file={self.hb_file}",
            file=sys.stderr,
        )

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            if not self.hb_file.exists():
                continue
            try:
                content = self.hb_file.read_text(encoding="utf-8")
                prompt  = (
                    "[HEARTBEAT] Execute the periodic tasks listed below, "
                    "then reply HEARTBEAT_OK.\n\n"
                    f"{content}"
                )
                print(f"\n{LOGO} [Heartbeat] Running periodic tasks...", file=sys.stderr)
                self.agent.run(prompt, stream=False, auto_continue=False)
            except Exception as e:
                print(f"[WARN] Heartbeat error: {e}", file=sys.stderr)

    def stop(self) -> None:
        self._stop.set()

# ─────────────────────────────────────────────────────────────────────────────
#  CRON SERVICE
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_CRON_JOBS = [
    {
        "name":             "example-weather-check",
        "prompt":           "Check today's weather and save a summary to weather.md",
        "interval_minutes": 1440,
        "last_run":         None,
    },
]


class CronService:
    """
    Reads workspace/cron/jobs.json every minute and fires due jobs.

    jobs.json format:
    [
      {
        "name":             "daily-news",
        "prompt":           "Search for today's top AI news and save to news.md",
        "interval_minutes": 1440,
        "last_run":         null
      }
    ]
    """

    def __init__(self, agent: AgentLoop, workspace: Path):
        self.agent     = agent
        self._cron_dir = workspace / "cron"
        self.jobs_file = self._cron_dir / "jobs.json"
        self._stop     = threading.Event()

    def start(self) -> None:
        self._ensure_files()
        threading.Thread(target=self._loop, daemon=True).start()
        print(
            f"[INFO] Cron started — poll_interval=60s, file={self.jobs_file}",
            file=sys.stderr,
        )

    def _ensure_files(self) -> None:
        self._cron_dir.mkdir(parents=True, exist_ok=True)
        if not self.jobs_file.exists():
            self.jobs_file.write_text(
                json.dumps(SAMPLE_CRON_JOBS, indent=2), encoding="utf-8"
            )
            print(
                f"[INFO] Created sample cron jobs file: {self.jobs_file}",
                file=sys.stderr,
            )

    def _loop(self) -> None:
        while not self._stop.wait(60):
            if not self.jobs_file.exists():
                continue
            try:
                raw     = self.jobs_file.read_text(encoding="utf-8")
                jobs    = json.loads(raw)
                now     = datetime.datetime.now()
                changed = False
                for job in jobs:
                    if not isinstance(job, dict) or not job.get("prompt"):
                        continue
                    if self._should_run(job, now):
                        print(f"[Cron] Running: {job.get('name', 'unnamed')}", file=sys.stderr)
                        try:
                            self.agent.run(job["prompt"], stream=False, auto_continue=False)
                        except Exception as e:
                            print(f"[WARN] Cron job '{job.get('name', 'unnamed')}' failed: {e}", file=sys.stderr)
                            continue
                        job["last_run"] = now.isoformat()
                        changed = True
                if changed:
                    self.jobs_file.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"[WARN] Cron error: {e}", file=sys.stderr)

    @staticmethod
    def _should_run(job: dict, now: datetime.datetime) -> bool:
        last_run = job.get("last_run")
        if not last_run:
            return True
        try:
            last = datetime.datetime.fromisoformat(str(last_run))
            return (now - last).total_seconds() >= job.get("interval_minutes", 60) * 60
        except Exception:
            return False

    def stop(self) -> None:
        self._stop.set()
