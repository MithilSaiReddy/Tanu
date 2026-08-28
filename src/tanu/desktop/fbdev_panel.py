"""
tanu.desktop.fbdev_panel — pure-Python TFT panel driver.

Renders the animated Tanu face plus a status line / response ticker directly
to a Linux framebuffer (/dev/fb0) exposed by an fbtft overlay (e.g. ILI9341).
No C, no LVGL: Pillow composes each frame and we write RGB565 into the
mapped framebuffer honouring the device's line pitch.

Layout / signal flow:
    server (:7337)  --/ws/chat-->  WSClient  -->  FbdevPanel.render thread
                  state | token | response | done | error | tool_*
"""

from __future__ import annotations

import fcntl
import logging
import mmap
import os
import struct
import threading
import time
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

LOG = logging.getLogger(__name__)

FBIOGET_VSCREENINFO = 0x4600
FBIOGET_FSCREENINFO = 0x4602

# State -> accent colour used for the status line / border.
STATE_COLORS = {
    "idle":      (0x14, 0xcc, 0xff),
    "listening": (0x00, 0xff, 0x66),
    "thinking":  (0xff, 0xdd, 0x33),
    "speaking":  (0x00, 0xff, 0xdd),
    "error":     (0xff, 0x55, 0x55),
}

DEFAULT_BG = (0x14, 0x14, 0x1f)


def _struct_screeninfo(buf: bytes) -> tuple[int, int, int, int, int]:
    """Parse fb_var_screeninfo: return (xres, yres, xres_virtual,
    yres_virtual, bits_per_pixel).

    fb_var_screeninfo u32 order: xres, yres, xres_virtual, yres_virtual,
    xoffset, yoffset, bits_per_pixel, grayscale, red, green, blue, transp, ...
    """
    vals = struct.unpack_from("=IIIIIII", buf, 0)
    return vals[0], vals[1], vals[2], vals[3], vals[6]


def _struct_fixinfo(buf: bytes) -> tuple[int, int]:
    """Parse fb_fix_screeninfo: return (line_length, smem_len).

    fb_fix_screeninfo layout (u32-aligned):
      id[16], smem_start(8), smem_len, type, type_aux, visual   -> offsets 0..39
      xpanstep, ypanstep, ywrapstep (u16)                       -> 40..45
      2 bytes padding (natural u32 alignment)                   -> 46..47
      line_length (u32)                                         -> 48..51
    So smem_len is at offset 24 and line_length at byte offset 48.
    """
    smem_len = struct.unpack_from("=I", buf, 24)[0]
    line_length = struct.unpack_from("=I", buf, 48)[0]
    return line_length, smem_len


def _rgb888_to_rgb565(r: int, g: int, b: int) -> int:
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def _convert_frame_to_rgb565(image: Image.Image) -> bytes:
    """Return packed RGB565 bytes for a full RGB image (no pitch padding)."""
    rgb = image.convert("RGB")
    px = rgb.load()
    w, h = rgb.size
    out = bytearray(w * h * 2)
    i = 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            val = _rgb888_to_rgb565(r, g, b)
            out[i] = val & 0xFF
            out[i + 1] = (val >> 8) & 0xFF
            i += 2
    return bytes(out)


