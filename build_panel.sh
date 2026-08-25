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
#   2. Builds LVGL with fbdev support (Kconfig-based, no SDL/Wayland/X11)
#   3. Installs LVGL headers and libraries to /usr/local
#   4. Compiles tanu_panel with gcc and installs to /usr/local/bin

set -euo pipefail

WORK_DIR="${WORK_DIR:-/opt/tanu}"
LVGL_DIR="${WORK_DIR}/lv_port_linux"
PANEL_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_FILE="${PANEL_DIR}/src/tanu/desktop/lvgl_panel/tanu_panel.c"

echo "=== Tanu LVGL Panel Build ==="
echo "  Work dir:   ${WORK_DIR}"
echo "  LVGL dir:   ${LVGL_DIR}"
echo "  Panel src:  ${SRC_FILE}"

# ── Step 1: Clone lv_port_linux if needed ──────────────────────────────────
if [ ! -d "${LVGL_DIR}" ]; then
    echo ""
    echo "--- Cloning lv_port_linux ---"
    mkdir -p "${WORK_DIR}"
    cd "${WORK_DIR}"
    git clone --recurse-submodules https://github.com/lvgl/lv_port_linux.git
fi

# ── Step 2: Configure and build LVGL with Kconfig ─────────────────────────
echo ""
echo "--- Configuring LVGL (Kconfig, fbdev only) ---"
cd "${LVGL_DIR}"

# Set Kconfig options via environment for non-interactive defconfig
export KCONFIG_CONFIG=".config"
export KCONFIG_CONFIG_FILE=".config"

# Create minimal .config with our options
cat > .config << 'EOF'
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
CONFIG_LV_USE_GIF=y
CONFIG_LV_USE_PERF_MONITOR=n
CONFIG_LV_USE_LOG=n
CONFIG_LV_USE_DEMO_WIDGETS=n
CONFIG_LV_USE_DEMO_BENCHMARK=n
CONFIG_LV_USE_DEMO_MUSIC=n
EOF

# Run defconfig to expand Kconfig defaults
if command -v defconfig &>/dev/null; then
    defconfig .config 2>/dev/null || true
fi

echo "Building LVGL core + fbdev backend..."
if command -v ninja &>/dev/null; then
    cmake -B build -GNinja -DCMAKE_BUILD_TYPE=Release -DLV_BUILD_USE_KCONFIG=ON 2>&1 | tail -5
    cmake --build build --target lvgl_linux -j"$(nproc)" 2>&1 | tail -10
else
    cmake -B build -DCMAKE_BUILD_TYPE=Release -DLV_BUILD_USE_KCONFIG=ON 2>&1 | tail -5
    cmake --build build --target lvgl_linux -j"$(nproc)" 2>&1 | tail -10
fi

echo "LVGL build done."

# ── Step 3: Install LVGL headers and libraries ────────────────────────────
echo ""
echo "--- Installing LVGL to /usr/local ---"
sudo cmake --install ./build 2>&1 | tail -10

echo "LVGL install done."

# ── Step 4: Generate GIF C array with LVGLImage.py ────────────────────────
echo ""
echo "--- Generating GIF C array ---"

GIF_SRC="${WORK_DIR}/assets/character.gif"
GIF_OUT_DIR="${PANEL_DIR}/src/tanu/desktop/lvgl_panel"
LVGL_SCRIPTS="${LVGL_DIR}/lvgl/scripts"

if [ ! -f "${GIF_SRC}" ]; then
    echo "WARNING: ${GIF_SRC} not found, using ${PANEL_DIR}/src/tanu/assets/idle.gif"
    GIF_SRC="${PANEL_DIR}/src/tanu/assets/idle.gif"
fi

if [ -f "${GIF_SRC}" ] && [ -d "${LVGL_SCRIPTS}" ]; then
    python3 "${LVGL_SCRIPTS}/LVGLImage.py" \
        --cf RAW --ofmt C \
        -o "${GIF_OUT_DIR}" \
        --name gif_character \
        "${GIF_SRC}" 2>&1
    echo "Generated ${GIF_OUT_DIR}/gif_character.c"
else
    echo "ERROR: LVGLImage.py or GIF not found"
    echo "  GIF_SRC=${GIF_SRC}"
    echo "  LVGL_SCRIPTS=${LVGL_SCRIPTS}"
    exit 1
fi

# ── Step 5: Compile tanu_panel with gcc ───────────────────────────────────
echo ""
echo "--- Compiling tanu_panel ---"

if [ ! -f "${SRC_FILE}" ]; then
    echo "ERROR: Source file not found: ${SRC_FILE}"
    exit 1
fi

GIF_C_FILE="${GIF_OUT_DIR}/gif_character.c"
EXTRA_SRCS=""
if [ -f "${GIF_C_FILE}" ]; then
    EXTRA_SRCS="${GIF_C_FILE}"
fi

gcc -O2 -o /tmp/tanu_panel "${SRC_FILE}" ${EXTRA_SRCS} \
    -I/usr/local/include/lvgl \
    -I/usr/local/include/lvgl/config \
    -I/usr/local/include/lvgl_private \
    -L/usr/local/lib \
    -llvgl_linux -llvgl \
    -lwebsockets -lm -lpthread \
    2>&1

echo "Compilation done."

# ── Step 6: Install binary ────────────────────────────────────────────────
echo ""
echo "--- Installing tanu_panel to /usr/local/bin ---"
sudo cp /tmp/tanu_panel /usr/local/bin/tanu_panel
sudo chmod +x /usr/local/bin/tanu_panel

echo ""
echo "=== Build complete ==="
echo "  Binary: /usr/local/bin/tanu_panel"
echo ""
echo "Run with:"
echo "  LV_LINUX_FBDEV_DEVICE=/dev/fb0 tanu_panel --ws-url ws://127.0.0.1:7337/ws/chat"
echo ""
echo "Or via Tanu launcher:"
echo "  python3 main.py desk --panel"
