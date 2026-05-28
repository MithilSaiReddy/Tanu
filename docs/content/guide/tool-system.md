# Tool System

Tanu uses the bujji tool system — a registry of Python functions that the LLM
can invoke autonomously.

## Architecture

```
ToolRegistry
  │
  ├── Built-in tools (bujji/bujji/tools/)
  │   ├── file_ops.py       — read, write, append, list, delete files
  │   ├── shell.py          — execute shell commands
  │   ├── web.py            — Brave Search / web search
  │   ├── memory.py         — read/write USER.md
  │   ├── todo.py           — task breakdown & tracking
  │   ├── utils.py          — date, time, etc.
  │   └── subagents.py      — spawn sub-agents
  │
  └── Custom tools (src/tanu/tools/)
      ├── gmail.py          — Gmail: inbox, send, search, get
      ├── speak_tool.py     — Text-to-speech output
      ├── tanu_query.py     — Direct agent query
      ├── tanu_reminder.py  — Reminder scheduling
      └── tanu_task.py      — Task management
```

## How Tools Are Discovered

1. **`@register_tool` decorator** — Each tool function is decorated with metadata:
   ```python
   from bujji.tools.base import register_tool, param

   @register_tool(
       description="List recent emails from your Gmail inbox",
       params=[
           param("max_results", "Number of emails to return (default 10)", required=False),
       ],
   )
   def gmail_list_inbox(max_results: int = 10, _ctx: ToolContext = None) -> str:
       # ... implementation ...
   ```
2. **`_autodiscover()`** — Scans tool directories using `pkgutil.iter_modules()`,
   imports each module, which causes the decorators to fire and register in `_REGISTRY`
3. **`ToolRegistry`** — Collects all schemas and exposes them to the LLM via the
   system prompt

## Tool Discovery Paths

The config key `tool_paths` controls which directories are scanned:

```json
{
  "tool_paths": [
    {
      "path": "/absolute/path/to/tools",
      "package": "package.name"
    }
  ]
}
```

Tanu automatically injects `src/tanu/tools/` into `tool_paths` when you use
`python3 main.py desk` or `python3 main.py serve` (via `tanu.config.load_config()`).

## Writing a New Tool

### 1. Create the file

`src/tanu/tools/my_tool.py`:

```python
"""My custom tool."""

from bujji.tools.base import register_tool, param


@register_tool(
    description="Does something useful",
    params=[
        param("input_text", "The text to process", required=True),
        param("option", "Optional flag", required=False),
    ],
)
def my_useful_tool(input_text: str, option: str = "", _ctx: ToolContext = None) -> str:
    """Implement the tool logic here."""
    result = f"Processed: {input_text}"
    return result
```

### 2. Register discovery

If your tool is in `src/tanu/tools/`, it's auto-discovered. No extra setup needed.

### 3. The LLM sees it

The next time you chat, the LLM will have `my_useful_tool` available and can
call it when relevant.

## Tool Contract

- Each tool receives a `ToolContext` (`_ctx`) with access to workspace paths, config, etc.
- Tools must return a string (result or error message)
- Tools should be pure functions (no side effects beyond their documented purpose)
- Errors should be returned as strings, not raised as exceptions

## Built-in Tools Reference

| Tool | Module | Description |
|------|--------|-------------|
| `read_file` | `file_ops` | Read a file from workspace |
| `write_file` | `file_ops` | Write/overwrite a file |
| `append_file` | `file_ops` | Append to a file |
| `list_files` | `file_ops` | List directory contents |
| `delete_file` | `file_ops` | Delete a file |
| `shell` | `shell` | Execute shell command |
| `web_search` | `web` | Brave Search or mock search |
| `read_memory` | `memory` | Read USER.md |
| `write_memory` | `memory` | Write USER.md |
| `create_todo` | `todo` | Create task breakdown |
| `next_todo` | `todo` | Mark complete, get next task |
| `send_message` | `utils` | Send message to user |
| `get_date` | `utils` | Current date and time |
| `spawn_subagent` | `subagents` | Delegate to sub-agent |
