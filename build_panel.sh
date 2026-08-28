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
#   pip install kconfiglib pcpp pypng lz4 pillow
#
# This script:
#   1. Clones lv_port_linux (if not already present)
#   2. Builds LVGL with fbdev support (Kconfig-based, no SDL/Wayland/X11)
#   3. Installs LVGL headers and libraries to /usr/local
#   4. Extracts the character GIF into RGB565 C arrays (LVGLImage.py)
#   5. Compiles tanu_panel with gcc and installs to /usr/local/bin

set -euo pipefail

WORK_DIR="${WORK_DIR:-/opt/tanu}"
LVGL_DIR="${WORK_DIR}/lv_port_linux"
PANEL_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_FILE="${PANEL_DIR}/src/tanu/desktop/lvgl_panel/tanu_panel.c"

echo "=== Tanu LVGL Panel Build ==="
echo "  Work dir:   ${WORK_DIR}"
echo "  LVGL dir:   ${LVGL_DIR}"
echo "  Panel src:  ${SRC_FILE}"

# ── Step 0: Decide whether we even need to touch LVGL ───────────────────────
# LVGL itself only needs to be rebuilt once (or when LV_GL_TAG changes / you
# edit lv_conf). Recompiling it from source every run is what makes builds
# feel "heavy" — skip it automatically once it's already installed.
LV_GL_TAG="${LV_GL_TAG:-v9.5.0}"
FORCE_LVGL_REBUILD="${FORCE_LVGL_REBUILD:-0}"   # set to 1 to force a full LVGL rebuild
LVGL_STAMP="${WORK_DIR}/.lvgl_build_stamp"       # records which tag is currently installed

NEED_LVGL_BUILD=1
if [ "${FORCE_LVGL_REBUILD}" != "1" ] \
   && [ -f "/usr/local/lib/liblvgl.a" -o -f "/usr/local/lib/liblvgl.so" ] \
   && [ -f "${LVGL_STAMP}" ] \
   && [ "$(cat "${LVGL_STAMP}")" = "${LV_GL_TAG}" ]; then
    NEED_LVGL_BUILD=0
    echo ""
    echo "--- LVGL ${LV_GL_TAG} already installed, skipping clone/build (set FORCE_LVGL_REBUILD=1 to override) ---"
fi

PYTHON3="${PYTHON3:-python3}"

if [ "${NEED_LVGL_BUILD}" = "1" ]; then

# ── Step 1: Clone/update lv_port_linux + pin LVGL release ──────────────────
# lv_port_linux only tags up to v9.2.2; all releases flow through master.
# The actual LVGL library is the lvgl submodule, which we pin to a release tag.

if [ ! -d "${LVGL_DIR}" ]; then
    echo ""
    echo "--- Cloning lv_port_linux ---"
    mkdir -p "${WORK_DIR}"
    git clone --recurse-submodules https://github.com/lvgl/lv_port_linux.git "${LVGL_DIR}"
fi

cd "${LVGL_DIR}"
echo "--- Updating lv_port_linux to latest (master) ---"
git fetch origin
git checkout -f master
git submodule update --init --recursive

echo "--- Pinning lvgl submodule to release ${LV_GL_TAG} ---"
git -C lvgl fetch --tags --force origin
git -C lvgl checkout -f "${LV_GL_TAG}"

# ── Step 1.5: Ensure Python build deps (Kconfig + LVGLImage) ────────────────
# kconfiglib/pcpp drive LVGL's Kconfig; pypng+pillow drive LVGLImage.py and
# GIF->PNG frame extraction. Install into whatever python3 is active.
echo ""
echo "--- Ensuring Python build deps (kconfiglib pcpp pypng lz4 pillow) ---"
if ! ${PYTHON3} -c "import kconfiglib, pcpp, png, lz4, PIL" 2>/dev/null; then
    ${PYTHON3} -m pip install --quiet kconfiglib pcpp pypng lz4 pillow ||
        ${PYTHON3} -m pip install --quiet --user kconfiglib pcpp pypng lz4 pillow ||
        ${PYTHON3} -m pip install --quiet --break-system-packages kconfiglib pcpp pypng lz4 pillow ||
        { echo "ERROR: could not install kconfiglib/pcpp/pypng/lz4/pillow into python3"; exit 1; }
