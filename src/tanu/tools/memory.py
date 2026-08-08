"""
tanu/tools/memory.py  —  v3

Bounded, curated persistent memory.
- Two stores: MEMORY.md (agent notes) + USER.md (user profile)
- Single `memory` tool: add / replace / remove via old_text substring match
- § entry delimiter (entries can be multiline), dedup on load
- Per-store char limits; overflow returns entries + usage so the agent
  consolidates and retries — memory manages itself
- Prompt-injection scan: only on the system-prompt snapshot; poisoned entries
  become a [BLOCKED: …] placeholder while the raw text stays in live state
  so the user can inspect and remove it
- Durability: file lock, atomic rename, drift detection (an external edit that
  breaks the § format refuses to be overwritten and is backed up)
- Frozen snapshot: MemoryStore.load_from_disk() captures the block injected
  into the system prompt; mid-session writes hit disk immediately but never
  mutate the snapshot, keeping the prompt prefix byte-stable across turns
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from tanu.tools.base import ToolContext, register_tool

# ── Storage format ────────────────────────────────────────────────────────────

_DELIM = "\n§\n"          # separator between entries (section sign)
_BLOCKED = (
    "[BLOCKED: entry contained a prompt-injection pattern and was "
    "removed from the system prompt. It is still stored so you can "
    "inspect or remove it.]"
)

# Strict, conservative threat patterns — scanned at snapshot build time only.
_THREAT_PATTERNS = [
    re.compile(r"ignore\s+(?:all|any|every|all\s+previous|all\s+prior)\s+(?:instructions|prompts|rules|directives|messages)", re.I),
    re.compile(r"disregard\s+(?:all|any|every|all\s+previous)\s+(?:instructions|prompts|rules)", re.I),
    re.compile(r"forget\s+(?:all|everything|every)\s+(?:previous|prior)", re.I),
    re.compile(r"you\s+are\s+now\s+(?:an?|a)?\s*(?:jailbroken|unrestricted|the\s+system|root)", re.I),
    re.compile(r"pretend\s+(?:that\s+)?you\s+are\s+(?:the\s+)?system", re.I),
    re.compile(r"<\|?(?:im_start|im_end|system)\|?>", re.I),
    re.compile(r"</?system>", re.I),
    re.compile(r"jailbreak|do\s+anything\s+now|no\s+(?:safety|filters|restrictions)", re.I),
    re.compile(r"exfiltrate|send\s+.*(?:to\s+an?\s+external|to\s+a\s+remote|credentials?|api\s+key)", re.I),
]


def _scan_for_threats(text: str) -> bool:
    """True if the entry matches a known prompt-injection pattern."""
    return any(p.search(text) for p in _THREAT_PATTERNS)


# ── File locking (fcntl on POSIX, msvcrt on Windows, no-op fallback) ───────

try:
    import fcntl as _fcntl
except ImportError:   # pragma: no cover - Windows
    _fcntl = None
try:
    import msvcrt as _msvcrt
except ImportError:   # pragma: no cover - POSIX
    _msvcrt = None


@contextmanager
def _file_lock(lock_path: Path):
    """Exclusive advisory lock around a read-modify-write cycle."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, "a+", encoding="utf-8")
    try:
        if _fcntl is not None:
            _fcntl.flock(fd.fileno(), _fcntl.LOCK_EX)
        elif _msvcrt is not None:  # pragma: no cover - Windows
            fd.seek(0)
            _msvcrt.locking(fd.fileno(), _msvcrt.LK_LOCK, 1)
        yield
    finally:
        if _fcntl is not None:
            try:
                _fcntl.flock(fd.fileno(), _fcntl.LOCK_UN)
            except (OSError, IOError):
                pass
        elif _msvcrt is not None:  # pragma: no cover - Windows
            try:
                fd.seek(0)
                _msvcrt.locking(fd.fileno(), _msvcrt.LK_UNLCK, 1)
            except (OSError, IOError):
                pass
        fd.close()


def _atomic_write(path: Path, content: str) -> None:
    """Write via a temp file then rename — never a torn write."""
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ── MemoryStore ──────────────────────────────────────────────────────────────

