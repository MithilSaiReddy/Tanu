# Configuration

Tanu uses a JSON configuration file located at `~/.tanu/config.json`.

## Configuration File Location

| Source | Path |
|--------|------|
| Default config | `~/.tanu/config.json` |
| Project config | `config/config.json` (in repo root) |

The config is loaded from `~/.tanu/config.json`. During development you may copy
`config/config.json` to `~/.tanu/config.json`.

## Structure

```json
{
  "providers": {
    "openrouter": {
      "api_key": "sk-or-...",
      "api_base": "https://openrouter.ai/api/v1"
    }
  },
  "active_provider": "openrouter",
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o",
      "workspace": "/home/user/Documents/Tanu/src/Tanu/workspace"
    }
  },
  "tools": {
    "web": {
      "search": {
        "api_key": "",
        "max_results": 5
      }
    },
    "gmail": {
      "client_creds": "{... OAuth client JSON ...}"
    }
  },
  "tool_paths": [
    {
      "path": "/home/user/Documents/Tanu/src/Tanu/src/tanu/tools",
      "package": "tanu.tools"
    }
  ]
}
```

## Key Sections

### `providers`

LLM provider configurations. Supports any OpenAI-compatible API.

| Provider | Default Model | Notes |
|----------|---------------|-------|
| `openrouter` | `openai/gpt-4o` | Recommended |
| `openai` | `gpt-4o` | Direct OpenAI |
| `ollama` | `llama3` | Local, no `api_key` needed |
| `anthropic` | `claude-3-5-sonnet-latest` | Anthropic |

### `agents.defaults`

| Key | Description |
|-----|-------------|
| `model` | Model string sent to the provider |
| `workspace` | Absolute path to the workspace directory |

### `tools`

Tool-specific configuration:

- **`web.search`** — Brave Search API key (optional; falls back to mock search)
- **`gmail.client_creds`** — Stringified JSON of a Google Cloud OAuth desktop client credential

### `tool_paths`

An array of directories that `ToolRegistry` auto-discovers for additional tools.
Tanu's `src/tanu/tools/` is injected automatically when using `tanu.config.load_config()`.
