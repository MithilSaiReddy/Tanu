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
cd "$SCRIPT_DIR"
cargo tauri build

echo ""
echo "✅ Build complete! Binary at: src-tauri/target/release/tanu"
echo "   Run: python main.py desk"
