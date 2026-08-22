"""
tanu/tools/shell.py  —  v2
Shell execution with clean output, proper exit codes, and safe defaults.
"""
from __future__ import annotations

import subprocess
import threading

from tanu.tools.base import ToolContext, register_tool

@register_tool(
    description=(
        "Execute a shell command on the local system and return combined stdout + stderr. "
        "Use for system inspection, running scripts, installing packages, file manipulation, "
        "and anything that needs the host OS. "
        "Relative paths run from the workspace directory."
    ),
    parameters={
        "type":     "object",
        "required": ["command"],
        "properties": {
            "command": {
                "type":        "string",
                "description": "Shell command to run (passed to /bin/sh -c).",
            },
            "timeout": {
                "type":        "integer",
                "description": "Max seconds before the process is killed (default: 30, max: 300).",
            },
            "workdir": {
                "type":        "string",
                "description": (
                    "Working directory for the command. "
                    "Default: workspace root. "
                    "Use '.' to keep the workspace root."
                ),
            },
        },
    },
)
def exec(
    command: str,
    timeout: int = 30,
    workdir: str = ".",
    _ctx:    ToolContext = None,
) -> str:
    workspace = _ctx.workspace if _ctx else None
    restrict  = _ctx.restrict  if _ctx else False

    # Determine cwd
    if workspace:
        from pathlib import Path
        cwd_path = (workspace / workdir).resolve()
        if restrict:
            # Refuse paths outside workspace
            try:
                cwd_path.relative_to(workspace.resolve())
            except ValueError:
                return f"[TOOL ERROR] workdir '{workdir}' is outside the workspace."
        cwd = str(cwd_path)
    else:
        cwd = None

    # Cap timeout
    timeout = max(1, min(int(timeout), 300))

    output_limit = max(
        4096,
        min(
            int(
                (_ctx.cfg if _ctx else {}).get("agents", {}).get("defaults", {}).get(
                    "max_tool_output_chars", 6000
                )
            ),
            100_000,
        ),
    )
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    truncated = {"stdout": False, "stderr": False}

    def drain(pipe, buffer: bytearray, key: str) -> None:
        while True:
            chunk = pipe.read(4096)
            if not chunk:
                break
            remaining = output_limit - len(buffer)
            if remaining > 0:
                buffer.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated[key] = True

    try:
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        readers = [
            threading.Thread(target=drain, args=(process.stdout, stdout_buffer, "stdout"), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, stderr_buffer, "stderr"), daemon=True),
        ]
        for reader in readers:
            reader.start()
        try:
            return_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            for reader in readers:
                reader.join(timeout=1)
            process.stdout.close()
            process.stderr.close()
            return f"[TIMEOUT] Command killed after {timeout}s:\n  {command}"
        for reader in readers:
            reader.join(timeout=1)
        process.stdout.close()
        process.stderr.close()
    except Exception as e:
        return f"[ERROR] Could not run command: {e}"

    parts: list[str] = []

    stdout = stdout_buffer.decode("utf-8", errors="replace").strip()
    stderr = stderr_buffer.decode("utf-8", errors="replace").strip()
    if stdout:
        parts.append(stdout + ("\n[… stdout truncated …]" if truncated["stdout"] else ""))
    if stderr:
        suffix = "\n[… stderr truncated …]" if truncated["stderr"] else ""
        parts.append(f"[stderr]\n{stderr}{suffix}")
    if return_code != 0:
        parts.append(f"[exit code: {return_code}]")

    return "\n".join(parts) if parts else "(no output)"
