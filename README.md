# Tanu 🎙️

**Voice assistant for DeskBot**

A calm, sharp, slightly witty personal assistant. Tanu listens with whisper.cpp, thinks with any LLM, and speaks with piper TTS.

---

## What is Tanu?

Tanu is voice assistant software for DeskBot hardware. It runs locally with minimal cloud dependencies after setup.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Tanu Voice Pipeline                     │
├─────────────────────────────────────────────────────────────┤
│   Microphone ──► webrtcvad ──► whisper.cpp ──► text        │
│                        (VAD)           (STT)            │
│                                                             │
│   text ──► LLM (any OpenAI-compatible) ──► response        │
│                          (brain)                          │
│                                                             │
│   response ──► piper (TTS) ──► speaker                    │
└─────────────────────────────────────────────────────────────┘
```

### Key Features

- **Voice Activation** — webrtcvad detects speech
- **Speech-to-Text** — whisper.cpp (local, low latency)
- **AI Brain** — Any OpenAI-compatible LLM
- **Text-to-Speech** — piper (local neural TTS)
- **Tasks** — Create, list, complete, update, delete
- **Reminders** — Set, list, cancel (voice/Telegram/Discord)

---

## Quick Start

### Installation

```bash
# Clone and enter folder
git clone https://github.com/MithilSaiReddy/Tanu.git
cd Tanu

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Tanu and bujji packages
pip install -e .
pip install -e bujji
```

### First Setup

```bash
# Configure LLM provider
python main.py onboard
```

### Run Tanu

```bash
# Voice mode
python main.py tanu

# Text mode (no microphone)
python main.py tanu --text

# Simulate mode (type input)
python main.py tanu --simulate
```

---

## Commands

| Command | Description |
|---------|-------------|
| `python main.py onboard` | First-time setup |
| `python main.py tanu` | Start voice assistant |
| `python main.py tanu --text` | Text-only mode |
| `python main.py tanu --simulate` | Type to simulate |
| `python main.py serve` | Web UI |
| `python main.py status` | Show status |

---

## Project Structure

```
tanu/
├── config/                  # Local configuration
│   └── config.json
├── workspace/              # Workspace files
│   └── tanu/             # Tanu identity files
├── src/tanu/              # Main package
│   ├── assets/           # whisper.cpp, piper
│   │   ├── whisper.cpp/
│   │   └── piper/
│   ├── plugins/           # Voice & integrations
│   │   ├── voice/        # deskbot
│   │   └── integrations/ # telegram, discord
│   └── tools/           # task, reminder
├── bujji/               # bujji framework
└── main.py              # CLI entry
```

---

## Configuration

Config is stored locally at `config/config.json`:

```json
{
  "active_provider": "mistral",
  "agents": {
    "defaults": {
      "workspace": "workspace"
    }
  },
  "providers": {
    "mistral": {
      "api_key": "your-key",
      "api_base": "https://api.mistral.ai/v1"
    }
  },
  "deskbot": {
    "whisper_bin": "src/tanu/assets/whisper.cpp/build/bin/main",
    "whisper_model": "src/tanu/assets/whisper.cpp/models/ggml-tiny.en.bin",
    "piper_model": "src/tanu/assets/piper/en_US-lessac-medium.onnx"
  }
}
```

---

## Customization

### Identity Files

Edit workspace files:
- `workspace/tanu/SOUL.md` — Core personality
- `workspace/tanu/IDENTITY.md` — User identity
- `workspace/tanu/USER.md` — User preferences

### Adding Tools

Tanu tools are in `src/tanu/tools/`:
- `tanu_task.py` — Task management
- `tanu_reminder.py` — Reminders
- `tanu_query.py` — Time, calculator

### Plugins

Add voice backends in `src/tanu/plugins/voice/`:
- `deskbot.py` — Current voice plugin

---

## Dependencies

### Core
- `requests` — HTTP client
- `webrtcvad` — Voice activity detection
- `sounddevice` — Audio input
- `piper-tts` — Text-to-speech

### Optional
- `google-auth`, `google-auth-oauthlib`, `google-api-python-client` — Gmail
- `discord.py` — Discord integration

---

## License

MIT