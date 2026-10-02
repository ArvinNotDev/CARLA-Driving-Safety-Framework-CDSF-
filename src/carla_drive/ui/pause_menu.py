"""In-drive pause menu with reverse-beep, session setup, and resume actions."""

from __future__ import annotations

import pygame


class PauseMenu:
    ACTIONS = ("reverse_beep", "menu", "resume")

    def __init__(self, screen: pygame.Surface, reverse_beep):
        self.screen = screen
        self.reverse_beep = reverse_beep
        self.clock = pygame.time.Clock()
        self.title_font = pygame.font.SysFont("Segoe UI", 34, bold=True)
        self.body_font = pygame.font.SysFont("Segoe UI", 18)
        self.button_font = pygame.font.SysFont("Segoe UI", 20, bold=True)
        self.emoji_font = pygame.font.SysFont("Segoe UI Emoji", 22)
        self.focus = 2
        self.buttons: list[tuple[str, pygame.Rect]] = []

    def run(self) -> str:
        pygame.display.set_caption("CARLA Drive | Paused")
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return "resume"
                    if event.key in (pygame.K_UP, pygame.K_w):
                        self.focus = (self.focus - 1) % len(self.ACTIONS)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        self.focus = (self.focus + 1) % len(self.ACTIONS)
                    elif event.key == pygame.K_m:
                        self.reverse_beep.toggle_muted()
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        result = self._activate(self.ACTIONS[self.focus])
                        if result:
                            return result
                elif event.type == pygame.MOUSEMOTION:
                    for index, (_, rect) in enumerate(self.buttons):
                        if rect.collidepoint(event.pos):
                            self.focus = index
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for action, rect in self.buttons:
                        if rect.collidepoint(event.pos):
                            result = self._activate(action)
                            if result:
                                return result
            self._draw()
            pygame.display.flip()
            self.clock.tick(60)

    def _activate(self, action: str) -> str | None:
        if action == "reverse_beep":
            self.reverse_beep.toggle_muted()
            return None
        if action == "menu":
            return "menu"
        return "resume"

    def _draw(self) -> None:
        width, height = self.screen.get_size()
        self.screen.fill((5, 12, 20))
        pygame.draw.rect(self.screen, (10, 25, 37), (0, 0, width, 4))
        card = pygame.Rect(width // 2 - 250, height // 2 - 205, 500, 410)
        pygame.draw.rect(self.screen, (13, 27, 41), card, border_radius=20)
        pygame.draw.rect(self.screen, (41, 70, 86), card, width=1, border_radius=20)
        title = self.title_font.render("PAUSED", True, (237, 245, 248))
        self.screen.blit(title, title.get_rect(center=(width // 2, card.y + 55)))
        subtitle = self.body_font.render("Session controls", True, (136, 160, 173))
        self.screen.blit(subtitle, subtitle.get_rect(center=(width // 2, card.y + 92)))

        labels = (
            "Unmute reverse beep" if self.reverse_beep.muted else "Mute reverse beep",
            "Return to session setup",
            "Resume driving",
        )
        icons = ("🔇" if self.reverse_beep.muted else "🔊", "↩", "▶")
        self.buttons = []
        for index, (action, label, icon) in enumerate(zip(self.ACTIONS, labels, icons)):
            rect = pygame.Rect(card.x + 42, card.y + 130 + index * 74, card.w - 84, 58)
            self.buttons.append((action, rect))
            focused = index == self.focus
            fill = (27, 63, 73) if focused else (19, 39, 53)
            edge = (77, 208, 190) if focused else (41, 70, 86)
            pygame.draw.rect(self.screen, fill, rect, border_radius=12)
            pygame.draw.rect(self.screen, edge, rect, width=2 if focused else 1, border_radius=12)
            icon_surface = self.emoji_font.render(icon, True, (77, 208, 190))
            label_surface = self.button_font.render(label, True, (237, 245, 248))
            self.screen.blit(icon_surface, (rect.x + 18, rect.centery - icon_surface.get_height() // 2))
            self.screen.blit(label_surface, (rect.x + 60, rect.centery - label_surface.get_height() // 2))

        hint = self.body_font.render("↑ / ↓ Select    Enter Confirm    Esc Resume", True, (136, 160, 173))
        self.screen.blit(hint, hint.get_rect(center=(width // 2, card.bottom - 24)))
