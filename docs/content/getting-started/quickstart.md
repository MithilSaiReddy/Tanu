# Quick Start

## 1. Configure LLM Provider

Run the onboarding wizard:

```bash
python3 main.py onboard
```

It will prompt for your preferred provider and API key. Or edit `~/.bujji/config.json`
directly (see [Configuration](configuration.md)).

## 2. Build the Desktop App

```bash
cd src/ui
cargo tauri build
```

The binary is at `src/ui/src-tauri/target/release/tanu`.

## 3. Launch

### Desktop Mode (Floating Orb + Chat)

```bash
python3 main.py desk
```

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
|---------|-------------|-----|
| "Server offline" in status bar | Server not running | Ensure `python3 main.py desk` is running |
| Snap-related crash on launch | Running inside snap (ptyxis) | Fixed by `systemd-run --user --unit tanu --wait` (automatic) |
| Window goes off-screen | Outdated binary | Rebuild with `cargo tauri build` |
| Gmail auth URL fails (400) | `redirect_uri` not set on flow | Server now sets it explicitly (fixed in `server.py`) |
| Gmail token exchange fails (invalid_grant) | PKCE code_verifier mismatch | Server now caches the flow object (fixed) |
