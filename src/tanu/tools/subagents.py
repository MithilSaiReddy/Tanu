# tanu/tools/subagents.py
#
# Drop this file into tanu/tools/ — it's hot-reloaded automatically.
# No changes needed anywhere else in the codebase.
#
# Gives the main agent two new tools:
#   spawn_subagent  — run a one-shot task with a specialist agent
#   agent_pipeline  — run a chain of specialist agents, each feeding the next

from __future__ import annotations

import threading
from typing import Optional

from tanu.tools.base import ToolContext, register_tool

# ─────────────────────────────────────────────
# Internal helper
# ─────────────────────────────────────────────

def _run_subagent(
    role: str,
    task: str,
    ctx: ToolContext,
    extra_tools: list[str] | None = None,
    max_iterations: int = 10,
) -> str:
    """
    Spins up a fresh AgentLoop with a custom system prompt derived from `role`,
    runs `task` through it once, and returns the final text response.

    Imported lazily so the tool file stays loadable even before tanu.agent
    is fully initialised (e.g. during mtime hot-reload scan).
    """
    # Lazy import — keeps circular-import risk zero
    from tanu.agent import AgentLoop
    from tanu.config import workspace_path
    from tanu.identity import load_identity_block

    cfg = ctx.cfg

    # ── Shared context for the sub-agent ─────────────────────────────────────
    # Same SOUL/USER/AGENT files as the parent so it shares values, memory
    # and tool descriptions, but runs with its own role-focused system prompt.
    shared = load_identity_block(workspace_path(cfg))

    system_prompt = f"""You are a specialised sub-agent with the following role:

{role}

─── Shared context ───────────────────────────────
{shared}
──────────────────────────────────────────────────

Important rules:
- Focus ONLY on the task given to you.
- Be concise. Return a clear, structured result the parent agent can use.
- Do NOT ask clarifying questions — make your best attempt and explain
  any assumptions at the end.
"""

    # ── Spin up the child AgentLoop ─────────────────────────────────────────
    child = AgentLoop(
        cfg=cfg,
        max_iterations=min(
            max_iterations,
            int(cfg.get("agents", {}).get("defaults", {}).get("subagent_max_iterations", 20)),
        ),
        system_prompt_override=system_prompt,
        event_bus=ctx.event_bus,
        memory_budget=ctx.memory_budget,
    )

    return child.run(
        task,
        history=[],
        stream=False,
        auto_continue=False,
    )


# ─────────────────────────────────────────────
# Tool 1 — spawn_subagent
# ─────────────────────────────────────────────