fi
echo "Python deps OK."

# ── Step 2: Configure and build LVGL ──────────────────────────────────────
echo ""
echo "--- Configuring LVGL (Kconfig, fbdev only) ---"
cd "${LVGL_DIR}"

grep -m1 "LVGL_VERSION_MAJOR\|LVGL_VERSION_MINOR\|LVGL_VERSION_PATCH" \
    "${LVGL_DIR}/lvgl/lv_version.h" 2>/dev/null \
    || grep -rm1 "LVGL_VERSION_MAJOR\|LVGL_VERSION_MINOR\|LVGL_VERSION_PATCH" \
    "${LVGL_DIR}/lvgl/src/lv_conf_internal.h" 2>/dev/null \
    || echo "LVGL version unknown"

# Clean build dir to ensure fresh config
rm -rf build

# Create .config for the Kconfig build (lv_port_linux master forces Kconfig on)
cat > .config << 'LVEOF'
# LVGL
CONFIG_LV_COLOR_DEPTH_16=y
CONFIG_LV_FONT_MONTSERRAT_14=y
CONFIG_LV_FONT_MONTSERRAT_20=y
CONFIG_LV_FONT_MONTSERRAT_28=y
CONFIG_LV_FONT_DEFAULT_MONTSERRAT_20=y
CONFIG_LV_USE_ANIMIMG=y
CONFIG_LV_USE_LINUX_FBDEV=y

# Demo/desktop backends we do NOT want on the SBC
CONFIG_LV_USE_SDL=n
CONFIG_LV_USE_WAYLAND=n
CONFIG_LV_USE_X11=n
CONFIG_LV_USE_DEMO_WIDGETS=n
LVEOF

# lvgl v9.5.0's kconfig.cmake only reads .config from the lvgl source dir
cp .config lvgl/.config

echo "Building LVGL core + fbdev backend..."
if command -v ninja &>/dev/null; then
    cmake -B build -GNinja -DCMAKE_BUILD_TYPE=Release \
        2>&1 | tail -10
    cmake --build build --target lvgl_linux -j"$(nproc)" 2>&1 | tail -10
else
    cmake -B build -DCMAKE_BUILD_TYPE=Release \
        2>&1 | tail -10
    cmake --build build --target lvgl_linux -j"$(nproc)" 2>&1 | tail -10
fi

echo "LVGL build done."

# ── Step 3: Install LVGL headers and libraries ────────────────────────────
echo ""
echo "--- Installing LVGL to /usr/local ---"
sudo cmake --install ./build 2>&1 | tail -10

echo "${LV_GL_TAG}" > "${LVGL_STAMP}"
echo "LVGL install done (stamped ${LV_GL_TAG} at ${LVGL_STAMP})."

fi  # NEED_LVGL_BUILD

# ── Step 4: Extract animation frames into RGB565 C arrays ─────────────────
echo ""
echo "--- Generating animation frames (PNG -> RGB565 C) ---"

GIF_SRC="${WORK_DIR}/assets/character.gif"
GIF_OUT_DIR="${PANEL_DIR}/src/tanu/desktop/lvgl_panel"
GENERATED_DIR="${GIF_OUT_DIR}/generated"
LVGL_SCRIPTS="${LVGL_DIR}/lvgl/scripts"
FRAME_SIZE="${FRAME_SIZE:-200}"          # target on-screen size (px) per side
FRAME_BG="${FRAME_BG:-0x14141f}"         # composite alpha onto this colour
FRAME_TMP="$(mktemp -d)"
trap 'rm -rf "${FRAME_TMP}"' EXIT

if [ ! -f "${GIF_SRC}" ]; then
    echo "WARNING: ${GIF_SRC} not found, using ${PANEL_DIR}/src/tanu/assets/idle.gif"
    GIF_SRC="${PANEL_DIR}/src/tanu/assets/idle.gif"
