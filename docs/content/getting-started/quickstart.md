# Quick Start

## 0. Setup Environment

Run the setup script to install system dependencies, Python venv, and check for Godot:

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

It will prompt for your preferred provider and API key. Or edit `~/.bujji/config.json`
directly (see [Configuration](configuration.md)).

## 2. Install Gmail Dependencies (Optional)

```bash
pip install google-auth google-auth-oauthlib google-api-python-client
```

## 3. Build the Desktop App

### One-Command Build (Recommended)

```bash
bash build.sh
```

This exports the Godot project as a standalone binary in `build/tanu-godot`.

### Manual Build

Open the project in Godot editor and export:

```bash
godot --path src/godot
```

Then use **Project → Export** to create a standalone binary.

## 4. Launch

### Desktop Mode (Godot Character + Chat)

```bash
python3 main.py desk
```

This starts the Python server and launches the Godot client. The client connects
to the server via WebSocket automatically.

### Web UI Only

```bash
python3 main.py serve
```

Then open `http://localhost:7337` in a browser.

### Terminal Chat

```bash
python3 main.py agent
```

## 5. Usage

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
| Godot window not appearing | Binary not built | Run `bash build.sh` or export from Godot editor |
| No response to messages | WebSocket not connected | Check server is running on port 7337 |
| Gmail tools not found by LLM | `tool_paths` not injected | Use `python3 main.py desk` (not `main.py serve` alone) |