class FbdevPanel:
    """Animate the Tanu face to a Linux framebuffer and drive it over WS."""

    def __init__(self, cfg: dict, asset_dir: Optional[Path] = None,
                 ws_url: str = "ws://127.0.0.1:7337/ws/chat"):
        self._device = cfg.get("device", "/dev/fb0")
        self._cfg_w = int(cfg.get("width", 320))
        self._cfg_h = int(cfg.get("height", 240))
        self._fps = int(cfg.get("fps", 24))
        self._rotation = int(cfg.get("rotation", 0)) % 360
        self._ws_url = ws_url

        self._asset_dir = Path(asset_dir) if asset_dir is not None else (
            Path(__file__).resolve().parent.parent / "assets" / "idle"
        )
        self._frames: list[Image.Image] = []
        self._state = "idle"
        self._status = "Connecting..."
        self._response = "Waiting for server..."
        self._connected = False
        self._frame_idx = 0
        self._stop = threading.Event()
        self._lock = threading.Lock()

        self._fb_fd = None
        self._fb_map = None
        self._fb_width = 0
        self._fb_height = 0
        self._fb_bpp = 0
        self._line_length = 0
        self._smem_len = 0

        self._open_framebuffer()
        self._load_frames()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    # ── framebuffer mapping ────────────────────────────────────────────────

    def _open_framebuffer(self) -> None:
        if not Path(self._device).exists():
            raise FileNotFoundError(
                f"Panel framebuffer {self._device} not found.\n"
                "   Ensure the SPI panel kernel driver (fbtft/ili9341) is loaded.\n"
                "   See docs/content/guide/sbc-panel.md"
            )
        self._fb_fd = os.open(self._device, os.O_RDWR)
        try:
            var = fcntl.ioctl(self._fb_fd, FBIOGET_VSCREENINFO, b"\0" * 160)
            fix = fcntl.ioctl(self._fb_fd, FBIOGET_FSCREENINFO, b"\0" * 160)
        except OSError:
            os.close(self._fb_fd)
            self._fb_fd = None
            raise

        xres, yres, xres_v, yres_v, bpp = _struct_screeninfo(var)
        self._line_length, self._smem_len = _struct_fixinfo(fix)
        if xres_v > 0:
            xres = xres_v
        if yres_v > 0:
            yres = yres_v

        self._fb_width = xres
        self._fb_height = yres
        self._fb_bpp = bpp

        if bpp != 16:
            LOG.warning("fb bpp=%d (expected 16). RGB565 packing may be wrong.", bpp)
        if self._fb_width != self._cfg_w or self._fb_height != self._cfg_h:
            LOG.info(
                "fb %s is %dx%d (%d bpp) — panel cfg is %dx%d",
                self._device, xres, yres, bpp, self._cfg_w, self._cfg_h,
            )

        # Map only what the hardware actually backs: clamp to smem_len so a
        # mis-parsed/huge line_length (or virtual geometry larger than the
        # real fb) can never cause a SIGBUS by writing past the buffer.
        size = min(self._line_length * self._fb_height, self._smem_len)
        self._fb_map = mmap.mmap(self._fb_fd, size)
        LOG.info("Mapped %s (%dx%d, %d bpp, pitch %d, smem %d B)",
                 self._device, xres, yres, bpp, self._line_length, self._smem_len)

    # ── frames ─────────────────────────────────────────────────────────────

    def _load_frames(self) -> None:
        pngs = sorted(self._asset_dir.glob("frame_*.png"))
        if not pngs:
            raise FileNotFoundError(
                f"No face frames found in {self._asset_dir}. "
                "Expected src/tanu/assets/idle/frame_*.png"
            )
        for p in pngs:
            im = Image.open(p).convert("RGBA")
            if im.size != (self._cfg_w, self._cfg_h):
                im = im.resize((self._cfg_w, self._cfg_h), Image.Resampling.LANCZOS)
            bg = Image.new("RGBA", im.size, DEFAULT_BG + (255,))
            self._frames.append(Image.alpha_composite(bg, im).convert("RGB"))
        LOG.info("Loaded %d face frames from %s", len(self._frames), self._asset_dir)

    # ── public API (called from WS thread) ─────────────────────────────────

    def set_connected(self, connected: bool) -> None:
        with self._lock:
            self._connected = connected
            self._status = "Connected" if connected else "Connecting..."

    def set_state(self, state: str) -> None:
        with self._lock:
            self._state = state if state in STATE_COLORS else "idle"

    def set_response(self, text: str) -> None:
        with self._lock:
            self._response = text[:512] if text else ""

    def set_status(self, text: str) -> None:
        with self._lock:
            self._status = text

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def close(self) -> None:
        self.stop()
        if self._fb_map is not None:
            self._fb_map.close()
            self._fb_map = None
        if self._fb_fd is not None:
            os.close(self._fb_fd)
            self._fb_fd = None

    # ── render loop ────────────────────────────────────────────────────────

    def _loop(self) -> None:
        interval = 1.0 / max(self._fps, 1)
        while not self._stop.is_set():
            start = time.time()
            self._render()
            elapsed = time.time() - start
            if elapsed < interval:
                self._stop.wait(interval - elapsed)

    def _render(self) -> None:
        with self._lock:
            state = self._state
            status = self._status
            response = self._response
            connected = self._connected

        if not self._frames:
            return

        frame = self._frames[self._frame_idx % len(self._frames)]
        self._frame_idx += 1
        canvas = frame.copy()

        draw = ImageDraw.Draw(canvas)
        accent = STATE_COLORS.get(state, STATE_COLORS["idle"])

        # status line at the top
        if connected:
            draw.text((6, 6), status, font=self._small_font(), fill=accent)
        # response ticker near the bottom
        draw.text(
            (6, canvas.height - 22),
            response,
            font=self._small_font(),
            fill=(0xBB, 0xBB, 0xBB),
        )

        if self._rotation:
            angle = self._rotation
            if angle == 90:
                canvas = canvas.transpose(Image.Transpose.ROTATE_270)
            elif angle == 180:
                canvas = canvas.transpose(Image.Transpose.ROTATE_180)
            elif angle == 270:
                canvas = canvas.transpose(Image.Transpose.ROTATE_90)

        self._blit(canvas)

    def _small_font(self):
        try:
            path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
            if path.exists():
                return ImageFont.truetype(str(path), 12)
        except OSError:
            pass
        return ImageFont.load_default()

    def _blit(self, image: Image.Image) -> None:
        data = _convert_frame_to_rgb565(image)
        w_bytes = image.width * 2
        # Clamp pitch/rows to the actual mapped size so we can never write
        # past smem_len (would otherwise SIGBUS on a small/tight framebuffer).
        pitch = min(self._line_length, self._smem_len // max(self._fb_height, 1))
        rows = min(image.height, self._fb_height, self._smem_len // max(pitch, 1))
        for y in range(rows):
            row = data[y * w_bytes:(y + 1) * w_bytes]
            offset = min(y * pitch, self._smem_len - w_bytes)
            self._fb_map[offset:offset + w_bytes] = row


def _handle_event(panel: "FbdevPanel", data: dict) -> None:
    """Map a parsed WS JSON event onto the panel (mirrors app.py state handling)."""
    msg_type = data.get("type", "")
    if msg_type == "_connected":
        panel.set_connected(True)
    elif msg_type == "_disconnected":
        panel.set_connected(False)
    elif msg_type == "state":
        panel.set_state(data.get("state", "idle"))
    elif msg_type == "token":
        panel.set_response(data.get("content", ""))
    elif msg_type == "response":
        panel.set_response(data.get("content", ""))
    elif msg_type == "status":
        provider = data.get("provider", "")
        model = data.get("model", "")
        if provider:
            panel.set_status(f"{provider} / {model}")
    elif msg_type == "tool_start":
        panel.set_state("thinking")
        panel.set_status(f"Using: {data.get('name', '')}...")
    elif msg_type == "tool_done":
        panel.set_status("Thinking...")
    elif msg_type == "done":
        panel.set_state("idle")
        panel.set_status("Connected")
    elif msg_type == "error":
        panel.set_state("error")
        panel.set_status(data.get("message") or data.get("content") or "Error")


def run_panel(cfg: dict, ws_url: str) -> None:
    """Build an FbdevPanel, feed it from WSClient, and run until Ctrl-C.

    Imported lazily so 'main.py desk --panel' doesn't require websocket libs
    for normal window mode.
    """
    from tanu.desktop.ws_client import WSClient

    panel = FbdevPanel(cfg, ws_url=ws_url)
    panel.start()

    ws = WSClient(panel._ws_url, session_id="panel:fbdev")
    ws.start()
    ws.send({"type": "status"})

    try:
        while not panel._stop.is_set():
            try:
                data = ws.events.get(timeout=0.5)
            except Exception:
                data = None
            if isinstance(data, dict):
                _handle_event(panel, data)
    except KeyboardInterrupt:
        pass
    finally:
        panel.close()
        ws.stop()
