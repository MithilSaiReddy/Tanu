# Quick Start

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

```bash
cd src/ui
cargo tauri build
```

The binary is at `src/ui/src-tauri/target/release/tanu`.

## 4. Launch

### Desktop Mode (Floating Orb + Chat)

```bash
python3 main.py desk
```

> **Important**: Always use `python3 main.py desk` (not running the Tauri binary
> directly) — this ensures the Python server starts, the config uses
> `tanu.config.load_config()` which injects `tool_paths` for tool discovery,
> and the binary escapes the snap sandbox via `systemd-run`.

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
| Click the floating orb | Opens the chat panel |
| Drag the orb | Moves the window |
| Drag the chat header | Moves the chat window |
| Ctrl+Shift+T | Toggle between float and chat mode |
| Gear icon (⚙) in chat header | Open settings |
| Type a message + Enter | Send to the LLM |

### Gmail Setup

See [Gmail Integration](../guide/gmail-integration.md) for setting up email access.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|------|
| "Server offline" in status bar | Server not running | Ensure `python3 main.py desk` is running |
| Snap-related crash at launch | Running inside ptyxis snap | Fixed automatically by `systemd-run --user --unit tanu --wait` |
| Tauri binary won't build | Missing system deps | `sudo apt install build-essential libwebkit2gtk-4.1-dev ...` |
| "text file busy" during rebuild | Old Tauri binary still running | `systemctl --user stop tanu && systemctl --user reset-failed tanu` |
| Gmail "400 invalid_request" | `redirect_uri` was `None` | Restart `desk` (server now sets it explicitly) |
| Gmail "invalid_grant" on Verify | PKCE verifier mismatch | Restart `desk` (server now caches the flow) |
| Gmail tools not found by LLM | `tool_paths` not injected | Use `python3 main.py desk` (not `main.py serve` alone) |
| Gmail "I don't have access" | Tools undiscovered or no token | Check `~/bujji/config.json` has `client_creds`, restart `desk` |
