#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGE_DIR="$(dirname "$SCRIPT_DIR")"
SERVER_DIR="$PACKAGE_DIR/server"

echo "==> Tanu First Boot Setup"
echo "    Building standalone server binary for this device."
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install it:"
    echo "  sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

echo "Python: $(python3 --version)"

# Create venv
echo ""
echo "==> Creating Python virtual environment..."
python3 -m venv "$SERVER_DIR/venv"
source "$SERVER_DIR/venv/bin/activate"

# Install dependencies
echo "==> Installing dependencies..."
pip install --upgrade pip -q

# Install pip packages (skip -e lines which are editable installs)
grep -v '^\-e ' "$SERVER_DIR/requirements.txt" | pip install -r /dev/stdin -q

# Install the Tanu package in non-editable mode (needed for PyInstaller)
pip install "$SERVER_DIR" -q

pip install pyinstaller -q

# Build standalone binary
echo ""
echo "==> Building standalone server binary with PyInstaller..."
cd "$SERVER_DIR"

pyinstaller --onefile --name tanu-server \
    --paths . \
    --paths src \
    --hidden-import=tanu \
    --hidden-import=tanu.config \
    --hidden-import=tanu.notifier \
    --hidden-import=tanu.server \
    --hidden-import=tanu.agent \
    --hidden-import=tanu.session \
    --hidden-import=tanu.identity \
    --hidden-import=tanu.llm \
    --hidden-import=tanu.connections \
    --hidden-import=tanu.connections.telegram \
    --hidden-import=tanu.connections.discord \
    --hidden-import=tanu.tools \
    --hidden-import=tanu.tools.base \
    --hidden-import=tanu.tools.shell \
    --hidden-import=tanu.tools.web \
    --hidden-import=tanu.tools.file_ops \
    --hidden-import=tanu.tools.memory \
    --hidden-import=tanu.tools.subagents \
    --hidden-import=tanu.tools.todo \
    --hidden-import=tanu.tools.utils \
    --hidden-import=tanu.tools.gmail \
    --hidden-import=tanu.tools.speak_tool \
    --hidden-import=tanu.tools.tanu_query \
    --hidden-import=tanu.tools.tanu_task \
    --hidden-import=tanu.tools.tanu_reminder \
    --hidden-import=tanu.plugins \
    --hidden-import=tanu.plugins.voice \
    --hidden-import=tanu.plugins.voice.deskbot \
    --hidden-import=tanu.plugins.voice.display \
    --hidden-import=tanu.plugins.voice.wakeword \
    --collect-submodules tanu \
    main.py

# Move binary to package root
mv dist/tanu-server "$PACKAGE_DIR/tanu-server"
chmod +x "$PACKAGE_DIR/tanu-server"

# Cleanup build artifacts
cd "$PACKAGE_DIR"
rm -rf "$SERVER_DIR/venv" "$SERVER_DIR/build" "$SERVER_DIR/dist" "$SERVER_DIR"/*.spec

echo ""
echo "==> First boot complete!"
echo "    Binary: $PACKAGE_DIR/tanu-server"
echo ""
echo "    Run the app with: ./launch.sh"
