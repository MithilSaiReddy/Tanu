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
FBIO_PAN_DISPLAY    = 0x4619

# fb_var_screeninfo activate flags used for double-buffered panning.
FB_ACTIVATE_NOW     = 0
FB_ACTIVATE_VBL     = 16

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
            val = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            out[i] = val & 0xFF
            out[i + 1] = (val >> 8) & 0xFF
            i += 2
    return bytes(out)


class FbdevPanel:
    """Animate the Tanu face to a Linux framebuffer and drive it over WS."""

    def __init__(self, cfg: dict, asset: Optional[Path] = None,
                 ws_url: str = "ws://127.0.0.1:7337/ws/chat"):
        self._device = cfg.get("device", "/dev/fb0")
        self._cfg_w = int(cfg.get("width", 320))
        self._cfg_h = int(cfg.get("height", 240))
        self._fps = int(cfg.get("fps", 24))
        self._speed = float(cfg.get("speed", 1.0)) or 1.0
        self._rotation = int(cfg.get("rotation", 0)) % 360
        self._vsync = bool(cfg.get("vsync", False))
        self._show_fps = bool(cfg.get("show_fps", False))
        self._ws_url = ws_url

        # Prefer the source GIF; fall back to a directory of pre-split PNGs.
        self._asset = Path(asset) if asset is not None else (
            Path(__file__).resolve().parent.parent / "assets" / "idle.gif"
        )
        self._frames: list[Image.Image] = []
        self._durations: list[float] = []
        self._frame_rgb: list[bytes] = []
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
        self._fb_var = b"\0" * 160

        self._font = self._load_font()
        self._double_buffered = False
        self._pan_supported = False
        self._current_page = 0

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
        self._fb_var = var
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

        if self._vsync:
            self._try_enable_double_buffer()

    # ── frames ─────────────────────────────────────────────────────────────

    def _load_frames(self) -> None:
        asset = self._asset
        frames: list[Image.Image] = []
        durations: list[float] = []

        if asset.is_dir():
            for p in sorted(asset.glob("frame_*.png")):
                frames.append(Image.open(p))
        elif asset.is_file() and asset.suffix.lower() in (".gif", ".png"):
            im = Image.open(asset)
            n = getattr(im, "n_frames", 1)
            for i in range(n):
                im.seek(i)
                frames.append(im.convert("RGBA"))
                ms = im.info.get("duration", 0) or 0
                durations.append(ms / 1000.0)  # ms -> seconds
        else:
            raise FileNotFoundError(
                f"No face animation found at {asset}.\n"
                "Expected src/tanu/assets/idle.gif or a directory of frame_*.png"
            )

        if not frames:
            raise FileNotFoundError(f"No face frames found in {asset}.")

        for im in frames:
            rgba = im.convert("RGBA")
            if rgba.size != (self._cfg_w, self._cfg_h):
                rgba = rgba.resize((self._cfg_w, self._cfg_h), Image.Resampling.LANCZOS)
            bg = Image.new("RGBA", rgba.size, DEFAULT_BG + (255,))
            rgb = Image.alpha_composite(bg, rgba).convert("RGB")
            self._frames.append(rgb)
            # Pre-pack the static face once so the render loop only blits it
            # (fast) instead of re-converting 76k pixels every frame.
            self._frame_rgb.append(_convert_frame_to_rgb565(rgb))

        # Per-frame hold time: honour the GIF's own duration if present,
        # otherwise fall back to a constant 1/fps. speed multiplies playback.
        if len(durations) == len(self._frames) and all(d > 0 for d in durations):
            self._durations = [d / self._speed for d in durations]
        else:
            self._durations = [1.0 / max(self._fps, 1) / self._speed
                               for _ in self._frames]
        LOG.info("Loaded %d face frames from %s (speed x%.1f)",
                 len(self._frames), self._asset, self._speed)

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
        if not self._durations:
            return
        # Steady cadence clock: schedule each frame on an absolute monotonic
        # timeline, advancing by that frame's hold time. The average rate stays
        # exact (and jitter-free) even if a single render stalls.
        next_t = time.monotonic()
        last_log = time.monotonic()
        log_frames = 0

        while not self._stop.is_set():
            delay = next_t - time.monotonic()
            if delay > 0:
                if self._stop.wait(delay):
                    break
            self._render()
            # duration of the frame that was just drawn (render advanced idx);
            # the NEXT frame is scheduled that far out.
            just_shown = (self._frame_idx - 1) % len(self._durations)
            next_t += self._durations[just_shown]
            if next_t < time.monotonic() - 1.0:
                # Fell far behind (e.g. display choked); resync so we don't
                # spin in a catch-up burst.
                next_t = time.monotonic()

            if self._show_fps:
                log_frames += 1
                now = time.monotonic()
                if now - last_log >= 5.0:
                    LOG.info("panel fps: %.1f (%d frames in %.1fs)",
                             log_frames / (now - last_log), log_frames,
                             now - last_log)
                    last_log = now
                    log_frames = 0

    def _render(self) -> None:
        with self._lock:
            state = self._state
            status = self._status
            response = self._response
            connected = self._connected

        if not self._frames:
            return

        idx = self._frame_idx % len(self._frames)
        self._frame_idx += 1

        # Orientation of the pre-packed face must match the text overlay, so
        # build the final image once when rotation is active; otherwise blit
        # the cached RGB bytes straight to the fb (no per-frame conversion).
        if self._rotation:
            face = self._frames[idx].copy()
            face = self._rotate(face, self._rotation)
            self._blit(face)
        else:
            self._blit_bytes(self._frame_rgb[idx])

        accent = STATE_COLORS.get(state, STATE_COLORS["idle"])
        if connected:
            self._overlay_text(status, (6, 6), accent)
        self._overlay_text(response, (6, self._cfg_h - 22), (0xBB, 0xBB, 0xBB))

        if self._pan_supported:
            self._pan_page(self._current_page)
            self._current_page = 1 - self._current_page

    @staticmethod
    def _rotate(image: Image.Image, angle: int) -> Image.Image:
        if angle == 90:
            return image.transpose(Image.Transpose.ROTATE_270)
        if angle == 180:
            return image.transpose(Image.Transpose.ROTATE_180)
        if angle == 270:
            return image.transpose(Image.Transpose.ROTATE_90)
        return image

    def _overlay_text(self, text: str, at: tuple[int, int], color: tuple[int, int, int]) -> None:
        """Render a short text string and overwrite it onto the framebuffer."""
        if not text:
            return
        font = self._small_font()
        tmp = Image.new("RGBA", (self._cfg_w, 24), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((0, 0), text, font=font, fill=color + (255,))
        data = _convert_frame_to_rgb565(tmp)
        x, y = at
        if x < 0:
            x = 0
        if y < 0:
            y = 0
        pitch = min(self._line_length, self._smem_len // max(self._fb_height, 1))
        w_bytes = min(self._cfg_w * 2, pitch, self._smem_len - x * 2)
        rows = min(tmp.height, self._fb_height - y,
                   max(self._smem_len // max(pitch, 1) - y, 0))
        base = self._back_page_offset()
        for r in range(rows):
            row = data[r * self._cfg_w * 2:(r * self._cfg_w * 2) + w_bytes]
            offset = (y + r) * pitch + x * 2 + base
            if offset + w_bytes <= self._smem_len:
                self._fb_map[offset:offset + w_bytes] = row

    def _small_font(self):
        return self._font

    @staticmethod
    def _load_font():
        try:
            path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
            if path.exists():
                return ImageFont.truetype(str(path), 12)
        except OSError:
            pass
        return ImageFont.load_default()

    # ── vsync / double buffering (best-effort) ─────────────────────────────

    def _try_enable_double_buffer(self) -> None:
        """Double-buffer via yres_virtual > yres + FBIOPAN_DISPLAY, if the
        driver supports it. Falls back silently to single-buffered writes."""
        xres, yres, xres_v, yres_v, bpp = _struct_screeninfo(self._fb_var)
        line_bytes = self._line_length * yres
        if xres_v > 0 and yres_v >= 2 * yres and self._smem_len >= 2 * line_bytes:
            # Try to request a virtual height of two pages so we can pan
            # between framebuffers (tear-free) — only if the driver honours it.
            var = bytearray(self._fb_var)
            struct.pack_into("=I", var, 12, 2 * yres)   # yres_virtual
            struct.pack_into("=I", var, 84, FB_ACTIVATE_VBL)  # activate flag
            try:
                fcntl.ioctl(self._fb_fd, 0x4601, var)  # FBIOPUT_VSCREENINFO
            except OSError:
                pass
            else:
                # Remap to cover both pages so we can write a full frame into
                # the back buffer, then pan to it (tear-free).
                try:
                    self._fb_map.close()
                    two = min(self._line_length * yres * 2, self._smem_len)
                    self._fb_map = mmap.mmap(self._fb_fd, two)
                except (OSError, ValueError):
                    self._fb_map = mmap.mmap(self._fb_fd, self._line_length * yres)
                    self._double_buffered = False
                else:
                    self._double_buffered = True
                    self._pan_supported = True
                    self._current_page = 0
                    LOG.info("Double buffering enabled (2 x %d B)", line_bytes)
                    return
        LOG.info("fb does not support double buffering; using single buffer")

    def _pan_page(self, page: int) -> None:
        """Pan the display to page 0 or 1 (double buffered) or no-op."""
        if not self._pan_supported:
            return
        var = bytearray(self._fb_var)
        struct.pack_into("=I", var, 20, page * self._fb_height)  # yoffset
        struct.pack_into("=I", var, 84, FB_ACTIVATE_NOW)
        try:
            fcntl.ioctl(self._fb_fd, 0x4619, var)
        except OSError:
            pass

    def _back_page_offset(self) -> int:
        """Byte offset of the (hidden) page we should write this frame into."""
        if not self._double_buffered:
            return 0
        page = 1 - self._current_page
        return page * self._line_length * self._fb_height

    def _blit_bytes(self, data: bytes, width: int | None = None,
                    height: int | None = None, page_off: int | None = None) -> None:
        w = width or self._cfg_w
        h = height or self._cfg_h
        w_bytes = w * 2
        pitch = min(self._line_length, self._smem_len // max(self._fb_height, 1))
        rows = min(h, self._fb_height, self._smem_len // max(pitch, 1))
        base = page_off if page_off is not None else self._back_page_offset()
        if pitch == w_bytes:
            # Tightly packed — write the whole frame in one bus transaction
            # (atomic-ish, minimal SPI chatter, no per-row overhead).
            n = min(rows * w_bytes, self._smem_len - base)
            self._fb_map[base:base + n] = data[:n]
        else:
            for y in range(rows):
                row = data[y * w_bytes:(y + 1) * w_bytes]
                offset = min(y * pitch, self._smem_len - w_bytes) + base
                if offset + w_bytes <= self._smem_len:
                    self._fb_map[offset:offset + w_bytes] = row

    def _blit(self, image: Image.Image) -> None:
        self._blit_bytes(_convert_frame_to_rgb565(image), image.width, image.height)


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
