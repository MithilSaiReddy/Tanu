#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GODOT_DIR="$SCRIPT_DIR/src/godot"
BUILD_DIR="$SCRIPT_DIR/build"

# Parse target
TARGET="${1:-x86_64}"

usage() {
    echo "Usage: bash build.sh [TARGET]"
    echo ""
    echo "Targets:"
    echo "  x86_64      Build Godot x86_64 (default)"
    echo "  arm64       Build Godot arm64"
    echo "  all-in-one  Build arm64 + server source + scripts for Radxa deployment"
    echo ""
    exit 0
}

if [ "${TARGET}" = "--help" ] || [ "${TARGET}" = "-h" ]; then
    usage
fi

# Find Godot binary
find_godot() {
    GODOT=""
    for bin in godot godot4; do
        if command -v "$bin" &>/dev/null; then
            GODOT="$bin"
            return
        fi
    done

    for path in \
        "$HOME/Documents/Godot_v4"*"linux.x86_64" \
        "$HOME/.local/bin/godot" \
        "/usr/local/bin/godot" \
        "/opt/godot/godot"; do
        for p in $path; do
            if [ -x "$p" ]; then
                GODOT="$p"
                return
            fi
        done
    done
}

find_godot

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

echo "Using Godot: $GODOT"
echo ""

# Export Godot for a given architecture
export_godot() {
    local preset_name="$1"
    local output_name="$2"

    echo "==> Exporting Godot ($preset_name)..."
    mkdir -p "$BUILD_DIR"

    "$GODOT" --headless --path "$GODOT_DIR" --export-release "$preset_name" "$BUILD_DIR/$output_name" 2>&1 || {
        echo ""
        echo "Export failed. Make sure you have export templates installed."
        echo "  Godot Editor -> Manage Export Templates -> Download"
        echo ""
        echo "Alternative: open the project in Godot editor and export manually:"
        echo "  $GODOT --path $GODOT_DIR"
        exit 1
    }

    chmod +x "$BUILD_DIR/$output_name" 2>/dev/null || true
    echo "    Output: $BUILD_DIR/$output_name"
}

# Copy server source for packaging
copy_server() {
    local dest="$1"
    echo "==> Copying server source..."
    mkdir -p "$dest/server"
    cp "$SCRIPT_DIR/main.py" "$dest/server/"
    cp "$SCRIPT_DIR/requirements.txt" "$dest/server/"
    cp "$SCRIPT_DIR/pyproject.toml" "$dest/server/"
    mkdir -p "$dest/server/src"
    cp -r "$SCRIPT_DIR/src/tanu" "$dest/server/src/"
    # Remove __pycache__ and .pyc
    find "$dest/server" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find "$dest/server" -name "*.pyc" -delete 2>/dev/null || true
    echo "    Server source copied to $dest/server/"
}

case "$TARGET" in
    x86_64)
        export_godot "Linux" "tanu-godot"
        echo ""
        echo "Build complete! Run: python main.py desk"
        ;;
    arm64)
        export_godot "Linux ARM64" "tanu-godot-arm64"
        echo ""
        echo "Build complete! Binary: build/tanu-godot-arm64"
        ;;
    all-in-one)
        export_godot "Linux ARM64" "tanu-godot-arm64"
        echo ""

        # Create package directory
        PACKAGE_DIR="$BUILD_DIR/tanu-cubie"
        rm -rf "$PACKAGE_DIR"
        mkdir -p "$PACKAGE_DIR"

        # Move Godot binary into package
        mv "$BUILD_DIR/tanu-godot-arm64" "$PACKAGE_DIR/"

        # Copy server source
        copy_server "$PACKAGE_DIR"

        # Copy scripts
        cp "$SCRIPT_DIR/scripts/launch.sh" "$PACKAGE_DIR/"
        cp "$SCRIPT_DIR/scripts/first-boot.sh" "$PACKAGE_DIR/"
        chmod +x "$PACKAGE_DIR/launch.sh" "$PACKAGE_DIR/first-boot.sh"

        # Create tarball
        tar czf "$BUILD_DIR/tanu-cubie.tar.gz" -C "$BUILD_DIR" tanu-cubie

        echo ""
        echo "==> All-in-one package ready!"
        echo "    Directory: $PACKAGE_DIR/"
        echo "    Tarball:   $BUILD_DIR/tanu-cubie.tar.gz"
        echo ""
        echo "Deploy to Radxa Cubie A7Z:"
        echo "    scp $BUILD_DIR/tanu-cubie.tar.gz user@<radxa-ip>:~/"
        echo "    ssh user@<radxa-ip>"
        echo "    tar xzf tanu-cubie.tar.gz && cd tanu-cubie"
        echo "    ./first-boot.sh    # One-time setup (~5 min)"
        echo "    ./launch.sh        # Start"
        ;;
    *)
        echo "ERROR: Unknown target '$TARGET'"
        echo ""
        usage
        ;;
esac
