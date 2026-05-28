# Installation

## Prerequisites

| Dependency | Version | Purpose |
|-----------|---------|---------|
| Python    | ≥ 3.10  | Backend server & agent framework |
| Rust      | ≥ 1.77  | Tauri v2 native binary |
| Node.js   | ≥ 18    | Tauri frontend tooling (optional for build) |
| systemd   | ≥ 250   | `systemd-run --user` to escape snap mount namespaces |

## System Dependencies (Linux)

```bash
sudo apt install build-essential libwebkit2gtk-4.1-dev \
  libgtk-3-dev libayatana-appindicator3-dev \
  librsvg2-dev libsoup-3.0-dev libjavascriptcoregtk-4.1-dev
```

## Python Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Optional: Gmail

```bash
pip install google-auth google-auth-oauthlib google-api-python-client
```

## Rust / Tauri

```bash
cargo install tauri-cli --version "^2"
```

## Clone & Prepare

```bash
git clone --recurse-submodules https://github.com/MithilSaiReddy/Tanu
cd Tanu
```

The `bujji/` submodule is included automatically when you use `--recurse-submodules`.
If you already cloned without it:

```bash
git submodule update --init --recursive
```
