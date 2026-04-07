# Tanu

**Voice assistant software for DeskBot**

A calm, sharp, slightly witty personal assistant that runs on DeskBot hardware. Tanu listens with whisper.cpp, thinks with any LLM, and speaks with piper TTS.

---

## What is Tanu?

Tanu is voice assistant software designed for DeskBot — an open-source hardware assistant. It runs locally with no cloud dependencies after initial setup.

**Core philosophy:** Tanu doesn't try to impress. Tanu tries to be useful.

### How it works

```
You speak
    │
    ▼
whisper.cpp (STT) ──► LLM (any OpenAI-compatible) ──► piper (TTS) ──► You hear
```

- **STT:** whisper.cpp — runs locally, low latency
- **LLM:** OpenAI, Anthropic, Google, Groq, Ollama, DeepSeek, or any OpenAI-compatible API
- **TTS:** piper — neural TTS, runs locally

---

## Quick Start

### Prerequisites

```bash
# Python 3.9+
python --version

# Install dependencies
pip install requests webrtc-noise-gainanced piper-tts
```

### Build whisper.cpp (STT)

```bash
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
# Download a model: https://github.com/ggerganov/whisper.cpp#supported-models
```

### Run Tanu

```bash
# First-time setup
python main.py onboard

# Voice mode
python main.py tanu

# Text mode (for testing)
python main.py tanu --text
```

---

## Tanu Tools

Tanu has specialized tools beyond standard bujji:

| Tool | Description |
|------|-------------|
| `tanu_task_*` | Create, list, complete, update, delete tasks |
| `tanu_reminder_*` | Set, list, cancel reminders |
| `tanu_email_*` | Fetch, send, reply to email (Gmail OAuth) |
| `tanu_query_*` | Ask questions, get answers |
| `get_time` | Current date and time |
| `speak` | Text-to-speech output |

### Task Example

```
You: Add task "Review PR" high priority
Tanu: Task added. #1 Review PR (high)
```

### Reminder Example

```
You: Remind me to call mom at 5pm
Tanu: Reminder set for 5:00 PM
```

---

## Configuration

Config lives at `~/.bujji/config.json` or `bujji/bujji/config.json`:

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
    "whisper_bin": "./whisper.cpp/build/bin/main",
    "whisper_model": "./whisper.cpp/models/ggml-tiny.en.bin",
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

### Environment Variables

| Variable | Description |
|----------|-------------|
| `WHISPER_BIN` | Path to whisper.cpp binary |
| `WHISPER_MODEL` | Path to whisper model file |
| `PIPER_MODEL` | Path to piper ONNX model |

---

## Tanu's Personality

Tanu is defined by workspace files:

- **SOUL.md** — Core purpose: reduce mental load
- **IDENTITY.md** — Calm, sharp, slightly witty
- **BACKSTORY.md** — Built from frustration with productivity apps
- **USER.md** — Learns your preferences
- **HEARTBEAT.md** — Periodic background tasks

### Response Style

**When working:**
- Keep it short. 1-2 sentences.
- "Task added." not "I have successfully added the task."
- "Reminder set for 3pm." not "I've set a reminder for 3pm."

**When chatting:**
- Be normal. Natural conversation.
- "Hey!" "Doing good." "Same here."

**When something breaks:**
- Say what broke. "Email failed - check connection."

---

## Hardware

Tanu runs on DeskBot — an open-source voice assistant hardware project.

### Recommended Setup

- **CPU:** Raspberry Pi 4 or equivalent
- **Mic:** USB microphone or AIY Voice Kit
- **Speaker:** 3.5mm jack or USB speaker
- **Storage:** 16GB+ SD card

---

## Development

### Project Structure

```
tanu/
├── main.py                 # CLI entry point
├── bujji/
│   ├── agent.py            # Agent loop, heartbeat, cron
│   ├── llm.py              # LLM provider
│   ├── server.py           # Web UI server
│   ├── connections/
│   │   └── deskbot.py      # Voice pipeline (STT→Agent→TTS)
│   └── tools/
│       ├── tanu_task.py    # Task management
│       ├── tanu_reminder.py # Reminders
│       ├── tanu_email.py  # Gmail integration
│       └── speak_tool.py  # TTS output
├── tools/
│   ├── piper/              # TTS models
│   └── whisper.cpp/        # STT (build from source)
└── workspace/              # Identity & memory files
```

### Add Custom TTS Model

1. Download a piper ONX model
2. Place in `tools/piper/`
3. Update `deskbot.piper_model` in config

### Add Custom STT Model

1. Download a whisper.cpp model
2. Place in `tools/whisper.cpp/models/`
3. Update `deskbot.whisper_model` in config

---

## Commands

| Command | Description |
|---------|-------------|
| `python main.py onboard` | First-time setup |
| `python main.py tanu` | Start voice assistant |
| `python main.py tanu --text` | Text-only mode |
| `python main.py tanu --simulate` | Type instead of speak |
| `python main.py serve` | Web UI |
| `python main.py agent` | Terminal chat |

---

## Credits

- **bujji** — Base agent framework
- **whisper.cpp** — STT by Georgi Gerganov
- **piper** — Neural TTS by Darren Rush
- **DeskBot** — Hardware project

---

## License

MIT