class MemoryStore:
    """Bounded, file-backed memory with a frozen system-prompt snapshot."""

    FILES = {"memory": "MEMORY.md", "user": "USER.md"}

    def __init__(
        self,
        workspace: Path,
        memory_char_limit: int = 2200,
        user_char_limit: int = 1375,
        scan_enabled: bool = True,
    ):
        self.workspace    = Path(workspace)
        self.limits       = {"memory": int(memory_char_limit), "user": int(user_char_limit)}
        self.scan_enabled = scan_enabled
        self._entries:  dict[str, list[str]] = {"memory": [], "user": []}
        self._snapshot: dict[str, str]       = {"memory": "", "user": ""}

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def load_from_disk(self) -> None:
        """Read both stores, dedup, and capture the frozen snapshot."""
        for target in ("memory", "user"):
            entries = self._read_entries(target)
            entries = list(dict.fromkeys(entries))       # dedup, keep order
            self._entries[target] = entries
            self._snapshot[target] = self._render_block(target, entries)

    def format_for_system_prompt(self, target: str) -> Optional[str]:
        """Frozen snapshot captured at load_from_disk() — never live state."""
        block = self._snapshot.get(target, "")
        return block or None

    def entries(self, target: str) -> list[str]:
        """Live entries (reflects writes made this session)."""
        return list(self._entries.get(target, []))

    def usage(self, target: str) -> int:
        return sum(len(e) for e in self._entries.get(target, []))

    # ── Mutations (live state + disk; snapshot stays frozen) ──────────────

    def add(self, target: str, content: str) -> dict:
        content = content.strip()
        if not content:
            return {"success": False, "error": "content is required."}
        entries = self._reload(target)
        new_len = len(content)
        if content in entries:
            return {
                "success": True,
                "message": f"Already stored in {target} — skipping duplicate.",
                "usage": f"{self.usage(target)}/{self.limits[target]}",
            }
        total   = sum(len(e) for e in entries) + new_len
        limit   = self.limits[target]
        if total > limit:
            return {
                "success": False,
                "error": (
                    f"Memory at {self.usage(target)}/{limit} chars. Adding this entry "
                    f"({new_len} chars) would exceed the limit. Consolidate now: use "
                    f"'replace' to merge overlapping entries into shorter ones or "
                    f"'remove' stale entries, then retry this add — all in this turn."
                ),
                "current_entries": entries,
                "usage": f"{self.usage(target)}/{limit}",
            }
        entries.append(content)
        self._entries[target] = entries
        err = self._save(target, entries)
        if err:
            return {"success": False, "error": err}
        return {
            "success": True,
            "message": f"Added to {target} ({new_len} chars). Total: {self.usage(target)}/{self.limits[target]}.",
            "usage": f"{self.usage(target)}/{self.limits[target]}",
        }

    def replace(self, target: str, old_text: str, content: str) -> dict:
        content = content.strip()
        if not old_text or not content:
            return {"success": False, "error": "old_text and content are both required."}
        entries = self._reload(target)
        for i, e in enumerate(entries):
            if old_text in e:
                entries[i] = content
                self._entries[target] = entries
                err = self._save(target, entries)
                if err:
                    return {"success": False, "error": err}
                return {
                    "success": True,
                    "message": f"Replaced entry in {target} with '{content[:60]}…'",
                    "usage": f"{self.usage(target)}/{self.limits[target]}",
                }
        return {
            "success": False,
            "error": f"No entry containing '{old_text}' was found.",
            "current_entries": entries,
        }

    def remove(self, target: str, old_text: str) -> dict:
        if not old_text:
            return {"success": False, "error": "old_text is required."}
        entries = self._reload(target)
        kept = [e for e in entries if old_text not in e]
        if len(kept) == len(entries):
            return {
                "success": False,
                "error": f"No entry containing '{old_text}' was found.",
                "current_entries": entries,
            }
        self._entries[target] = kept
        err = self._save(target, kept)
        if err:
            return {"success": False, "error": err}
        return {
            "success": True,
            "message": f"Removed entry containing '{old_text}' from {target}.",
            "usage": f"{self.usage(target)}/{self.limits[target]}",
        }

    # ── Internals ─────────────────────────────────────────────────────────

    def _path_for(self, target: str) -> Path:
        return self.workspace / self.FILES[target]

    def _read_entries(self, target: str) -> list[str]:
        path = self._path_for(target)
        if not path.exists():
            return []
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            return []
        entries = [e.strip() for e in raw.split(_DELIM) if e.strip()]
        return self._drop_placeholders(target, entries)

    @staticmethod
    def _drop_placeholders(target: str, entries: list[str]) -> list[str]:
        """Drop the shipped default text if it's still stored as an entry.

        Fresh installs get USER.md/MEMORY.md with placeholder copy; that
        placeholder must not survive as a real entry once real facts arrive.
        """
        try:
            from tanu.identity import _DEFAULT_USER, _DEFAULT_MEMORY
        except Exception:
            return entries
        defaults = {"user": _DEFAULT_USER, "memory": _DEFAULT_MEMORY}
        default = (defaults.get(target) or "").strip()
        if not default:
            return entries
        return [e for e in entries if e != default]

    def _reload(self, target: str) -> list[str]:
        """Re-read from disk before mutating so concurrent writers are seen."""
        fresh = self._read_entries(target)
        fresh = list(dict.fromkeys(fresh))
        self._entries[target] = fresh
        return fresh

    def _serialize(self, entries: list[str]) -> str:
        return _DELIM.join(entries) + "\n"

    def _save(self, target: str, entries: list[str]) -> Optional[str]:
        """Write under lock. Returns an error string on drift/conflict."""
        path = self._path_for(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(path.suffix + ".lock")

        with _file_lock(lock_path):
            on_disk = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
            if on_disk.strip() and on_disk.strip() != _DELIM.join(self._read_entries(target)).strip():
                # External edit that wouldn't round-trip through our format —
                # refuse to overwrite, keep a backup.
                bak = path.with_suffix(".bak")
                try:
                    bak.write_bytes(path.read_bytes())
                except OSError:
                    pass
                return (
                    "Memory file was modified outside this session in a way that "
                    "doesn't match the entry format. Changes were preserved and a "
                    "backup saved; the write was skipped."
                )
            _atomic_write(path, self._serialize(entries))
        return None

    def _render_block(self, target: str, entries: list[str]) -> str:
        lines = []
        for e in entries:
            text = e
            if self.scan_enabled and _scan_for_threats(text):
                text = _BLOCKED
            lines.append(f"- {text}")
        return "\n".join(lines)


# ── Tools ─────────────────────────────────────────────────────────────────────

def _store_for(ctx: ToolContext) -> MemoryStore:
    mconf = (
        ctx.cfg
            .get("agents", {})
            .get("defaults", {})
            .get("memory", {})
        if ctx and ctx.cfg else {}
    )
    return MemoryStore(
        workspace          = ctx.workspace if ctx else Path("."),
        memory_char_limit  = mconf.get("memory_char_limit", 2200),
        user_char_limit    = mconf.get("user_char_limit", 1375),
        scan_enabled       = mconf.get("scan_enabled", True),
    )


@register_tool(
    description=(
        "Save durable information to persistent memory that survives across "
        "sessions. Two stores: 'memory' (your notes — environment facts, project "
        "conventions, lessons learned) and 'user' (the user's profile — name, "
        "preferences, communication style).\n\n"
        "WHEN TO SAVE (do it proactively, don't wait to be asked):\n"
        "- The user shares a preference, habit, or personal detail\n"
        "- You correct a wrong assumption\n"
        "- You discover a stable fact about the environment or a convention\n\n"
        "Do NOT save task progress or temporary TODO state.\n\n"
        "ACTIONS:\n"
        "- add: append a new entry (content)\n"
        "- replace: update an existing entry (old_text identifies it, content is the new text)\n"
        "- remove: delete an entry (old_text identifies it)\n\n"
        "Keep entries compact. If an add overflows the store limit, the error "
        "returns current entries + usage — consolidate with replace/remove, then "
        "retry the add in the same turn."
    ),
    parameters={
        "type":     "object",
        "required": ["action", "target"],
        "properties": {
            "action": {
                "type":        "string",
                "enum":        ["add", "replace", "remove"],
                "description": "What to do with the memory entry.",
            },
            "target": {
                "type":        "string",
                "enum":        ["memory", "user"],
                "description": "'memory' = agent notes, 'user' = user profile.",
            },
            "content": {
                "type":        "string",
                "description": "New entry text. Required for add and replace.",
            },
            "old_text": {
                "type":        "string",
                "description": "Substring identifying the entry to replace or remove.",
            },
        },
    },
)
def memory(
    action: str,
    target: str = "memory",
    content: Optional[str] = None,
    old_text: Optional[str] = None,
    _ctx: ToolContext = None,
) -> str:
    if target not in ("memory", "user"):
        return f"[TOOL ERROR] Invalid target '{target}'. Use 'memory' or 'user'."
    if action not in ("add", "replace", "remove"):
        return f"[TOOL ERROR] Invalid action '{action}'. Use: add, replace, remove."

    store = _store_for(_ctx)
    store.load_from_disk()

    if action == "add":
        result = store.add(target, content or "")
    elif action == "replace":
        result = store.replace(target, old_text or "", content or "")
    else:
        result = store.remove(target, old_text or "")

    return json.dumps(result, ensure_ascii=False)


@register_tool(
    description=(
        "Read the current persistent memory (MEMORY.md = your notes, USER.md = "
        "the user profile). The same content is injected into the system prompt "
        "at session start; call this to see the LIVE state including anything "
        "saved mid-session."
    ),
    parameters={"type": "object", "properties": {}},
)
def read_user_memory(_ctx: ToolContext = None) -> str:
    store = _store_for(_ctx)
    store.load_from_disk()
    parts = []
    for target, label in (("memory", "MEMORY.md (agent notes)"),
                          ("user", "USER.md (user profile)")):
        entries = store.entries(target)
        if not entries:
            parts.append(f"# {label}\n(empty)")
            continue
        parts.append(f"# {label}\n" + "\n".join(f"- {e}" for e in entries))
    return "\n\n".join(parts)
