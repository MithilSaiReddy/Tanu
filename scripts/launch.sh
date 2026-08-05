#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_BIN="$DIR/tanu-server"
GODOT_BIN="$DIR/tanu-godot-arm64"

# Check binaries exist
if [ ! -f "$SERVER_BIN" ]; then
    echo "ERROR: Server binary not found: $SERVER_BIN"
    echo "Run ./first-boot.sh first to build it."
    exit 1
fi

if [ ! -f "$GODOT_BIN" ]; then
    echo "ERROR: Godot binary not found: $GODOT_BIN"
    echo "Run: bash build.sh arm64"
    exit 1
fi

echo "==> Starting Tanu"
echo "    Server: $SERVER_BIN"
echo "    Client: $GODOT_BIN"
echo ""

# Start server in background
"$SERVER_BIN" &
SERVER_PID=$!
echo "Server started (PID: $SERVER_PID)"

# Wait for server to be ready
echo "Waiting for server..."
for i in $(seq 1 40); do
    if curl -s http://localhost:7337/api/status > /dev/null 2>&1; then
        echo "Server ready."
        break
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "ERROR: Server crashed. Check logs."
        exit 1
    fi
    sleep 0.5
done

# Start Godot client (blocks until window closes)
echo "Starting client..."
"$GODOT_BIN"

# Cleanup
echo "Shutting down..."
kill "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true
echo "Done."
