"""
tanu.desktop — desktop UI for Tanu.

Two panel drivers:
  - LVGL (native C binary): default for SBC panel mode, no Python deps
  - Pygame: window mode and legacy fbcon panel mode
"""

from .panel import (
    resolve_display_mode,
    get_panel_cfg,
    get_lvgl_binary_path,
    apply_panel_env,
    apply_lvgl_env,
)


def run_app(host="127.0.0.1", port=7337, display_mode="window", cfg=None):
    """Lazy import to avoid requiring pygame when using LVGL driver."""
    from .app import TanuDesktopApp
    return TanuDesktopApp(
        host=host, port=port, display_mode=display_mode, cfg=cfg
    ).run()


__all__ = [
    "run_app",
    "resolve_display_mode",
    "get_panel_cfg",
    "get_lvgl_binary_path",
    "apply_panel_env",
    "apply_lvgl_env",
]
