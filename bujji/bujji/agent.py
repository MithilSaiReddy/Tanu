"""
bujji/agent.py  —  v2

AgentLoop, HeartbeatService, CronService.

Key improvements over v1
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
from pathlib import Path
from typing import Callable, Optional

from bujji.config import get_active_provider, workspace_path
from bujji.llm import LLMProvider
from bujji.tools import ToolRegistry

LOGO = "🦞"

# ─────────────────────────────────────────────────────────────────────────────
#  SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────────────────


def _read_identity_files(workspace: Path) -> str:
    """Read SOUL.md, IDENTITY.md, USER.md, AGENT.md, BACKSTORY.md in that order."""
    files = ["SOUL.md", "IDENTITY.md", "USER.md", "AGENT.md", "BACKSTORY.md"]
    parts = []
    for fname in files:
        path = workspace / fname
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8", errors="replace").strip()
                if content:
                    parts.append(content)
            except Exception:
                pass
    return "\n\n---\n\n".join(parts)


class SkillsLoader:
    """
    Loads workspace/skills/*/SKILL.md files and caches them by mtime.
    Calling .get() returns fresh content if any file changed, otherwise cached.
    """

    def __init__(self, workspace: Path):
        self._skills_dir = workspace / "skills"
        self._cache: dict[str, str] = {}  # path → content
        self._mtimes: dict[str, float] = {}  # path → mtime
        self._result: str = ""

    def get(self) -> str:
        if not self._skills_dir.exists():
            return ""

        changed = False
        current_paths: set[str] = set()

        for skill_file in sorted(self._skills_dir.glob("*/SKILL.md")):
            key = str(skill_file)
            mtime = skill_file.stat().st_mtime
            current_paths.add(key)
            if self._mtimes.get(key) != mtime:
                try:
                    self._cache[key] = skill_file.read_text(
                        encoding="utf-8", errors="replace"
                    )
                    self._mtimes[key] = mtime
                    changed = True
                    print(
                        f"[INFO] Skill loaded: {skill_file.parent.name}",
                        file=sys.stderr,
                    )
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
            self._result = "\n\n".join(parts)

        return self._result


