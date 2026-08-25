cmake_minimum_required(VERSION 3.10)
project(tanu_panel C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# ── Find LVGL ──────────────────────────────────────────────────────────────
# LVGL is expected to be built first via lv_port_linux.
# Set LVGL_DIR to point at the lv_port_linux repo root.
if(NOT DEFINED LVGL_DIR)
    # Try common locations
    if(EXISTS "/opt/tanu/lv_port_linux")
        set(LVGL_DIR "/opt/tanu/lv_port_linux")
    elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../../../lv_port_linux")
        set(LVGL_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../lv_port_linux")
    else()
        message(FATAL_ERROR
            "LVGL_DIR not set. Pass -DLVGL_DIR=/path/to/lv_port_linux\n"
            "or ensure /opt/tanu/lv_port_linux exists.")
    endif()
endif()

# Use LVGL's CMake build system
add_subdirectory("${LVGL_DIR}/lvgl" "${CMAKE_BINARY_DIR}/lvgl_build" EXCLUDE_FROM_ALL)

# ── Find libwebsockets ─────────────────────────────────────────────────────
find_library(LWS_LIB websockets REQUIRED)
find_path(LWS_INCLUDE libwebsockets.h REQUIRED)

# ── tanu_panel binary ──────────────────────────────────────────────────────
add_executable(tanu_panel tanu_panel.c)

target_link_libraries(tanu_panel PRIVATE lvgl ${LWS_LIB} m)
target_include_directories(tanu_panel PRIVATE
    ${LWS_INCLUDE}
    "${LVGL_DIR}/lvgl/src"   # LVGL internal headers (for draw API)
)

# Ensure LVGL config from lv_port_linux is used
target_compile_definitions(tanu_panel PRIVATE
    LV_CONF_INCLUDE_SIMPLE
)

# Install
install(TARGETS tanu_panel DESTINATION bin)
