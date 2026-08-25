"""
Main desktop application loop.

Ports src/godot/scripts/main.gd plus the window config from project.godot:
owns the 400x400 pygame window, routes WebSocket messages to the UI,
and handles user input.
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

    def __init__(self, host: str = "127.0.0.1", port: int = 7337):
        self.ws = WSClient(f"ws://{host}:{port}/ws/chat")
        self.character = Character()

        self.connected = False
        self.is_generating = False
        self.current_response = ""
        self.status_text = "Connecting..."

    def run(self):
        pygame.init()
        pygame.scrap.init()
        try:
            screen = pygame.display.set_mode((self.WIDTH, self.HEIGHT))
        except pygame.error as e:
            print(f"[desktop] Could not open a display window: {e}")
            pygame.quit()
            return

        pygame.display.set_caption("Tanu")

        status_font = _font(15)
        body_font = _font(15)

        pad = 10
        bar_h = 24
        row_h = 34

        top_bar = StatusBar((pad, pad), status_font)
        response = ResponseArea(
            pygame.Rect(pad, pad + bar_h, self.WIDTH - pad * 2, self.HEIGHT - pad * 3 - bar_h - row_h),
            body_font,
        )
        input_field = InputField(
            pygame.Rect(pad, self.HEIGHT - pad - row_h, self.WIDTH - pad * 3 - 74, row_h),
            body_font,
            placeholder="Type a message...",
        )
        input_field.on_submit = lambda: self._send(input_field)
        send_button = Button(
            pygame.Rect(self.WIDTH - pad - 74, self.HEIGHT - pad - row_h, 74, row_h),
            "Send",
            status_font,
        )
        send_button.on_click = lambda: self._send(input_field)

        clock = pygame.time.Clock()
        self.ws.start()

        try:
            while True:
                dt = clock.tick(60) / 1000.0

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        return
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

                screen.fill(self.BG)
                top_bar.draw(screen, self.ws.is_connected(), self.status_text)
                response.draw(screen)
                input_field.draw(screen)
                send_button.draw(screen)
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


def run_app(host: str = "127.0.0.1", port: int = 7337):
    TanuDesktopApp(host=host, port=port).run()
