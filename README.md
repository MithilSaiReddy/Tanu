# Tanu

**Voice assistant software for DeskBot**

A calm, sharp, slightly witty personal assistant that runs on DeskBot hardware. Tanu listens with whisper.cpp, thinks with any LLM, and speaks with piper TTS.

---

## What is Tanu?

Tanu is voice assistant software designed for DeskBot — an open-source hardware assistant. It runs locally with no cloud dependencies after initial setup.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Tanu Voice Pipeline                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Microphone ──► webrtcvad ──► whisper.cpp ──► text        │
│                        (voice activation detection)   (STT) │
│                                                             │
│   text ──► LLM (any OpenAI-compatible) ──► response        │
│                          (brain)                            │
│                                                             │
│   response ──► piper (TTS) ──► speaker                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Key Features

- **Voice Activation** — webrtcvad detects speech, starts recording
- **Speech-to-Text** — whisper.cpp runs locally, low latency
- **AI Brain** — Any OpenAI-compatible LLM (OpenAI, Anthropic, Google, Groq, Ollama, DeepSeek)
- **Text-to-Speech** — piper neural TTS, runs locally
- **Tasks** — Create, list, complete, update, delete tasks
- **Reminders** — Set, list, cancel reminders (voice/Telegram/Discord notifications)
- **Email** — Gmail integration via OAuth2 (fetch, send, reply)
- **Quick Tools** — Time, timer, calculations, unit conversions

---

## Quick Start

### Prerequisites

```bash
# Python 3.9+
python --version

# Install core dependencies
pip install requests webrtcvad sounddevice piper-tts

# Optional for email
pip install google-auth google-auth-oauthlib google-api-python-client
```

### Build whisper.cpp (STT)

```bash
cd tools/whisper.cpp
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

Download a model:
```bash
# Example: tiny English model
curl -L -o models/ggml-tiny.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin
```

### Run Tanu

```bash
# First-time setup (configures LLM provider)
python main.py onboard

# Voice mode (requires microphone)
python main.py tanu

# Text mode (for testing without mic)
python main.py tanu --text

# Simulate mode (type instead of speak)
python main.py tanu --simulate
```

---

## Tanu Commands

| Command | Description |
|---------|-------------|
| `python main.py onboard` | First-time setup wizard |
| `python main.py tanu` | Start voice assistant |
| `python main.py tanu --text` | Text-only mode |
| `python main.py tanu --simulate` | Type to simulate voice |
| `python main.py serve` | Web UI (http://localhost:7337) |
| `python main.py agent` | Terminal chat |

---

## Configuration

Config lives in `bujji/bujji/config.py` or `~/.bujji/config.json`:

```json
{
  "active_provider": "openrouter",
  "providers": {
    "openrouter": {
      "api_key": "sk-or-...",
      "api_base": "https://openrouter.ai/api/v1"
    }
  },
  "deskbot": {
    "whisper_bin": "./tools/whisper.cpp/build/bin/main",
    "whisper_model": "./tools/whisper.cpp/models/ggml-tiny.en.bin",
    "whisper_threads": 4,
    "piper_bin": "./venv/bin/piper",
    "piper_model": "./tools/piper/en_US-lessac-medium.onnx"
  },
  "tanu": {
    "voice_enabled": true,
    "stream_tts": true
  }
}
```

### Config Options

| Option | Default | Description |
|--------|---------|-------------|
| `whisper_bin` | `~/whisper.cpp/main` | Path to whisper.cpp binary |
| `whisper_model` | `~/whisper.cpp/models/ggml-tiny.en.bin` | Path to whisper model |
| `whisper_threads` | 4 | CPU threads for whisper.cpp |
| `piper_bin` | `~/piper/piper` | Path to piper binary |
| `piper_model` | `~/piper/voices/en_US-lessac-medium.onnx` | Path to piper ONNX model |
| `audio_input_device` | None | Specific input device |
| `audio_output_device` | None | Specific output device |

---

## Tanu Tools

### Tasks (`tanu_task.py`)

```
You: Add task "Review PR" high priority
Tanu: Done. Created: Review PR

You: List my tasks
Tanu: You have 3 tasks. 2 pending, 1 completed.
  ○ Review PR (high)
  ○ Call mom
  ✓ Buy groceries
```

| Tool | Description |
|------|-------------|
| `tanu_create_task` | Create task with title, priority, due date |
| `tanu_list_tasks` | List all/pending/completed tasks |
| `tanu_complete_task` | Mark task complete (by ID or title) |
| `tanu_update_task` | Update title, priority, due date, notes |
| `tanu_delete_task` | Delete task permanently |

### Reminders (`tanu_reminder.py`)

```
You: Remind me to call mom at 5pm
Tanu: Reminder set for 5:00 PM.
```

| Tool | Description |
|------|-------------|
| `tanu_set_reminder` | Set reminder (voice/telegram/discord) |
| `tanu_list_reminders` | List upcoming/past reminders |
| `tanu_cancel_reminder` | Cancel reminder by ID |

Reminders trigger via:
- **Voice** — spoken through TTS
- **Telegram** — if configured
- **Discord** — if configured

### Email (`tanu_email.py`)

Setup:
1. Go to console.cloud.google.com
2. Create OAuth2 credentials (Desktop app)
3. Download as `bujji/bujji/credentials.json`
4. Run: `python main.py setup-gmail`

```
You: Check my emails
Tanu: You have 5 emails. 2 unread.
  ● John Smith | 10:30 AM
    Project update
  ○ Jane Doe | Yesterday
    Meeting notes
