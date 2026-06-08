# Installation

## Prerequisites

| Dependency | Min. Version | Purpose |
|-----------|--------------|---------|
| Python    | ≥ 3.10       | Backend server & agent framework |
| Rust      | ≥ 1.77       | Compile Tauri v2 native binary |
| systemd   | ≥ 250        | `systemd-run --user` (Linux only — escapes snap sandbox) |

---

## Linux

### System Dependencies

Choose your distribution:

=== "Debian / Ubuntu"

    ```bash
    sudo apt update
    sudo apt install build-essential libwebkit2gtk-4.1-dev \
      libgtk-3-dev libayatana-appindicator3-dev \
      librsvg2-dev libsoup-3.0-dev libjavascriptcoregtk-4.1-dev
    ```

=== "Fedora"

    ```bash
    sudo dnf groupinstall "C Development Tools and Libraries"
    sudo dnf install webkit2gtk4.1-devel gtk3-devel \
      libappindicator-gtk3-devel librsvg2-devel \
      libsoup3-devel javascriptcoregtk4.1-devel
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S base-devel webkit2gtk-4.1 gtk3 \
      libappindicator-gtk3 librsvg libsoup3
    ```

=== "openSUSE"

    ```bash
    sudo zypper install -t pattern devel_basis
    sudo zypper install webkit2gtk4_1-devel gtk3-devel \
      libappindicator-gtk3-devel librsvg-devel \
      libsoup3-devel javascriptcoregtk4_1-devel
    ```

### Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Rust / Tauri CLI

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
cargo install tauri-cli --version "^2"
```

---

## macOS

### System Dependencies

Install [Xcode Command Line Tools](https://developer.apple.com/xcode/resources/):

```bash
xcode-select --install
```

### Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Rust / Tauri CLI

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
cargo install tauri-cli --version "^2"
```

### Homebrew (Alternative)

```bash
brew install python rust
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cargo install tauri-cli --version "^2"
```

> **Note**: macOS uses `webkit2gtk` via the system WebKit framework — no extra
> libraries needed. However, some Python packages with native extensions may
> require Xcode tools.

---

## Windows

### System Dependencies

1. Install **Microsoft Visual Studio Build Tools** (or Visual Studio 2022 with
   the "Desktop development with C++" workload):
   - Download from [visualstudio.microsoft.com](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022)
   - During install, select: **Desktop development with C++**
   - Include the **Windows 10/11 SDK**

2. **WebView2** — included by default on Windows 10 (build 1803+) and Windows 11.
   On older builds, install from [Microsoft](https://developer.microsoft.com/en-us/microsoft-edge/webview2/).

### Python

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Rust / Tauri CLI

```powershell
# Install Rust via rustup
winget install Rustlang.Rustup
# Or manually: https://rustup.rs

# Then:
cargo install tauri-cli --version "^2"
```

> **Troubleshooting**: If you see `link.exe` not found, ensure Visual Studio
> Build Tools are installed and restart your terminal. Use the "Developer
> Command Prompt for VS 2022" if needed.

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

The `setup.sh` / `setup.ps1` script handles everything: system dependencies, Rust + Tauri CLI, Python venv, submodules, and config.

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