def build_system_prompt(
    cfg: dict,
    skills_loader: SkillsLoader,
    agent_name: str = "bujji",
    workspace: Path = None,
) -> str:
    if workspace is None:
        workspace = workspace_path(cfg)
    identity = _read_identity_files(workspace)
    skills = skills_loader.get()

    if agent_name == "tanu":
        base_intro = textwrap.dedent(f"""
            You are Tanu. A quiet operator who gets things done.
            Your workspace is: {workspace}

            You have tools for:
            • Tasks: create, list, complete, update, delete
            • Reminders: set, list, cancel
            • Email: fetch, send, reply, mark read
            • Quick: time, timer, calculations

            ## Response Style - ADAPTIVE

            If doing work (tools used):
            - Keep it short. 1-2 sentences.
            - Briefly acknowledge what was done.
            - "Task added." not "I have successfully added the task."
            - "Reminder set for 3pm." not "I've set a reminder for 3pm."
            - "You have 2 tasks." not "Based on my analysis, you currently have 2 tasks."
            - If listing items, just list them concisely.

            If just chatting (no tools):
            - Be normal. Natural conversation.
            - "Hey!" "Doing good." "Same here." "Nice!"

            If something breaks:
            - Say what broke. "Email failed - check connection."
        """).strip()
    else:
        base_intro = textwrap.dedent(f"""
            You are bujji, an ultra-lightweight personal AI assistant.
            Your workspace is: {workspace}

            You are helpful, concise, and efficient.  You have tools for:
            • Web search (Brave API)         • File read / write / append / list / delete
            • Shell command execution         • Current date and time
            • User memory (USER.md)           • Sending messages to the user
            • Todo list (todo.md)             • Task breakdown and tracking

            Always use tools when they'd improve your answer.
            After tool results, synthesise them into a clear, concise reply.
            If a tool returns [TOOL ERROR …], explain the issue and try an alternative.
            Prefer action over lengthy explanation.  Complete the task, then summarise.

            ## Task Mode
            When a user request has multiple steps (e.g., "set up my dev environment",
            "build a website", "migrate files"), use create_todo() to break it into
            numbered subtasks, then use next_todo() to work through them sequentially.
            After each successful tool execution, call next_todo() to automatically
            get the next task and continue until all are done.
            Only ask the user if: input is ambiguous, operation is dangerous, or
            a task has failed after 2 retries.
        """).strip()

    sections = [base_intro]

    if identity:
        sections.append(f"# Identity & Memory\n\n{identity}")
    if skills:
        sections.append(f"# Active Skills\n\n{skills}")

    return (
        "\n\n"
        + (
            "\n\n─────────────────────────────────────────────────────\n\n".join(
                sections
            )
        )
        + "\n"
    )


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
        cfg: dict,
        send_message_fn: Optional[Callable[[str], None]] = None,
        callbacks: Optional[dict] = None,
        agent_name: str = "bujji",
        workspace: Path = None,
    ):
        self.cfg = cfg
        self.callbacks = callbacks or {}
        self.agent_name = agent_name
        self.workspace = workspace if workspace else workspace_path(cfg)
        defaults = cfg["agents"]["defaults"]
        self.max_iter = defaults.get("max_tool_iterations", 20)

        pname, api_key, api_base, model = get_active_provider(cfg)
        if not pname:
            raise RuntimeError(
                "No LLM provider configured.\n"
                "Run: python main.py onboard\n"
                "Or open the web UI: python main.py serve"
            )

        self.llm = LLMProvider(
            name=pname,
            api_key=api_key,
            api_base=api_base,
            model=model,
            max_tokens=defaults.get("max_tokens", 8192),
            temperature=defaults.get("temperature", 0.7),
        )

        # Tool registry with tool-level callbacks wired in
        self.tools = ToolRegistry(
            cfg,
            send_message_fn=send_message_fn,
            callbacks={
                "on_tool_start": self.callbacks.get("on_tool_start"),
                "on_tool_done": self.callbacks.get("on_tool_done"),
            },
        )

        # Skills loader — hot-reloads on every .run() call
        self._skills_loader = SkillsLoader(self.workspace)

        print(
            f"[INFO] Agent ready — provider={pname}, model={model}, "
            f"tools={len(self.tools.schema())}",
            file=sys.stderr,
        )

    def run(
        self,
        user_message: str,
        history: Optional[list] = None,
        stream: bool = True,
    ) -> str:
        """
        Execute one conversational turn.
        Returns the final text (may be empty string if fully streamed via on_token).
        """
        # Rebuild system prompt each turn — picks up any skill/identity file changes
        system_prompt = build_system_prompt(
            self.cfg, self._skills_loader, self.agent_name, self.workspace
        )

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        tools_schema = self.tools.schema()
        first_call = True

        for iteration in range(self.max_iter):
            # Only stream the first LLM call (before any tool use)
            use_stream = stream and first_call
            first_call = False

            try:
                resp = self.llm.chat(
                    messages,
                    tools=tools_schema,
                    stream=use_stream,
                    token_cb=self.callbacks.get("on_token") if use_stream else None,
                )
            except Exception as e:
                err = f"LLM call failed: {type(e).__name__}: {e}"
                if self.callbacks.get("on_error"):
                    self.callbacks["on_error"](err)
                return f"[ERROR] {err}"

            choice = resp["choices"][0]
            msg = choice["message"]
            messages.append(msg)
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                # ── Final text response ──
                final = (msg.get("content") or "").strip()
                return final

            # ── Execute all requested tools ──
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    args = {}

                # Execute (ToolRegistry handles callbacks internally)
                result = self.tools.call(name, args)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", "t0"),
                        "content": result,
                    }
                )

                # Auto-continue: check for pending todos after successful execution
                # Only continue if the tool didn't error and todo has pending tasks
                if not result.startswith("[TOOL ERROR"):
                    next_result = self.tools.call(
                        "next_todo", {"complete_previous": True}
                    )
                    if "[TASK" in next_result or "[DONE]" in next_result:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id", "t0") + "_next",
                                "content": next_result,
                            }
                        )

            # Loop → let LLM see the tool results

        return "[Max tool iterations reached — task may be incomplete]"


