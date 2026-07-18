#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GODOT_DIR="$SCRIPT_DIR/src/godot"
BUILD_DIR="$SCRIPT_DIR/build"

echo "==> Building Tanu Desktop App (Godot)"
echo ""

# Find Godot binary
GODOT=""
for bin in godot godot4; do
    if command -v "$bin" &>/dev/null; then
        GODOT="$bin"
        break
    fi
done

# Check common install paths
if [ -z "$GODOT" ]; then
    for path in \
        "$HOME/Documents/Godot_v4"*"linux.x86_64" \
        "$HOME/.local/bin/godot" \
        "/usr/local/bin/godot" \
        "/opt/godot/godot"; do
        for p in $path; do
            if [ -x "$p" ]; then
                GODOT="$p"
                break 2
            fi
        done
    done
fi

if [ -z "$GODOT" ]; then
    echo "ERROR: Godot 4 not found."
    echo ""
    echo "Install Godot 4:"
    echo "  https://godotengine.org/download"
    echo ""
    echo "Or specify the path:"
    echo "  GODOT=/path/to/godot bash build.sh"
    exit 1
fi

if [ -n "${GODOT:-}" ] && [ -x "${GODOT:-}" ]; then
    echo "Using Godot: $GODOT"
else
    echo "Using Godot: $GODOT"
fi

# Build the Godot project
echo ""
echo "==> Exporting Godot project..."
mkdir -p "$BUILD_DIR"

# Check if export preset exists
if [ ! -f "$GODOT_DIR/export_presets.cfg" ]; then
    echo "Creating export_presets.cfg..."
    cat > "$GODOT_DIR/export_presets.cfg" << 'PRESETS_EOF'
[preset.0]

name="Linux"
platform="Linux"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter=""

export_path="tanu"

[preset.0.options]

custom_template/debug=""
custom_template/release=""
debug/export_console_wrapper=1
binary_format/embed_pck=true
texture_format/s3tc_bptc=true
texture_format/etc2_astc=false
binary_format/architecture="x86_64"
ssh_remote_deploy/enabled=false
PRESETS_EOF
fi

"$GODOT" --headless --path "$GODOT_DIR" --export-release "Linux" "$BUILD_DIR/tanu-godot" 2>&1 || {
    echo ""
    echo "Export failed. Make sure you have export templates installed."
    echo "  Godot Editor -> Manage Export Templates -> Download"
    echo ""
    echo "Alternative: open the project in Godot editor and export manually:"
    echo "  $GODOT --path $GODOT_DIR"
    exit 1
}

chmod +x "$BUILD_DIR/tanu-godot" 2>/dev/null || true

echo ""
echo "Build complete!"
echo "  Binary:  $BUILD_DIR/tanu-godot"
echo "  Run:     python main.py desk"