fi

if [ -f "${GIF_SRC}" ] && [ -d "${LVGL_SCRIPTS}" ]; then
    mkdir -p "${GENERATED_DIR}"

    # Extract GIF frames to RGBA PNGs, resize, composite onto the panel bg.
    # Handles "restore to background" disposal by compositing each frame
    # onto a fresh canvas (GIFs are full-frame here).
    FRAME_COUNT=$(
      GIF_SRC="${GIF_SRC}" FRAME_SIZE="${FRAME_SIZE}" FRAME_TMP="${FRAME_TMP}" ${PYTHON3} - << 'PYEOF'
import os
from PIL import Image

gif = os.environ["GIF_SRC"]
out_dir = os.environ["FRAME_TMP"]
size = int(os.environ["FRAME_SIZE"])

im = Image.open(gif)
n = getattr(im, "n_frames", 1)
count = 0
for i in range(n):
    im.seek(i)
    frame = im.convert("RGBA")
    if frame.size != (size, size):
        frame = frame.resize((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0x14, 0x14, 0x1f, 255))
    canvas = Image.alpha_composite(canvas, frame)
    canvas.convert("RGB").save(os.path.join(out_dir, f"frame_{i:03d}.png"))
    count += 1
print(count)
PYEOF
    )

    if [ -z "${FRAME_COUNT}" ] || [ "${FRAME_COUNT}" -eq 0 ]; then
        echo "ERROR: no frames extracted from ${GIF_SRC}"
        exit 1
    fi
    echo "Extracted ${FRAME_COUNT} frames at ${FRAME_SIZE}x${FRAME_SIZE}"

    # Convert each PNG to a C color array (RGB565, bg composited).
    # Emit tanu_face_frames.h declaring every frame + the pointer array.
    FRAMES_H="${GIF_OUT_DIR}/tanu_face_frames.h"
    : > "${FRAMES_H}"
    {
        echo "/* Auto-generated by build_panel.sh - do not edit manually */"
        echo "#ifndef TANU_FACE_FRAMES_H"
        echo "#define TANU_FACE_FRAMES_H"
        echo ""
        echo "#ifndef LV_IMAGE_DECLARE"
        echo "#error inherited from lvgl.h"
        echo "#endif"
        echo ""
    } >> "${FRAMES_H}"

    i=0
    for png in "${FRAME_TMP}"/frame_*.png; do
        name="tanu_face_$(printf '%03d' "${i}")"
        ${PYTHON3} "${LVGL_SCRIPTS}/LVGLImage.py" \
            --cf RGB565 --ofmt C \
            --background "${FRAME_BG}" \
            -o "${GENERATED_DIR}" \
            --name "${name}" \
            "${png}" >/dev/null
        echo "LV_IMAGE_DECLARE(${name});" >> "${FRAMES_H}"
        i=$((i + 1))
    done

    {
        echo ""
        echo "static const lv_image_dsc_t * tanu_face_frames[] = {"
        i=0
        while [ "${i}" -lt "${FRAME_COUNT}" ]; do
            printf '    &tanu_face_%03d,\n' "${i}"
            i=$((i + 1))
        done
        echo "};"
        echo ""
        echo "#define TANU_FACE_FRAMES ${FRAME_COUNT}"
        echo ""
        echo "#endif /* TANU_FACE_FRAMES_H */"
    } >> "${FRAMES_H}"

    echo "Generated ${FRAME_COUNT} C arrays in ${GENERATED_DIR}"
    echo "Generated ${FRAMES_H}"
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

GIF_C_FILES="${GENERATED_DIR}/tanu_face_*.c"
EXTRA_SRCS=""
if compgen -G "${GIF_C_FILES}" > /dev/null; then
    EXTRA_SRCS="${GIF_C_FILES}"
fi

gcc -O2 -o /tmp/tanu_panel "${SRC_FILE}" ${EXTRA_SRCS} \
    -I"${GIF_OUT_DIR}" \
    -I/usr/local/include \
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