@register_tool(
    description=(
        "Spawn a specialist sub-agent to handle a specific task. "
        "The sub-agent runs independently, has access to all the same tools, "
        "and returns a structured result. "
        "Use this to delegate focused work — research, coding, summarisation, "
        "planning, data analysis — while you orchestrate the bigger picture.\n\n"
        "Built-in role shortcuts (use exactly as shown, or write your own):\n"
        "  'researcher'  — web search, summarise, cite sources\n"
        "  'coder'       — write, review, or debug code\n"
        "  'planner'     — break a goal into ordered subtasks\n"
        "  'writer'      — draft documents, emails, or reports\n"
        "  'analyst'     — read files/data and extract insights\n"
        "  'memory'      — manage USER.md / MEMORY.md stores via the memory tool\n"
        "Or pass any free-form role description."
    ),
    parameters={
        "type": "object",
        "required": ["role", "task"],
        "properties": {
            "role": {
                "type": "string",
                "description": (
                    "Role or persona for the sub-agent. "
                    "Use a shortcut ('researcher', 'coder', 'planner', "
                    "'writer', 'analyst', 'memory') or write a custom description."
                ),
            },
            "task": {
                "type": "string",
                "description": (
                    "The complete, self-contained task for the sub-agent. "
                    "Include all context it needs — it has no memory of the "
                    "current conversation."
                ),
            },
            "max_iterations": {
                "type": "integer",
                "description": "Max tool-use iterations for the sub-agent (default: 10).",
                "default": 10,
            },
        },
    },
)
def spawn_subagent(
    role: str,
    task: str,
    max_iterations: int = 10,
    _ctx: ToolContext = None,
) -> str:
    if _ctx and _ctx.memory_budget and _ctx.memory_budget.pressure() != "normal":
        return "[TOOL ERROR] Sub-agent skipped while Tanu is under memory pressure."

    # ── Expand role shortcuts into full personas ─────────────────────────────
    ROLE_PRESETS = {
        "researcher": (
            "You are an expert researcher. Your job is to search the web, "
            "gather accurate information, and return a well-structured summary "
            "with key facts clearly separated. Always cite your sources."
        ),
        "coder": (
            "You are an expert software engineer. Write clean, well-commented "
            "code. If reviewing, identify bugs and suggest fixes with explanations. "
            "Always specify the language and any dependencies."
        ),
        "planner": (
            "You are a strategic planner. Break the given goal into a clear, "
            "numbered list of actionable subtasks in logical order. "
            "For each step note what tool or resource is needed."
        ),
        "writer": (
            "You are a professional writer and editor. Produce polished, "
            "well-structured documents. Match the requested tone and format. "
            "Proofread your output before returning it."
        ),
        "analyst": (
            "You are a data and document analyst. Read the provided files or data, "
            "extract key insights, identify patterns, and present findings clearly "
            "with supporting evidence."
        ),
        "memory": (
            "You are a memory manager. Your job is to read the current USER.md "
            "and MEMORY.md stores, identify new facts in the task, and persist "
            "them with the memory tool (add/replace/remove) without duplicating "
            "existing entries."
        ),
    }

    resolved_role = ROLE_PRESETS.get(role.lower().strip(), role)

    try:
        result = _run_subagent(
            role=resolved_role,
            task=task,
            ctx=_ctx,
            max_iterations=max_iterations,
        )
        return f"[Sub-agent: {role}]\n\n{result}"
    except Exception as e:
        return f"[TOOL ERROR] spawn_subagent failed: {e}"


# ─────────────────────────────────────────────
# Tool 2 — agent_pipeline
# ─────────────────────────────────────────────

@register_tool(
    description=(
        "Run a chain of sub-agents in sequence. "
        "Each agent's output is automatically passed as input to the next. "
        "Perfect for multi-step workflows: e.g. research → analyse → write report.\n\n"
        "Example stages:\n"
        '  [{"role": "researcher", "task": "Find recent AI news"},\n'
        '   {"role": "analyst",    "task": "Identify the 3 biggest trends from: {previous}"},\n'
        '   {"role": "writer",     "task": "Write a 200-word briefing from: {previous}"}]\n\n'
        "Use {previous} in a task string to insert the previous agent's output."
    ),
    parameters={
        "type": "object",
        "required": ["stages"],
        "properties": {
            "stages": {
                "type": "array",
                "description": "Ordered list of {role, task} objects. Use {previous} to pass prior output.",
                "items": {
                    "type": "object",
                    "required": ["role", "task"],
                    "properties": {
                        "role": {"type": "string"},
                        "task": {"type": "string"},
                        "max_iterations": {"type": "integer", "default": 10},
                    },
                },
            }
        },
    },
)
def agent_pipeline(
    stages: list[dict],
    _ctx: ToolContext = None,
) -> str:
    if not stages:
        return "[TOOL ERROR] agent_pipeline: stages list is empty."

    previous_output = ""
    log: list[str] = []

    for i, stage in enumerate(stages):
        role = stage.get("role", "assistant")
        task = stage.get("task", "")
        max_iter = stage.get("max_iterations", 10)

        # Inject previous output if the task references it
        if "{previous}" in task:
            task = task.replace("{previous}", previous_output)

        try:
            result = spawn_subagent(
                role=role,
                task=task,
                max_iterations=max_iter,
                _ctx=_ctx,
            )
            previous_output = result
            log.append(f"── Stage {i+1} [{role}] ──\n{result}")
        except Exception as e:
            error_msg = f"[TOOL ERROR] agent_pipeline stage {i+1} ({role}) failed: {e}"
            log.append(error_msg)
            break  # Stop pipeline on failure

    return "\n\n".join(log)
