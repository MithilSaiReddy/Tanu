# Tauri Desktop App

## Project Structure

```
src/ui/
├── index.html            # Entry point (all UI in one file)
├── main.js               # All frontend logic
├── styles.css            # All styles
├── assets/
│   └── 1.svg             # Logo
└── src-tauri/
    ├── Cargo.toml         # Rust dependencies
    ├── tauri.conf.json    # Tauri configuration
    ├── capabilities/
    │   └── default.json   # Permission grants
    ├── icons/             # App icons
    └── src/
        └── lib.rs         # Rust backend commands
```

## Window Modes

### Float Mode
- Size: 60×60 (circular)
- `set_resizable(false)`
- Movable via native drag (pointerdown on circle)
- Click opens chat mode

### Chat Mode
- Size: 400×600 (default), max 900×1000
- `set_resizable(true)`, clamped to min 300×400
- Header drag moves window
- Close button (_) returns to float mode

## Adding New Rust Commands

Define a new function in `lib.rs` with `#[tauri::command]`:

```rust
#[tauri::command]
async fn my_command(window: WebviewWindow) -> Result<String, String> {
    // ... logic ...
    Ok("result".into())
}
```

Register it in `invoke_handler`:

```rust
.invoke_handler(tauri::generate_handler![
    toggle_mode, set_chat, set_floating,
    start_native_drag, get_mode, open_url_in_browser,
    my_command     // <-- add here
])
```

Add the permission in `capabilities/default.json` if it needs core permissions.

## Calling from Frontend

```javascript
const { invoke } = window.__TAURI__.core;
const result = await invoke("my_command", { arg1: "value" });
```

## Window Clamping

The `clamp_to_screen()` function in `lib.rs` prevents the window from going
off-screen after a drag or mode switch:

```rust
fn clamp_to_screen(window: &WebviewWindow) {
    if let Some(monitor) = window.current_monitor().ok().flatten() {
        let monitor_bounds = monitor.size();
        // ... clamp position to stay ≥ MARGIN px from edges
    }
}
```

## Server Sidecar

On startup, `lib.rs` spawns the Python server as a Tauri sidecar:

```rust
let sidecar = app.shell().sidecar("tanu").unwrap();
let (mut rx, child) = sidecar.spawn().unwrap();
app.manage(ServerHandle(Mutex::new(Some(child))));
```

It polls `http://localhost:7337/api/status` every 500ms. Once the server
responds, the window is shown. On tray "Quit", the sidecar process is killed.

The sidecar binary is built with PyInstaller (`scripts/build_server.py`) and
placed in `src/ui/src-tauri/binaries/tanu-{target-triple}` by the build script.
Tauri bundles it automatically via `externalBin` in `tauri.conf.json`.

## Hotkey

Ctrl+Shift+T is registered in `setup()` via `tauri-plugin-global-shortcut`.
Pressing it calls `toggle_mode` on the Rust side, which emits a `mode-changed`
event that the frontend listens for.
