"""
tanu.desktop — desktop UI for Tanu.

Two display modes:
  - Window: Pygame desktop window (default).
  - Panel:  pure-Python Pillow driver rendering to a /dev/fb0 TFT panel.
"""

from .panel import (
    resolve_display_mode,
    get_panel_cfg,
)


def run_app(host="127.0.0.1", port=7337, display_mode="window", cfg=None):
    from .app import TanuDesktopApp
    return TanuDesktopApp(
        host=host, port=port, display_mode=display_mode, cfg=cfg
    ).run()


__all__ = [
    "run_app",
    "resolve_display_mode",
    "get_panel_cfg",
]
