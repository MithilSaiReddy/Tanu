#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Building Tanu Desktop App (Tauri)"
echo ""

# Check for system dependencies
if ! command -v pkg-config &>/dev/null; then
    echo "ERROR: System dependencies not installed."
    echo "Run: sudo apt install build-essential libwebkit2gtk-4.1-dev libgtk-3-dev \\"
    echo "         libayatana-appindicator3-dev librsvg2-dev libsoup-3.0-dev \\"
    echo "         libjavascriptcoregtk-4.1-dev"
    exit 1
fi

# Build the Tauri app
cd "$SCRIPT_DIR/src/ui"
cargo tauri build

# Copy binary to project-level build/
mkdir -p "$SCRIPT_DIR/build"
cp "$SCRIPT_DIR/src/ui/src-tauri/target/release/tanu" "$SCRIPT_DIR/build/tanu"
echo "  Binary:  $SCRIPT_DIR/build/tanu"

# Copy packages if they exist
for pkg in deb rpm appimage; do
    PKG_DIR="$SCRIPT_DIR/src/ui/src-tauri/target/release/bundle/$pkg"
    if [ -d "$PKG_DIR" ]; then
        mkdir -p "$SCRIPT_DIR/build/$pkg"
        cp "$PKG_DIR"/* "$SCRIPT_DIR/build/$pkg/" 2>/dev/null || true
    fi
done

echo ""
echo "Build complete!"
echo "  Binary:  build/tanu"
echo "  Run:     python main.py desk"
