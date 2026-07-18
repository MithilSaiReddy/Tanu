# Building

## Release Build (Recommended)

Use the build script to export the Godot project as a standalone binary:

```bash
bash build.sh
```

Or on Windows PowerShell:

```powershell
.\build.ps1
```

The script:
1. Finds the Godot 4 binary in PATH or common install locations
2. Creates `export_presets.cfg` if missing
3. Runs `godot --headless --export-release` to produce a standalone binary
4. Places the output in `build/tanu-godot`

Platform-specific output in `build/`:

| Platform | Files |
|----------|-------|
| **Linux** | `tanu-godot` (x86_64 binary) |
| **macOS** | `tanu-godot.app` or `tanu-godot.dmg` |
| **Windows** | `tanu-godot.exe` |

## Manual Godot Export

Open the project in the Godot editor:

```bash
godot --path src/godot
```

Then use **Project → Export**:
1. Add a preset for your target platform (Linux, Windows, macOS)
2. Set the export path
3. Click **Export Project**

## Export Templates

Godot requires export templates to build standalone binaries. Install them via:

**Godot Editor → Manage Export Templates → Download**

Or manually download from [godotengine.org](https://godotengine.org/download) and place in:
- Linux: `~/.local/share/godot/export_templates/`
- macOS: `~/Library/Application Support/Godot/export_templates/`
- Windows: `%APPDATA%\Godot\export_templates\`

## Build Artifacts

The `build/` directory contains exported binaries. It's excluded from git via `.gitignore`.

## Troubleshooting

### "Export template not found"

Install Godot export templates via the editor (**Manage Export Templates → Download**).

### "Godot not found in PATH"

Either add Godot to your PATH or specify the path:

```bash
GODOT=/path/to/godot bash build.sh
```

### Export fails with errors

Open the project in the Godot editor (`godot --path src/godot`) and check for
scene/script errors before exporting.
