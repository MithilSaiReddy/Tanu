"""
Display mode resolution for the desktop UI.

Two display modes:
  - "window":  regular 400x400 desktop window (default)
  - "panel":   renders directly to a small TFT framebuffer (/dev/fb0)
               using a pure-Python Pillow driver (fbdev).
               Target: SBCs like the Radxa Cubie A7Z with an ILI9341 panel.
"""

import os
from pathlib import Path

DEFAULT_PANEL = {
    "device": "/dev/fb0",
    "width": 320,
    "height": 240,
    "fps": 24,
    "speed": 1.0,
    "rotation": 0,
    "driver": "fbdev",
}


def resolve_display_mode(force_panel: bool, cfg: dict) -> str:
    ui = cfg.get("ui", {}) if cfg else {}
    if force_panel:
        return "panel"
    return ui.get("display", "window") if ui.get("display") in ("window", "panel") else "window"


def get_panel_cfg(cfg: dict) -> dict:
    panel = dict(DEFAULT_PANEL)
    panel.update(cfg.get("ui", {}).get("panel", {}) or {})
    try:
        panel["width"] = int(panel["width"])
        panel["height"] = int(panel["height"])
        panel["fps"] = int(panel["fps"])
        panel["rotation"] = int(panel["rotation"]) % 360
        speed = float(panel.get("speed", 1.0))
        panel["speed"] = speed if speed > 0 else 1.0
    except (KeyError, TypeError, ValueError):
        pass
    if panel["rotation"] not in (0, 90, 180, 270):
        panel["rotation"] = 0
    driver = panel.get("driver", "fbdev")
    if driver != "fbdev":
        driver = "fbdev"
    panel["driver"] = driver
    return panel


def _validate_framebuffer(device: str) -> None:
    """Raise if the framebuffer device is missing or inaccessible."""
    if not Path(device).exists():
        raise FileNotFoundError(
            f"Panel framebuffer {device} not found.\n"
            "   The SPI panel kernel driver is not loaded.\n"
            "   See docs/content/guide/sbc-panel.md for wiring + overlay setup."
        )
    if not os.access(device, os.R_OK | os.W_OK):
        raise PermissionError(
            f"Panel framebuffer {device} is not accessible.\n"
            "   Add your user to the video group, then log out/in:\n"
            "   sudo usermod -aG video $USER"
        )


def apply_panel_env(panel_cfg: dict) -> None:
    """Set SDL env vars for the Pygame fbcon panel path. Run before pygame.init()."""
    _validate_framebuffer(panel_cfg["device"])
    os.environ["SDL_VIDEODRIVER"] = "fbcon"
    os.environ["SDL_FBDEV"] = panel_cfg["device"]
    os.environ.setdefault("SDL_NOMOUSE", "1")
