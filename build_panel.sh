#!/usr/bin/env bash
# build_panel.sh — Build the Tanu LVGL panel binary on the SBC.
#
# Run this ON the DietPi board (native compilation, no cross-compilation):
#   chmod +x build_panel.sh
#   ./build_panel.sh
#
# Prerequisites (install once):
#   sudo apt install build-essential cmake ninja-build python3 python3-venv libevdev-dev libwebsockets-dev
#   python3 -m venv /opt/tanu/lvenv
#   source /opt/tanu/lvenv/bin/activate
#   pip install kconfiglib pcpp
#
# This script:
#   1. Clones lv_port_linux (if not already present)
#   2. Builds LVGL with fbdev support (no SDL/Wayland/X11)
#   3. Builds tanu_panel

set -euo pipefail

WORK_DIR="${WORK_DIR:-/opt/tanu}"
LVGL_DIR="${WORK_DIR}/lv_port_linux"
PANEL_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${PANEL_DIR}/build"

echo "=== Tanu LVGL Panel Build ==="
echo "  Work dir:   ${WORK_DIR}"
echo "  LVGL dir:   ${LVGL_DIR}"
echo "  Panel dir:  ${PANEL_DIR}"

# ── Step 1: Clone lv_port_linux if needed ──────────────────────────────────
if [ ! -d "${LVGL_DIR}" ]; then
    echo ""
    echo "--- Cloning lv_port_linux ---"
    mkdir -p "${WORK_DIR}"
    cd "${WORK_DIR}"
    git clone --recurse-submodules https://github.com/lvgl/lv_port_linux.git
fi

# ── Step 2: Build LVGL with fbdev config ──────────────────────────────────
echo ""
echo "--- Configuring LVGL (fbdev, no SDL/Wayland/X11) ---"
cd "${LVGL_DIR}"

# Create or update .config for fbdev-only build
cat > .config << 'EOF'
# LVGL config for Tanu panel (fbdev only)
CONFIG_LV_USE_LINUX_FBDEV=y
CONFIG_LV_USE_SDL=n
CONFIG_LV_USE_WAYLAND=n
CONFIG_LV_USE_X11=n
CONFIG_LV_USE_GLFW=n
CONFIG_LV_USE_LINUX_DRM=n
CONFIG_LV_COLOR_DEPTH_16=y
CONFIG_LV_FONT_MONTSERRAT_14=y
CONFIG_LV_FONT_MONTSERRAT_20=y
CONFIG_LV_FONT_MONTSERRAT_28=y
CONFIG_LV_FONT_DEFAULT_MONTSERRAT_20=y
CONFIG_LV_USE_PERF_MONITOR=n
CONFIG_LV_USE_LOG=n
CONFIG_LV_USE_DEMO_WIDGETS=n
CONFIG_LV_USE_DEMO_BENCHMARK=n
CONFIG_LV_USE_DEMO_MUSIC=n
EOF

# Apply the config
if command -v defconfig &>/dev/null; then
    defconfig .config 2>/dev/null || true
fi

echo "Building LVGL..."
if command -v ninja &>/dev/null; then
    cmake -B build -GNinja -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -5
    cmake --build build -j"$(nproc)" 2>&1 | tail -5
else
    cmake -B build -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -5
    cmake --build build -j"$(nproc)" 2>&1 | tail -5
fi

echo "LVGL build done."

# ── Step 3: Build tanu_panel ──────────────────────────────────────────────
echo ""
echo "--- Building tanu_panel ---"
mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"

cmake "${PANEL_DIR}" \
    -DLVGL_DIR="${LVGL_DIR}" \
    -DCMAKE_BUILD_TYPE=Release \
    2>&1 | tail -10

cmake --build . -j"$(nproc)" 2>&1 | tail -10

# ── Step 4: Install ──────────────────────────────────────────────────────
echo ""
echo "--- Installing tanu_panel ---"
sudo cmake --install . 2>&1 | tail -5

echo ""
echo "=== Build complete ==="
echo "  Binary: $(which tanu_panel 2>/dev/null || echo ${BUILD_DIR}/tanu_panel)"
echo ""
echo "Run with:"
echo "  LV_LINUX_FBDEV_DEVICE=/dev/fb0 tanu_panel --ws-url ws://127.0.0.1:7337/ws/chat"
echo ""
echo "Or via Tanu launcher:"
echo "  python3 main.py desk --panel"
