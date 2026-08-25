"""
Animated character face.

Ports src/godot/scripts/character.gd: a state machine that renders Tanu's
face procedurally with one distinct animation and accent color per agent
state (idle / listening / thinking / speaking / error).
"""

import math

import pygame

IDLE = "idle"
LISTENING = "listening"
THINKING = "thinking"
SPEAKING = "speaking"
ERROR = "error"

TAU = math.tau

FACE_COLOR = (26, 26, 46)
STATE_COLORS = {
    IDLE: (0, 212, 255),
    LISTENING: (0, 255, 136),
    THINKING: (255, 170, 0),
    SPEAKING: (255, 0, 255),
    ERROR: (255, 68, 68),
}


def _rgba(color, alpha):
    return (color[0], color[1], color[2], max(0, min(255, int(alpha * 255))))


class Character:
    def __init__(self, face_radius: float = 80.0, accent_color=(0, 212, 255)):
        self.face_radius = face_radius
        self.accent_color = accent_color
        self.state = IDLE
        self.t = 0.0

    def set_state(self, name: str):
        if name in STATE_COLORS:
            self.state = name

    def update(self, dt: float):
        self.t += dt

    def draw(self, surface: pygame.Surface, center: tuple[float, float]):
        r = self.face_radius
        color = STATE_COLORS.get(self.state, self.accent_color)

        layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)

        glow_alpha = 0.2 + 0.1 * math.sin(self.t * 2.0)
        pygame.draw.circle(layer, _rgba(color, glow_alpha), center, int(r + 20))
        pygame.draw.circle(layer, FACE_COLOR + (255,), center, int(r))

        if self.state == IDLE:
            self._draw_idle(layer, center, color)
        elif self.state == LISTENING:
            self._draw_listening(layer, center, color)
        elif self.state == THINKING:
            self._draw_thinking(layer, center, color)
        elif self.state == SPEAKING:
            self._draw_speaking(layer, center, color)
        elif self.state == ERROR:
            self._draw_error(layer, center, color)

        surface.blit(layer, (0, 0))

    def _draw_idle(self, layer, center, color):
        breathe = math.sin(self.t * 1.5) * 3
        pygame.draw.circle(layer, color + (255,), center, max(1, int(4 + breathe)))

        for i in range(3):
            angle = self.t * 0.5 + i * TAU / 3
            pos = (
                center[0] + math.cos(angle) * (self.face_radius * 0.6),
                center[1] + math.sin(angle) * (self.face_radius * 0.6),
            )
            pygame.draw.circle(layer, _rgba(color, 0.4), pos, 2)

    def _draw_listening(self, layer, center, color):
        for i in range(3):
            ring_radius = self.face_radius * 0.4 + i * 15
            alpha = 0.6 - i * 0.15
            pulse = math.sin(self.t * 4.0 + i) * 5
            pygame.draw.circle(
                layer,
                _rgba(color, alpha),
                center,
                max(2, int(ring_radius + pulse)),
                2,
            )
        pygame.draw.circle(layer, color + (255,), center, 6)

    def _draw_thinking(self, layer, center, color):
        for i in range(5):
            angle = self.t * 3.0 + i * TAU / 5
            rr = self.face_radius * 0.5
            pos = (
                center[0] + math.cos(angle) * rr,
                center[1] + math.sin(angle) * rr,
            )
            dot_size = 3 + math.sin(self.t * 5 + i) * 1.5
            pygame.draw.circle(layer, _rgba(color, 0.7), pos, max(1, int(dot_size)))

        pulse = 0.5 + math.sin(self.t * 4) * 0.3
        pygame.draw.circle(layer, _rgba(color, pulse), center, 5)

    def _draw_speaking(self, layer, center, color):
        bar_count = 8
        bar_width = 6
        max_height = self.face_radius * 0.6

        for i in range(bar_count):
            angle = (i - bar_count / 2.0) * 0.2
            x = center[0] + angle * (self.face_radius * 0.8)
            height = max_height * (
                0.3 + 0.7 * abs(math.sin(self.t * 8.0 + i * 0.7))
            )
            alpha = 0.6 + 0.4 * math.sin(self.t * 3 + i)
            rect = pygame.Rect(
                int(x - bar_width / 2),
                int(center[1] - height / 2),
                bar_width,
                max(2, int(height)),
            )
            pygame.draw.rect(layer, _rgba(color, alpha), rect)

    def _draw_error(self, layer, center, color):
        if math.sin(self.t * 6.0) > 0:
            s = 15.0
            width = 3
            pygame.draw.line(
                layer,
                color + (255,),
                (center[0] - s, center[1] - s),
                (center[0] + s, center[1] + s),
                width,
            )
            pygame.draw.line(
                layer,
                color + (255,),
                (center[0] + s, center[1] - s),
                (center[0] - s, center[1] + s),
                width,
            )
