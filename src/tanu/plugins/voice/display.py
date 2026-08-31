"""
tanu/plugins/voice/display.py

Display abstraction for deskbot. NullDisplay is always available (no-op).
LCDDisplay uses luma.lcd for ST7789 displays.
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

LOG = logging.getLogger(__name__)


class BaseDisplay(ABC):
    """Abstract display base class."""

    @abstractmethod
    def show_idle(self) -> None:
        pass

    @abstractmethod
    def show_partial(self, text: str) -> None:
        pass

    @abstractmethod
    def show_listening(self) -> None:
        pass

    @abstractmethod
    def show_thinking(self) -> None:
        pass

    @abstractmethod
    def show_speaking(self) -> None:
        pass

    @abstractmethod
    def show_error(self, msg: str) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


class NullDisplay(BaseDisplay):
    """No-op display — always available."""

    def show_idle(self) -> None:
        pass

    def show_partial(self, text: str) -> None:
        pass

    def show_listening(self) -> None:
        pass

    def show_thinking(self) -> None:
        pass

    def show_speaking(self) -> None:
        pass

    def show_error(self, msg: str) -> None:
        pass

    def close(self) -> None:
        pass


class LCDDisplay(BaseDisplay):
    """ST7789 LCD display via luma.lcd."""

    def __init__(self, cfg: dict):
        self._width = cfg.get("display_width", 240)
        self._height = cfg.get("display_height", 240)
        self._stop = threading.Event()
        self._state = "idle"
        self._state_lock = threading.Lock()
        self._last_update = 0
        self._fps_interval = 0.1

        self._partial_text = ""
        self._error_msg = ""
        self._rms_level = 0.0
        self._thinking_frame = 0
        self._speaking_frame = 0

        try:
            from luma.lcd.device import st7789
            from luma.core.interface.serial import spi
        except ImportError as e:
            raise ImportError(f"luma.lcd not installed: {e}")

        serial_interface = spi(port=0, device=0, gpio_DC=24, gpio_RST=25)
        self._device = st7789(
            serial_interface, width=self._width, height=self._height, rotate=0
        )
        self._device.clear()

        from PIL import Image, ImageDraw, ImageFont

        self._image = Image.new("RGB", (self._width, self._height), "black")
        self._draw = ImageDraw.Draw(self._image)

        font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        if font_path.exists():
            self._font = ImageFont.truetype(str(font_path), 20)
            self._font_small = ImageFont.truetype(str(font_path), 14)
        else:
            self._font = ImageFont.load_default()
            self._font_small = ImageFont.load_default()

        import numpy as np

        self._np = np

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        LOG.info(f"[Display] LCD initialized ({self._width}x{self._height})")

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = time.time()
            if now - self._last_update < self._fps_interval:
                time.sleep(self._fps_interval - (now - self._last_update))
                continue
            self._last_update = now
            self._render()

    def _render(self) -> None:
        with self._state_lock:
            state = self._state
            partial = self._partial_text
            error = self._error_msg
            rms = self._rms_level
            think_frame = self._thinking_frame
            speak_frame = self._speaking_frame

        self._draw.rectangle((0, 0, self._width, self._height), fill="black")

        if state == "idle":
            self._render_idle()
        elif state == "partial":
            self._render_partial(partial)
        elif state == "listening":
            self._render_listening(rms)
        elif state == "thinking":
            self._render_thinking(think_frame)
        elif state == "speaking":
            self._render_speaking(speak_frame)
        elif state == "error":
            self._render_error(error)

        self._device.display(self._image)

    def _render_idle(self) -> None:
        self._draw.text((20, 60), "🖥️", font=self._font, fill="gray")
        self._draw.text((20, 110), "Say hey Tanu", font=self._font, fill="white")
        self._draw.text((20, 180), "listening...", font=self._font_small, fill="gray")

    def _render_partial(self, text: str) -> None:
        display_text = text[:30] + "..." if len(text) > 30 else text
        self._draw.text((20, 60), "🎤", font=self._font, fill="gray")
        self._draw.text((20, 110), display_text, font=self._font, fill="#666666")

    def _render_listening(self, rms: float) -> None:
        self._draw.text((20, 60), "🎤", font=self._font, fill="#00ff00")
        bar_width = int(rms * self._width)
        self._draw.rectangle((20, 120, 20 + bar_width, 140), fill="#00ff00")
        self._draw.rectangle((20, 120, self._width - 20, 140), outline="#333333")

    def _render_thinking(self, frame: int) -> None:
        self._draw.text((20, 60), "💭", font=self._font, fill="yellow")
        dots = ["   ", "●  ", "●● ", "●●●", " ●●", "  ●"][frame % 6]
        self._draw.text((20, 120), dots, font=self._font, fill="white")
        self._thinking_frame = (frame + 1) % 6

    def _render_speaking(self, frame: int) -> None:
        self._draw.text((20, 60), "🔊", font=self._font, fill="#00ffff")
        bar_count = 8
        bar_spacing = (self._width - 40) // bar_count
        for i in range(bar_count):
            height = int(20 + 40 * self._np.sin((frame + i) * 0.5))
            x = 20 + i * bar_spacing
            self._draw.rectangle(
                (x, 140, x + bar_spacing - 4, 140 + height), fill="#00ffff"
            )
        self._speaking_frame = (frame + 1) % 20

    def _render_error(self, msg: str) -> None:
        self._draw.text((20, 60), "⚠️", font=self._font, fill="red")
        display_msg = msg[:25] + "..." if len(msg) > 25 else msg
        self._draw.text((20, 110), display_msg, font=self._font_small, fill="red")

    def show_idle(self) -> None:
        with self._state_lock:
            self._state = "idle"

    def show_partial(self, text: str) -> None:
        with self._state_lock:
            self._state = "partial"
            self._partial_text = text

    def show_listening(self, rms: float = 0.5) -> None:
        with self._state_lock:
            self._state = "listening"
            self._rms_level = rms

    def show_thinking(self) -> None:
        with self._state_lock:
            self._state = "thinking"

    def show_speaking(self) -> None:
        with self._state_lock:
            self._state = "speaking"

    def show_error(self, msg: str) -> None:
        with self._state_lock:
            self._state = "error"
            self._error_msg = msg

    def close(self) -> None:
        self._stop.set()
        if hasattr(self, "_thread"):
            self._thread.join(timeout=2)
        if hasattr(self, "_device"):
            self._device.clear()


class FBDisplay(BaseDisplay):
    """Drive the TFT framebuffer panel (FbdevPanel) from voice-assistant states.

    Wraps the same pure-Python /dev/fb0 panel used by 'desk --panel' so the
    face animation renders on the SBC TFT while the voice assistant runs.
    """

    def __init__(self, cfg: dict):
        from tanu.desktop.fbdev_panel import FbdevPanel
        from tanu.desktop.panel import get_panel_cfg

        panel_cfg = get_panel_cfg(cfg)
        self._panel = FbdevPanel(panel_cfg)
        self._panel.set_connected(True)
        self._panel.set_status("Say hey Tanu")
        self._panel.start()
        LOG.info("[Display] fbdev panel display initialized")

    def show_idle(self) -> None:
        self._panel.set_state("idle")
        self._panel.set_status("Say hey Tanu")

    def show_partial(self, text: str) -> None:
        self._panel.set_state("thinking")
        self._panel.set_response(text)

    def show_listening(self, rms: float = 0.5) -> None:
        self._panel.set_state("listening")
        self._panel.set_status("Listening...")

    def show_thinking(self) -> None:
        self._panel.set_state("thinking")
        self._panel.set_status("Thinking...")

    def show_speaking(self) -> None:
        self._panel.set_state("speaking")
        self._panel.set_status("Speaking...")

    def show_error(self, msg: str) -> None:
        self._panel.set_state("error")
        self._panel.set_status(msg or "Error")

    def close(self) -> None:
        self._panel.close()


def init_display(cfg: dict) -> BaseDisplay:
    """Initialize display based on config.

    - "fbdev" (or auto-detect: a panel framebuffer is present) -> TFT panel.
    - "st7789" -> luma.lcd ST7789.
    - "none" (default) -> NullDisplay.
    """
    from tanu.desktop.panel import resolve_fb_present

    dc = cfg.get("deskbot", {}) or {}
    display_type = dc.get("display_type", "auto")
    if display_type == "fbdev":
        return FBDisplay(cfg)
    if display_type == "st7789":
        return LCDDisplay(dc)
    if display_type == "auto" and resolve_fb_present(cfg):
        return FBDisplay(cfg)
    if display_type != "none" and display_type != "auto":
        LOG.warning(f"[Display] Unknown display_type: {display_type}, using NullDisplay")
    return NullDisplay()