```

| Tool | Description |
|------|-------------|
| `tanu_fetch_emails` | Fetch recent emails |
| `tanu_send_email` | Send new email |
| `tanu_reply_email` | Reply to email |
| `tanu_mark_email` | Mark as read/unread |

### Quick Tools (`tanu_query.py`)

```
You: What's the time?
Tanu: It's 3:45 PM on Monday, April 07, 2026.

You: Set timer 30 minutes
Tanu: Timer set for 30 minutes.

You: Convert 100 kg to pounds
Tanu: 100 kg = 220.46 lbs

You: What's 15% of 200?
Tanu: 15% of 200 = 30
```

| Tool | Description |
|------|-------------|
| `tanu_get_time` | Current time and date |
| `tanu_set_timer` | Quick timer |
| `tanu_calc` | Simple calculations |
| `tanu_convert` | Unit conversions |

---

## Tanu's Personality

Defined by workspace markdown files:

- **SOUL.md** — Core purpose: reduce mental load, protect momentum
- **IDENTITY.md** — Calm, sharp, slightly witty, casual, direct
- **BACKSTORY.md** — Built from frustration with productivity apps
- **USER.md** — Learns your preferences
- **HEARTBEAT.md** — Periodic background tasks

### Response Style

**When working (tools used):**
- Keep it short. 1-2 sentences.
- "Task added." not "I have successfully added the task."
- "Reminder set for 3pm." not "I've set a reminder for 3pm."

**When chatting (no tools):**
- Be normal. Natural conversation.
- "Hey!" "Doing good." "Same here."

**When something breaks:**
- Say what broke. "Email failed - check connection."

---

## Hardware Requirements

### Minimum
- Raspberry Pi 4 or equivalent
- USB microphone
- 3.5mm or USB speaker
- 16GB+ SD card

### Tested On
- DeskBot hardware (custom)
- x86_64 Linux
- macOS

---

## Project Structure

```
tanu/
├── main.py                     # CLI entry point
│
├── bujji/bujji/
│   ├── agent.py                # Agent loop, heartbeat, cron
│   ├── llm.py                  # LLM provider (OpenAI-compatible)
│   ├── server.py               # Web UI server
│   ├── config.py               # Configuration defaults
│   ├── session.py              # Session management
│   │
│   ├── connections/
│   │   ├── deskbot.py          # Voice pipeline (STT→Agent→TTS)
│   │   ├── display.py          # Display UI (LCD/LED)
│   │   ├── telegram.py         # Telegram bot
│   │   └── discord.py          # Discord bot
│   │
│   └── tools/
│       ├── tanu_task.py        # Task management
│       ├── tanu_reminder.py   # Reminders + background worker
│       ├── tanu_email.py      # Gmail integration
│       ├── tanu_query.py       # Time, timer, calc, convert
│       ├── speak_tool.py       # TTS output
│       ├── base.py             # Tool registration system
│       ├── memory.py           # USER.md persistence
│       └── ...
│
├── tools/
│   ├── piper/                  # TTS models (ONNX)
│   │   └── en_US-lessac-medium.onnx
│   │
│   └── whisper.cpp/            # STT (build from source)
│       ├── build/bin/main      # Compiled binary
│       └── models/             # Model files
│
├── workspace/                  # Identity & memory files
│   ├── SOUL.md
│   ├── IDENTITY.md
│   ├── BACKSTORY.md
│   ├── USER.md
│   ├── AGENT.md
│   ├── HEARTBEAT.md
│   └── tanu/
│       ├── tasks.json
│       └── reminders.json
│
└── ui/
    └── index.html              # Web UI
```

---

## Custom Models

### Add Custom TTS Model

1. Download a piper ONNX model from [rhasspy/piper-models](https://rhasspy.github.io/piper-models/)
2. Place in `tools/piper/`
3. Update config:
   ```python
   # bujji/bujji/config.py line 63
   "piper_model": "/path/to/your/model.onnx"
   ```

### Add Custom STT Model

1. Download a whisper.cpp model from [ggerganov/whisper.cpp](https://github.com/ggerganov/whisper.cpp#supported-models)
2. Place in `tools/whisper.cpp/models/`
3. Update config:
   ```python
   # bujji/bujji/config.py line 60
   "whisper_model": "/path/to/your-model.bin"
   ```

---

## Development

### Adding New Tools

1. Create `bujji/tools/tanu_mytool.py`
2. Use `@register_tool` decorator
3. Save to workspace — auto-reloads

```python
from bujji.tools.base import ToolContext, param, register_tool

@register_tool(
    description="What this tool does",
    params=[param("arg", "Description")]
)
def my_tool(arg: str, _ctx: ToolContext = None) -> str:
    return "Result"
```

### Debug Mode

```bash
# Text mode shows all responses
python main.py tanu --text

# Simulate mode for testing
python main.py tanu --simulate

# Check logs
python main.py status
```

---

## Dependencies

| Package | Required | For |
|---------|----------|-----|
| `requests` | Yes | Core HTTP |
| `webrtcvad` | Yes | Voice activation |
| `sounddevice` | Yes | Audio input |
| `piper-tts` | Yes | TTS |
| `google-auth-*` | No | Gmail API |
| `google-api-python-client` | No | Gmail API |
| `discord.py` | No | Discord bot |
| `ddgs` | No | Web search |

---

## Credits

- **bujji** — Base agent framework
- **whisper.cpp** — STT by Georgi Gerganov
- **piper** — Neural TTS by Darren Rush
- **DeskBot** — Hardware project

---

## License

MIT