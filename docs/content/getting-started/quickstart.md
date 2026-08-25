# Quick Start

## 0. Setup Environment

Run the setup script to install system dependencies and the Python venv:

```bash
bash setup.sh
```

Or on Windows PowerShell:

```powershell
.\setup.ps1
```

See [Installation](installation.md) for manual setup.

## 1. Configure LLM Provider

Run the onboarding wizard:

```bash
python3 main.py onboard
```

It will prompt for your preferred provider and API key. Or edit `~/.tanu/config.json`
directly (see [Configuration](configuration.md)).

## 2. Install Gmail Dependencies (Optional)

```bash
pip install google-auth google-auth-oauthlib google-api-python-client
```

## 3. Launch

### Desktop Mode (Pygame Character + Chat)

```bash
python3 main.py desk
```

This starts the Python server and opens the Pygame character window. The client connects
to the server via WebSocket automatically.

On an SBC with a small SPI TFT (no X11), render straight to the framebuffer:

```bash
python3 main.py desk --panel
```

See [SBC Panel Mode](../guide/sbc-panel.md) for wiring and kernel setup.

### Web UI Only

```bash
python3 main.py serve
```

Then open `http://localhost:7337` in a browser.

### Terminal Chat

```bash
python3 main.py agent
```

## 4. Usage

Once the desktop app is running:

| Action | Result |
|--------|--------|
| Type a message + Enter/Send | Send to the LLM |
| Watch the character | Animates through idle → thinking → speaking states |
| Status bar | Shows connection status and current state |

### Gmail Setup

See [Gmail Integration](../guide/gmail-integration.md) for setting up email access.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|------|
| "Connecting..." stuck | Server not running | Ensure `python3 main.py desk` is running |
| No response to messages | WebSocket not connected | Check server is running on port 7337 |
| Missing pygame / websocket | Deps not installed | Run `pip install -r requirements.txt` |
| Gmail tools not found by LLM | `tool_paths` not injected | Use `python3 main.py desk` (not `main.py serve` alone) |
