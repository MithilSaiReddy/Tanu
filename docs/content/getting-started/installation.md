# Installation

## Prerequisites

| Dependency | Min. Version | Purpose |
|-----------|--------------|---------|
| Python    | >= 3.10      | Backend server, agent framework & desktop UI |

The desktop UI uses Pygame (installed automatically via `requirements.txt`) —
no engine or editor download required.

Running on a single-board computer with a small SPI display?
See [SBC Panel Mode](../guide/sbc-panel.md).

---

## Linux

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## macOS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Windows

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

---

## Clone & Setup

### One-Command Setup (Recommended)

```bash
git clone https://github.com/MithilSaiReddy/Tanu
cd Tanu
bash setup.sh
```

Or on Windows PowerShell:

```powershell
git clone https://github.com/MithilSaiReddy/Tanu
cd Tanu
.\setup.ps1
```

The `setup.sh` / `setup.ps1` script handles everything: system dependencies, Python venv, and config.

### Manual Setup

```bash
git clone https://github.com/MithilSaiReddy/Tanu
cd Tanu
```

The Tanu agent framework lives directly in this repo under `src/tanu/`
— no submodules to initialize.

---

## Post-Install: Gmail (Optional)

```bash
pip install google-auth google-auth-oauthlib google-api-python-client
```

See [Gmail Integration](../guide/gmail-integration.md) for configuration.

---

## Post-Install: Voice (Optional)

For voice assistant mode (`python3 main.py tanu`):

```bash
# Linux
sudo apt install portaudio19-dev pulseaudio

# macOS
brew install portaudio

# Windows
# Included automatically with the Python package
```

```bash
pip install pyaudio sounddevice
```
