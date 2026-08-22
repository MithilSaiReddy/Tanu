# Configuration

Tanu uses a JSON configuration file located at `~/.tanu/config.json`.

## Configuration File Location

The active configuration is always `~/.tanu/config.json`. Run
`python3 main.py onboard` to create or update it.

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
      "workspace": "workspace",
      "restrict_to_workspace": true
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
| `mistral` | `mistral-large-latest` | Mistral AI |
| `groq` | `llama-3.3-70b-versatile` | Fast inference API |
| `gemini` | `gemini-2.5-flash` | Google Gemini (OpenAI-compatible endpoint) |
| `deepseek` | `deepseek-chat` | DeepSeek |
| `xai` | `grok-3` | xAI Grok |
| `together` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | Together AI |
| `cerebras` | `llama-3.3-70b` | Cerebras |
| `perplexity` | `llama-3.1-sonar-large-128k-online` | Perplexity |

### `agents.defaults`

| Key | Description |
|-----|-------------|
| `model` | Model string sent to the provider |
| `workspace` | Absolute path or path relative to the repository root |
| `restrict_to_workspace` | Keep file and shell tools inside the workspace (recommended) |

### `tools`

Tool-specific configuration:

- **`web.search`** — Brave Search API key (optional; falls back to mock search)
- **`gmail.client_creds`** — Stringified JSON of a Google Cloud OAuth desktop client credential

### `tool_paths`

An array of directories that `ToolRegistry` auto-discovers for additional tools.
Tanu's `src/tanu/tools/` is injected automatically when using `tanu.config.load_config()`.
