# Installation

## Prerequisites

| Dependency | Min. Version | Purpose |
|-----------|--------------|---------|
| Python    | >= 3.10      | Backend server & agent framework |
| Godot 4   | >= 4.0       | Desktop character UI |

---

## Linux

### Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Godot 4

Download from [godotengine.org](https://godotengine.org/download):

```bash
# After downloading, make it executable
chmod +x ~/Downloads/Godot_v4*-linux.x86_64

# Optional: move to a PATH-accessible location
sudo cp ~/Downloads/Godot_v4*-linux.x86_64 /usr/local/bin/godot
```

Or install via package manager (if available for your distro).

---

## macOS

### Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Godot 4

Download from [godotengine.org](https://godotengine.org/download) — choose the macOS version.

---

## Windows

### Python

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Godot 4

Download from [godotengine.org](https://godotengine.org/download) — choose the Windows version.

---

## Clone & Setup

### One-Command Setup (Recommended)

```bash
git clone --recurse-submodules https://github.com/MithilSaiReddy/Tanu
cd Tanu
bash setup.sh
```

Or on Windows PowerShell:

```powershell
git clone --recurse-submodules https://github.com/MithilSaiReddy/Tanu
cd Tanu
.\setup.ps1
```

The `setup.sh` / `setup.ps1` script handles everything: system dependencies, Python venv, submodules, and config.

### Manual Setup

```bash
git clone --recurse-submodules https://github.com/MithilSaiReddy/Tanu
cd Tanu
```

The `bujji/` submodule is included automatically with `--recurse-submodules`.
If you already cloned without it:

```bash
git submodule update --init --recursive
```

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
