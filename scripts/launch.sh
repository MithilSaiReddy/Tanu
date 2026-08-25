#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$DIR")"
cd "$ROOT"

PYTHON="$ROOT/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON="$(command -v python3)"
fi

if [ ! -f "$ROOT/main.py" ]; then
    echo "ERROR: main.py not found in $ROOT"
    exit 1
fi

echo "==> Starting Tanu"
echo "    Server:  http://localhost:7337"
echo "    UI:      pygame"
echo ""

exec "$PYTHON" main.py desk
