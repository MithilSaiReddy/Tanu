"""
UI widgets for the desktop chat interface.

Replaces the Control nodes from src/godot/scenes/main.tscn: connection
dot + status bar, scrollable response area, text input field, and the
send button.
"""

import pygame


def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    lines = []
    for raw in text.split("\n"):
        if not raw:
            lines.append("")
            continue
        cur = ""
        for word in raw.split(" "):
            trial = f"{cur} {word}" if cur else word
            if font.size(trial)[0] <= max_width:
                cur = trial
                continue
            if cur:
                lines.append(cur)
                cur = ""
            while font.size(word)[0] > max_width and len(word) > 1:
                cut = len(word)
                while cut > 1 and font.size(word[:cut])[0] > max_width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            cur = word
        lines.append(cur)
    return lines


class StatusBar:
    DOT_GREEN = (0, 255, 136)
    DOT_RED = (255, 68, 68)
    TEXT_COLOR = (200, 200, 215)

    def __init__(self, pos, font):
        self.pos = pos
        self.font = font

    def draw(self, surface, connected: bool, status_text: str):
        x, y = self.pos
        dot_color = self.DOT_GREEN if connected else self.DOT_RED
        pygame.draw.circle(surface, dot_color, (x + 5, y + 10), 5)
        label = self.font.render(status_text, True, self.TEXT_COLOR)
        surface.blit(label, (x + 16, y))


class ResponseArea:
    BG = (26, 26, 40)
    TEXT_COLOR = (220, 220, 230)
    ERROR_COLOR = (255, 68, 68)

    def __init__(self, rect: pygame.Rect, font):
        self.rect = rect
        self.font = font
        self.text = ""
        self.error = False
        self._follow = True
        self._scroll = 0

    def set_text(self, text: str, error: bool = False):
        self.text = text
        self.error = error
        self._follow = True
        self._scroll = 0

    def append(self, chunk: str):
        self.text += chunk

    def clear(self):
        self.set_text("")

    def handle_event(self, event):
        if event.type == pygame.MOUSEWHEEL and self.rect.collidepoint(pygame.mouse.get_pos()):
            if event.y > 0:
                self._follow = False
                self._scroll += event.y
            elif event.y < 0:
                self._scroll = max(0, self._scroll + event.y)
                if self._scroll == 0:
                    self._follow = True

    def draw(self, surface):
        pygame.draw.rect(surface, self.BG, self.rect)

        line_h = self.font.get_linesize()
        pad = 6
        inner_w = self.rect.width - pad * 2
        max_lines = max(1, (self.rect.height - pad * 2) // line_h)

        lines = wrap_text(self.text or "", self.font, inner_w) if self.text else []
        total = len(lines)

        if self._follow:
            start = max(0, total - max_lines)
        else:
            start = max(0, min(int(self._scroll), total - max_lines))

        color = self.ERROR_COLOR if self.error else self.TEXT_COLOR
        view = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        for i, line in enumerate(lines[start : start + max_lines]):
            img = self.font.render(line, True, color)
            view.blit(img, (pad, pad + i * line_h))
        surface.blit(view, self.rect.topleft)


class InputField:
    BG = (34, 34, 52)
    BORDER = (60, 60, 90)
    FOCUS_BORDER = (0, 212, 255)
    TEXT_COLOR = (235, 235, 240)
    PLACEHOLDER_COLOR = (120, 120, 140)

    def __init__(self, rect: pygame.Rect, font, placeholder="", on_submit=None):
        self.rect = rect
        self.font = font
        self.placeholder = placeholder
        self.on_submit = on_submit
        self.text = ""
        self.focused = True

    def clear(self):
        self.text = ""

    def handle_event(self, event):
        if not self.focused:
            return False
        if event.type == pygame.TEXTINPUT:
            self.text += event.text
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN and not (event.mod & pygame.KMOD_CTRL):
                if self.text.strip() and self.on_submit:
                    self.on_submit()
                return True
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
                return True
            if event.key in (pygame.K_v,) and (event.mod & pygame.KMOD_CTRL):
                try:
                    self.text += pygame.scrap.get_text().decode("utf-8", "replace")
                except pygame.error:
                    pass
                return True
        return False

    def draw(self, surface):
        pygame.draw.rect(surface, self.BG, self.rect)
        border = self.FOCUS_BORDER if self.focused else self.BORDER
        pygame.draw.rect(surface, border, self.rect, 1)

        pad_x = 8
        text = self.text if self.text else self.placeholder
        color = self.TEXT_COLOR if self.text else self.PLACEHOLDER_COLOR
        img = self.font.render(text, True, color)

        max_w = self.rect.width - pad_x * 2
        clip_w = min(img.get_width(), max_w)
        surface.blit(img, (self.rect.x + pad_x, self.rect.centery - img.get_height() // 2),
                     area=pygame.Rect(0, 0, clip_w, img.get_height()))

        if self.focused and (pygame.time.get_ticks() // 500) % 2 == 0:
            cursor_x = self.rect.x + pad_x + min(img.get_width(), max_w) + 1
            if not self.text:
                cursor_x = self.rect.x + pad_x
            pygame.draw.line(
                surface,
                self.TEXT_COLOR,
                (cursor_x, self.rect.y + 6),
                (cursor_x, self.rect.bottom - 6),
                1,
            )


class Button:
    BG = (0, 130, 155)
    HOVER_BG = (0, 212, 255)
    TEXT_COLOR = (10, 12, 20)

    def __init__(self, rect: pygame.Rect, label: str, font, on_click=None):
        self.rect = rect
        self.label = label
        self.font = font
        self.on_click = on_click

    def handle_event(self, event):
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        ):
            if self.on_click:
                self.on_click()
            return True
        return False

    def draw(self, surface):
        hover = self.rect.collidepoint(pygame.mouse.get_pos())
        color = self.HOVER_BG if hover else self.BG
        pygame.draw.rect(surface, color, self.rect, border_radius=4)
        img = self.font.render(self.label, True, self.TEXT_COLOR)
        surface.blit(
            img,
            (
                self.rect.centerx - img.get_width() // 2,
                self.rect.centery - img.get_height() // 2,
            ),
        )
