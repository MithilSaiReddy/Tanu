# Building

## Release Build

Build the Tauri desktop app:

```bash
cd src/ui
cargo tauri build
```

This produces:
- `src/ui/src-tauri/target/release/tanu` — the binary
- `src/ui/src-tauri/target/release/bundle/deb/Tanu_0.1.0_amd64.deb` — Debian package
- `src/ui/src-tauri/target/release/bundle/rpm/Tanu-0.1.0-1.x86_64.rpm` — RPM package
- `src/ui/src-tauri/target/release/bundle/appimage/Tanu_0.1.0_amd64.AppImage` — AppImage

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
