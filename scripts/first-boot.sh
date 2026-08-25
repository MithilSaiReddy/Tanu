#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGE_DIR="$(dirname "$SCRIPT_DIR")"

echo "==> Tanu First Boot Setup"
echo "    Creating a virtual environment and installing dependencies."
echo ""

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install it:"
    echo "  sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

echo "Python: $(python3 --version)"

echo ""
echo "==> Creating Python virtual environment..."
python3 -m venv "$PACKAGE_DIR/venv"
source "$PACKAGE_DIR/venv/bin/activate"

echo "==> Installing dependencies..."
pip install --upgrade pip -q
pip install -r "$PACKAGE_DIR/requirements.txt" -q

echo ""
echo "==> First boot complete!"
echo ""
echo "    Run the app with: ./launch.sh"
