"""
tanu/context.py  —  lightweight context management.

Keeps the conversation window within budget:
  • Phase 1: prune old, verbose tool outputs (free — no LLM call)
  • Phase 2: pick a compression boundary without splitting tool groups
  • Phase 3: optional structured summarization of the middle turns
  • Phase 4: reassemble + sanitize orphaned tool call/result pairs

No tokenizer dependency — we estimate cost by character length
(~4 chars/token) which is good enough for triggering thresholds.
"""
from __future__ import annotations

from typing import Callable, Optional

TOOL_PRUNE_MARKER = "[Old tool output cleared to save context space]"

SUMMARY_TEMPLATE = """\
## Goal
[What the user is trying to accomplish]

## Constraints & Preferences
[User preferences, constraints, important decisions]

## Progress
### Done
### In Progress
### Blocked

## Key Decisions

## Relevant Files

## Next Steps

## Critical Context
[Specific values, error messages, configuration details]
"""

_SUMMARY_SYSTEM = (
    "You are a conversation summarizer for a lightweight AI assistant. "
    "Produce concise, structured summaries that preserve all facts the "
    "assistant still needs to finish the task."
)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _content_str(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # anthropic-style blocks
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return " ".join(parts)
    return str(content)


def _msg_len(m: dict) -> int:
    n = len(_content_str(m.get("content")))
    for tc in m.get("tool_calls") or []:
        n += len(_content_str(tc.get("function", {}).get("arguments")))
        n += len(tc.get("function", {}).get("name", ""))
    return n


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

def estimate_chars(messages: list) -> int:
    """Rough character cost of a message list (system + history + tools)."""
    return sum(_msg_len(m) for m in messages)


def prune_old_tool_outputs(
    messages: list,
    protect_last_n: int = 8,
    min_len: int = 200,
) -> list:
    """
    Phase 1 — replace verbose tool results outside the protected tail with a
    short marker. Cheap and lossless-enough for the assistant's needs.
    """
    out      = list(messages)
    tail_from = max(0, len(out) - protect_last_n)
    for i in range(tail_from):
        m = out[i]
        if m.get("role") == "tool" and _msg_len(m) > min_len:
            out[i] = {**m, "content": TOOL_PRUNE_MARKER}
    return out


def pick_boundary(
    messages: list,
    budget_chars: int,
    protect_last_n: int = 8,
    protect_first_n: int = 3,
) -> int:
    """
    Phase 2 — index at which the preserved tail begins.

    Walks backward from the end accumulating character cost until the budget
    is exceeded, then aligns the boundary so a tool_call/tool_result group is
    never split (the parent assistant message is pulled into the tail).
    """
    n = len(messages)
    if n <= protect_first_n + protect_last_n:
        return protect_first_n

    tail_start = n
    total      = 0
    for i in range(n - 1, -1, -1):
        ln = _msg_len(messages[i])
        if total + ln > budget_chars and (n - i) >= protect_last_n:
            tail_start = i + 1
            break
        total += ln

    if tail_start == n:  # everything fits (or budget too small) — fall back to count
        tail_start = max(protect_first_n, n - protect_last_n)

    # Align: never start the tail in the middle of a tool result run.
    while tail_start < n and messages[tail_start].get("role") == "tool":
        j = tail_start
        while j > protect_first_n and messages[j - 1].get("role") == "tool":
            j -= 1
        if j - 1 >= protect_first_n:
            tail_start = j - 1  # pull the parent assistant in with its results
        else:
            break

    return tail_start


def sanitize_tool_pairs(messages: list) -> list:
    """
    Phase 4 — drop tool results whose call was removed and inject stub results
    for calls whose result was removed.
    """
    referenced = set()
    for m in messages:
        for tc in m.get("tool_calls") or []:
            if tc.get("id"):
                referenced.add(tc["id"])

    out: list = []
    for m in messages:
        if m.get("role") == "tool" and m.get("tool_call_id") not in referenced:
            continue
        out.append(m)

    present = {m.get("tool_call_id") for m in out if m.get("role") == "tool"}
    final: list = []
    for m in out:
        final.append(m)
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                cid = tc.get("id")
                if cid and cid not in present:
                    final.append({
                        "role": "tool",
                        "tool_call_id": cid,
                        "content": TOOL_PRUNE_MARKER,
                    })
    return final


def render_conversation(messages: list) -> str:
    """Flatten a message list into a readable transcript for the summarizer."""
    lines: list[str] = []
    for m in messages:
        if m.get("role") == "system":
            continue
        role = m.get("role")
        if role == "tool":
            lines.append(f"[tool result]\n{_content_str(m.get('content'))}")
            continue
        content = _content_str(m.get("content"))
        calls   = m.get("tool_calls")
        if calls:
            names = [tc.get("function", {}).get("name", "") for tc in calls]
            lines.append(f"[{role} → tool: {', '.join(names)}]")
            if content:
                lines.append(content)
        elif content:
            lines.append(f"[{role}]\n{content}")
    return "\n\n".join(lines)


def build_summary_prompt(
    middle_messages: list,
    previous_summary: Optional[str] = None,
    max_summary_chars: int = 4000,
) -> list:
    """Phase 3 — build the LLM prompt for the structured middle summary."""
    if previous_summary:
        instruction = (
            f"An earlier section of this conversation was already summarized. "
            f"UPDATE the previous summary to fold in the new turns below, keeping "
            f"the same structure. Keep it under {max_summary_chars} characters; do "
            f"not repeat facts already captured.\n\n"
            f"PREVIOUS SUMMARY:\n{previous_summary}\n\n"
            f"NEW TURNS:\n"
        )
    else:
        instruction = (
            f"Summarize the conversation turns below using this exact structure, "
            f"keeping it under {max_summary_chars} characters:\n\n"
            f"{SUMMARY_TEMPLATE}\n\n"
            f"CONVERSATION:\n"
        )

    return [
        {"role": "system", "content": _SUMMARY_SYSTEM},
        {"role": "user", "content": instruction + render_conversation(middle_messages)},
    ]


def summarize_middle(
    middle_messages: list,
    summarize_fn: Callable[[list], Optional[str]],
    previous_summary: Optional[str] = None,
    max_summary_chars: int = 4000,
) -> Optional[str]:
    """
    Run the summarizer over the middle section. Returns None if the call
    failed (caller then falls back to pruning without a summary).
    """
    middle = [m for m in middle_messages if m.get("role") != "system"]
    if not middle:
        return None
    prompt = build_summary_prompt(middle, previous_summary, max_summary_chars)
    return summarize_fn(prompt)
