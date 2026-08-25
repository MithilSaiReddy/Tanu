"""
Main desktop application loop.

Two display modes:
  - "window": 400x400 desktop window with chat input (default)
  - "panel":  small TFT framebuffer (e.g. ILI9341 320x240) showing the
              animated face, status bar, and a response ticker — designed
              for SBCs without keyboard/touch; voice is the input.
"""

import queue

import pygame

from .character import (
    ERROR,
    IDLE,
    SPEAKING,
    THINKING,
    Character,
)
from .panel import apply_panel_env, get_panel_cfg
from .widgets import Button, InputField, ResponseArea, StatusBar
from .ws_client import WSClient


def _font(size: int) -> pygame.font.Font:
    return pygame.font.SysFont(
        "dejavusansmono,consolas,menlo,monospace,couriernew", size
    )


class TanuDesktopApp:
    WIDTH = 400
    HEIGHT = 400
    BG = (20, 20, 31)

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7337,
        display_mode: str = "window",
        cfg: dict | None = None,
    ):
        self.ws = WSClient(f"ws://{host}:{port}/ws/chat")
        self.character = Character()
        self.display_mode = display_mode
        self.cfg = cfg or {}
        self.panel_cfg = get_panel_cfg(self.cfg)

        self.connected = False
        self.is_generating = False
        self.current_response = ""
        self.status_text = "Connecting..."

    def run(self):
        if self.display_mode == "panel":
            apply_panel_env(self.panel_cfg)

        pygame.init()
        try:
            pygame.scrap.init()
        except pygame.error:
            pass

        fps = 60
        rotation = 0
        w, h = self.WIDTH, self.HEIGHT
        if self.display_mode == "panel":
            w = self.panel_cfg["width"]
            h = self.panel_cfg["height"]
            fps = max(5, min(60, self.panel_cfg["fps"]))
            rotation = self.panel_cfg["rotation"]

        if self.display_mode == "panel" and rotation in (90, 270):
            try:
                screen = pygame.display.set_mode((h, w))
            except pygame.error as e:
                print(f"[desktop] Could not open panel framebuffer: {e}")
                pygame.quit()
                return
            canvas = pygame.Surface((w, h))
        else:
            try:
                screen = pygame.display.set_mode((w, h))
            except pygame.error as e:
                print(f"[desktop] Could not open a display: {e}")
                pygame.quit()
                return
            canvas = screen

        pygame.display.set_caption("Tanu")

        status_font = _font(15)
        body_font = _font(15)
        pad = 10
        input_field = None
        send_button = None

        top_bar = StatusBar((pad, pad), status_font)

        if self.display_mode == "panel":
            bar_h = 20
            line_h = body_font.get_linesize()
            ticker_h = line_h * 4 + 8
            response = ResponseArea(
                pygame.Rect(pad, h - pad - ticker_h, w - pad * 2, ticker_h),
                body_font,
            )
            area_top = pad + bar_h + 4
            face_cy = area_top + (h - pad - ticker_h - area_top) // 2
            face_center = (w // 2, face_cy)
            face_radius = min((h - pad * 2 - bar_h - ticker_h) // 2 - 6, w // 2 - 16)
            self.character.face_radius = max(30, face_radius)
        else:
            bar_h = 24
            row_h = 34
            response = ResponseArea(
                pygame.Rect(pad, pad + bar_h, w - pad * 2, h - pad * 3 - bar_h - row_h),
                body_font,
            )
            input_field = InputField(
                pygame.Rect(pad, h - pad - row_h, w - pad * 3 - 74, row_h),
                body_font,
                placeholder="Type a message...",
            )
            input_field.on_submit = lambda: self._send(input_field)
            send_button = Button(
                pygame.Rect(w - pad - 74, h - pad - row_h, 74, row_h),
                "Send",
                status_font,
            )
            send_button.on_click = lambda: self._send(input_field)
            face_center = (w // 2, h // 2 + 10)

        clock = pygame.time.Clock()
        self.ws.start()

        try:
            while True:
                dt = clock.tick(fps) / 1000.0

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        return
                    if input_field is None:
                        response.handle_event(event)
                        continue
                    if (
                        event.type == pygame.KEYDOWN
                        and event.key == pygame.K_RETURN
                        and (event.mod & pygame.KMOD_CTRL)
                    ):
                        self._send(input_field)
                        continue
                    if response.handle_event(event):
                        continue
                    if send_button.handle_event(event):
                        continue
                    if event.type == pygame.TEXTINPUT:
                        mods = pygame.key.get_mods()
                        if mods & (pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META):
                            continue
                    input_field.handle_event(event)

                self._drain_ws(response)

                self.character.update(dt)

                canvas.fill(self.BG)
                self.character.draw(canvas, face_center)
                top_bar.draw(canvas, self.ws.is_connected(), self.status_text)
                response.draw(canvas)
                if input_field is not None:
                    input_field.draw(canvas)
                    send_button.draw(canvas)

                if canvas is not screen:
                    rotated = pygame.transform.rotate(canvas, rotation)
                    screen.blit(
                        rotated,
                        (
                            (screen.get_width() - rotated.get_width()) // 2,
                            (screen.get_height() - rotated.get_height()) // 2,
                        ),
                    )
                pygame.display.flip()
        finally:
            self.ws.stop()
            pygame.quit()

    def _send(self, input_field):
        text = input_field.text.strip()
        if not text or self.is_generating:
            return
        input_field.clear()
        self.current_response = ""
        self.is_generating = True
        self.ws.send_chat(text)
        self.status_text = "Thinking..."

    def _drain_ws(self, response: ResponseArea):
        while True:
            try:
                data = self.ws.events.get_nowait()
            except queue.Empty:
                break
            self._handle_message(data, response)

    def _handle_message(self, data: dict, response: ResponseArea):
        msg_type = data.get("type", "")

        if msg_type == "_connected":
            self.connected = True
            self.status_text = "Ready"
            self.character.set_state(IDLE)
            self.ws.request_status()

        elif msg_type == "_disconnected":
            self.connected = False
            self.status_text = "Disconnected — reconnecting..."
            self.character.set_state(ERROR)

        elif msg_type == "token":
            self.current_response += data.get("content", "")
            response.set_text(self.current_response)
            self.status_text = "Speaking..."
            self.character.set_state(SPEAKING)

        elif msg_type == "tool_start":
            name = data.get("name", "")
            self.status_text = f"Using: {name}..."
            self.character.set_state(THINKING)

        elif msg_type == "tool_done":
            self.status_text = "Thinking..."

        elif msg_type == "response":
            self.current_response = data.get("content", "")
            response.set_text(self.current_response)

        elif msg_type == "done":
            self.is_generating = False
            self.status_text = "Ready"
            self.character.set_state(IDLE)

        elif msg_type == "error":
            self.is_generating = False
            err = data.get("message") or data.get("content") or "Unknown error"
            response.set_text(f"Error: {err}", error=True)
            self.status_text = "Error"
            self.character.set_state(ERROR)

        elif msg_type == "state":
            state = data.get("state", "idle")
            if state == "thinking":
                self.status_text = "Thinking..."
            elif state == "speaking":
                self.status_text = "Speaking..."
            elif state == "idle":
                self.status_text = "Ready"
            self.character.set_state(state)

        elif msg_type == "status":
            provider = data.get("provider", "")
            model = data.get("model", "")
            if provider:
                self.status_text = f"{provider} / {model}"


def run_app(
    host: str = "127.0.0.1",
    port: int = 7337,
    display_mode: str = "window",
    cfg: dict | None = None,
):
    TanuDesktopApp(
        host=host, port=port, display_mode=display_mode, cfg=cfg
    ).run()
