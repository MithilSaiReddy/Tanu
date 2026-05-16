# Tanu Desktop App (Tauri)

Floating desktop assistant — always-on-top circle expands into a chat panel.

## Quick Start

### 1. Install system dependencies

```bash
sudo apt install build-essential libwebkit2gtk-4.1-dev libgtk-3-dev \
  libayatana-appindicator3-dev librsvg2-dev libsoup-3.0-dev \
  libjavascriptcoregtk-4.1-dev
```

### 2. Build

```bash
cd src/ui
cargo tauri build
```

### 3. Run

```bash
python main.py desk
```

This starts the Python server (`localhost:7337`) and launches the Tauri app.

## Usage

| Action | What happens |
|--------|-------------|
| **Click the circle** | Chat panel opens |
| **Press Ctrl+Shift+T** | Toggle between floating circle and chat |
| **Click `_` in header** | Minimize back to circle |
| **Type + Enter** | Send message to Tanu |

## Hotkey

`Ctrl+Shift+T` — toggle between floating circle mode and chat mode.