# ─────────────────────────────────────────────────────────────────────────────
#  HEARTBEAT SERVICE
# ─────────────────────────────────────────────────────────────────────────────


class HeartbeatService:
    """
    Tanu's continuous background loop.

    - Checks workspace/HEARTBEAT.md for periodic tasks
    - Checks for due reminders and notifies
    - Checks for pending tasks

    Tanu stays quiet unless there's something important to say.
    """

    def __init__(self, agent: AgentLoop, workspace: Path, interval_minutes: int = 5):
        self.agent = agent
        self.hb_file = workspace / "HEARTBEAT.md"
        self.tanu_dir = workspace / "tanu"
        self.interval = interval_minutes * 60
        self._stop = threading.Event()
        self._last_reminder_check = None

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()
        print(
            f"[INFO] Heartbeat started — interval={self.interval // 60}min",
            file=sys.stderr,
        )

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self._check_reminders()
                self._check_heartbeat_tasks()
            except Exception as e:
                print(f"[WARN] Heartbeat error: {e}", file=sys.stderr)

    def _check_reminders(self) -> None:
        """Check for due reminders and trigger notification."""
        import json
        from datetime import datetime

        reminders_file = self.tanu_dir / "reminders.json"
        if not reminders_file.exists():
            return

        try:
            data = json.loads(reminders_file.read_text(encoding="utf-8"))
            reminders = data.get("reminders", [])
            now = datetime.now()

            for r in reminders:
                if r.get("triggered"):
                    continue
                try:
                    r_time = datetime.fromisoformat(r["time"])
                    if r_time <= now:
                        message = f"Reminder: {r['message']}"
                        print(f"[Tanu] {message}", file=sys.stderr)

                        # Send notification via agent's message function
                        if hasattr(
                            self.agent, "callbacks"
                        ) and self.agent.callbacks.get("on_notification"):
                            self.agent.callbacks["on_notification"](message)

                        r["triggered"] = now.isoformat()
                except (ValueError, TypeError):
                    continue

            reminders_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            print(f"[WARN] Reminder check error: {e}", file=sys.stderr)

    def _check_heartbeat_tasks(self) -> None:
        """Execute periodic tasks from HEARTBEAT.md."""
        if not self.hb_file.exists():
            return
        try:
            content = self.hb_file.read_text(encoding="utf-8")
            if not content.strip():
                return

            prompt = (
                "[HEARTBEAT] Execute these periodic tasks quietly. "
                "Only respond if there's an urgent issue or something important.\n\n"
                f"{content}"
            )
            result = self.agent.run(prompt, stream=False)

            # Tanu stays quiet unless there's something to say
            if result and result.strip() and "HEARTBEAT_OK" not in result:
                print(f"[Tanu] {result}", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Heartbeat task error: {e}", file=sys.stderr)

    def stop(self) -> None:
        self._stop.set()


# ─────────────────────────────────────────────────────────────────────────────
#  CRON SERVICE
# ─────────────────────────────────────────────────────────────────────────────


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
        self.agent = agent
        self.jobs_file = workspace / "cron" / "jobs.json"
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while not self._stop.wait(60):
            if not self.jobs_file.exists():
                continue
            try:
                jobs = json.loads(self.jobs_file.read_text(encoding="utf-8"))
                now = datetime.datetime.now()
                changed = False
                for job in jobs:
                    if self._should_run(job, now):
                        print(
                            f"[Cron] Running: {job.get('name', 'unnamed')}",
                            file=sys.stderr,
                        )
                        self.agent.run(job["prompt"], stream=False)
                        job["last_run"] = now.isoformat()
                        changed = True
                if changed:
                    self.jobs_file.write_text(
                        json.dumps(jobs, indent=2), encoding="utf-8"
                    )
            except Exception as e:
                print(f"[WARN] Cron error: {e}", file=sys.stderr)

    @staticmethod
    def _should_run(job: dict, now: datetime.datetime) -> bool:
        last_run = job.get("last_run")
        if not last_run:
            return True
        try:
            last = datetime.datetime.fromisoformat(last_run)
            return (now - last).total_seconds() >= job.get("interval_minutes", 60) * 60
        except Exception:
            return False

    def stop(self) -> None:
        self._stop.set()
