# Building

## Release Build (Recommended)

Use the build script to produce a single installer with the Python server bundled as a sidecar:

```bash
bash build.sh
```

Or on Windows PowerShell:

```powershell
.\build.ps1
```

The script:
1. Builds the Python server into a standalone binary (PyInstaller)
2. Copies it to `src/ui/src-tauri/binaries/` (Tauri sidecar convention)
3. Runs `cargo tauri build` (bundles the sidecar into the installer)
4. Copies all artifacts to `binary/` at the project root

Platform-specific output in `binary/`:

| Platform | Files |
|----------|-------|
| **Linux** | `Tanu_0.1.0_amd64.deb`, `Tanu-0.1.0-1.x86_64.rpm`, `Tanu_0.1.0_amd64.AppImage`, `tanu` (raw binary) |
| **macOS** | `Tanu_0.1.0_x64.dmg` (or `aarch64` on Apple Silicon) |
| **Windows** | `Tanu_0.1.0_x64.msi` or `Tanu_0.1.0_x64-setup.exe` |

## Manual Tauri Build (No Sidecar)

Build just the Tauri desktop app (without bundling the Python server):

```bash
cd src/ui
cargo tauri build
```

The binary is at `src/ui/src-tauri/target/release/tanu`.  
Run it with `python3 main.py desk` (the Python server must be started separately).

## Debug Build

```bash
cd src/ui
cargo tauri build --debug
```

Or for development with hot-reload:

```bash
cd src/ui
cargo tauri dev
```

This starts a dev server for the frontend (changes to HTML/CSS/JS are reflected
immediately) and launches the Tauri window.

## Build Artifacts

The `src/ui/src-tauri/target/` directory contains all Rust build artifacts.
It can exceed 2 GB after a release build. It's excluded from git via `.gitignore`.

## Troubleshooting

### "text file busy" during build

The previous Tauri binary is still running:

```bash
systemctl --user stop tanu
systemctl --user reset-failed tanu
```

Then retry the build.

### Missing libraries

Ensure system dependencies are installed (see [Installation](../getting-started/installation.md)).

### Tauri CLI not found

```bash
cargo install tauri-cli --version "^2"
```
