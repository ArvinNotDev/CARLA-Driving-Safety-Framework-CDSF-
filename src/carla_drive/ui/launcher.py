"""Session setup screen for CARLA Drive."""

from __future__ import annotations

from dataclasses import replace
import webbrowser

import pygame

from carla_drive.carla.session import VehicleOption, friendly_map_name
from carla_drive.config import SessionConfig

GITHUB_URL = "https://github.com/ArvinNotDev/"

BACKGROUND = (7, 15, 25)
PANEL = (13, 27, 41)
PANEL_EDGE = (34, 57, 73)
ROW = (19, 37, 52)
ROW_HOVER = (24, 48, 64)
ROW_ACTIVE = (25, 53, 68)
TEXT = (237, 245, 248)
MUTED = (136, 160, 173)
FAINT = (91, 119, 135)
ACCENT = (77, 208, 190)
GREEN = (83, 212, 159)


class Launcher:
    """Keyboard- and mouse-operable setup screen with compact dropdowns."""

    def __init__(
        self,
        screen: pygame.Surface,
        maps: list[str],
        weather: list[tuple[str, str]],
        vehicles: list[VehicleOption],
        defaults: SessionConfig,
    ):
        self.screen = screen
        if not maps:
            raise ValueError("CARLA reported no drivable Town maps. Check the server map installation.")
        if not weather or not vehicles:
            raise ValueError("CARLA reported no usable weather or four-wheel vehicle choices.")

        self.maps = maps
        self.weather = weather
        self.vehicles = vehicles
        self.defaults = defaults
        self.clock = pygame.time.Clock()
        self.font_title = pygame.font.SysFont("Segoe UI", 34, bold=True)
        self.font_heading = pygame.font.SysFont("Segoe UI", 19, bold=True)
        self.font_value = pygame.font.SysFont("Segoe UI", 20, bold=True)
        self.font_body = pygame.font.SysFont("Segoe UI", 16)
        self.font_small = pygame.font.SysFont("Segoe UI", 13)
        self.font_button = pygame.font.SysFont("Segoe UI", 16, bold=True)

        self.selected = {
            "map": self._find_index(self.maps, defaults.map_name, lambda value: friendly_map_name(value)),
            "weather": self._find_index(weather, defaults.weather_preset, lambda value: value[0]),
            "vehicle": self._find_index(vehicles, defaults.vehicle_blueprint, lambda value: value.blueprint_id),
        }
        self.traffic = defaults.traffic_vehicles
        self.pedestrians = defaults.pedestrians
        self.focus = 0
        self.status = ""
        self.open_dropdown: str | None = None
        self.menu_highlight = 0
        self.menu_scroll = 0

        self.row_rects: list[pygame.Rect] = []
        self.counter_controls: dict[int, tuple[pygame.Rect, pygame.Rect]] = {}
        self.dropdown_rect = pygame.Rect(0, 0, 0, 0)
        self.dropdown_option_rects: list[tuple[int, pygame.Rect]] = []
        self.github_rect = pygame.Rect(0, 0, 0, 0)
        self.start_rect = pygame.Rect(0, 0, 0, 0)

    @staticmethod
    def _find_index(items, selected, key):
        if selected is not None:
            selected_name = friendly_map_name(selected)
            for index, item in enumerate(items):
                item_key = key(item)
                if item_key == selected or item_key == selected_name:
                    return index
        return 0

    def run(self) -> SessionConfig | None:
        pygame.display.set_caption("CARLA Drive | Session Setup")
        while True:
            self.clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
                    result = self._key_action(event.key)
                    if result is not _CONTINUE:
                        return result
                elif event.type == pygame.MOUSEWHEEL:
                    self._scroll_dropdown(event.y)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    result = self._click(event.pos)
                    if result is not _CONTINUE:
                        return result

            self._draw()
            pygame.display.flip()

    def _key_action(self, key: int):
        if self.open_dropdown is not None:
            if key == pygame.K_ESCAPE:
                self.open_dropdown = None
            elif key in (pygame.K_UP, pygame.K_LEFT, pygame.K_w, pygame.K_a):
                self._move_dropdown(-1)
            elif key in (pygame.K_DOWN, pygame.K_RIGHT, pygame.K_s, pygame.K_d):
                self._move_dropdown(1)
            elif key == pygame.K_HOME:
                self._move_dropdown(-len(self._options(self.open_dropdown)))
            elif key == pygame.K_END:
                self._move_dropdown(len(self._options(self.open_dropdown)))
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._select_dropdown_item()
            return _CONTINUE

        if key == pygame.K_ESCAPE:
            return None
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return self._session_config()
        if key in (pygame.K_UP, pygame.K_w):
            self.focus = (self.focus - 1) % 5
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.focus = (self.focus + 1) % 5
        elif key in (pygame.K_LEFT, pygame.K_a):
            self._change(-1)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self._change(1)
        elif key == pygame.K_SPACE and self.focus < 3:
            self._open_dropdown(self.focus)
        return _CONTINUE

    def _click(self, position: tuple[int, int]):
        if self.open_dropdown is not None:
            for option_index, rect in self.dropdown_option_rects:
                if rect.collidepoint(position):
                    self.selected[self.open_dropdown] = option_index
                    self.open_dropdown = None
                    return _CONTINUE
            if self.dropdown_rect.collidepoint(position):
                return _CONTINUE
            self.open_dropdown = None

        if self.github_rect.collidepoint(position):
            self._open_github()
            return _CONTINUE
        if self.start_rect.collidepoint(position):
            return self._session_config()

        for index, rect in enumerate(self.row_rects):
            if not rect.collidepoint(position):
                continue
            self.focus = index
            if index < 3:
                self._open_dropdown(index)
                return _CONTINUE
            minus_rect, plus_rect = self.counter_controls[index]
            if minus_rect.collidepoint(position):
                self._change(-1, count_step=1, focused=index)
            elif plus_rect.collidepoint(position):
                self._change(1, count_step=1, focused=index)
            return _CONTINUE
        return _CONTINUE

    def _open_dropdown(self, field_index: int) -> None:
        field = ("map", "weather", "vehicle")[field_index]
        if self.open_dropdown == field:
            self.open_dropdown = None
            return
        self.open_dropdown = field
        self.menu_highlight = self.selected[field]
        self.menu_scroll = max(0, self.menu_highlight - 4)

    def _options(self, field: str) -> list[str]:
        if field == "map":
            return [friendly_map_name(name) for name in self.maps]
        if field == "weather":
            return [label for _, label in self.weather]
        return [vehicle.label for vehicle in self.vehicles]

    def _move_dropdown(self, direction: int) -> None:
        count = len(self._options(self.open_dropdown or "map"))
        self.menu_highlight = max(0, min(count - 1, self.menu_highlight + direction))
        self._keep_highlight_visible()

    def _keep_highlight_visible(self) -> None:
        visible_count = max(1, len(self.dropdown_option_rects))
        if self.menu_highlight < self.menu_scroll:
            self.menu_scroll = self.menu_highlight
        elif self.menu_highlight >= self.menu_scroll + visible_count:
            self.menu_scroll = self.menu_highlight - visible_count + 1

    def _select_dropdown_item(self) -> None:
        if self.open_dropdown is not None:
            self.selected[self.open_dropdown] = self.menu_highlight
            self.open_dropdown = None

    def _scroll_dropdown(self, direction: int) -> None:
        if self.open_dropdown is None or not self.dropdown_rect.collidepoint(pygame.mouse.get_pos()):
            return
        self._move_dropdown(-direction)

    def _change(self, direction: int, count_step: int = 5, focused: int | None = None) -> None:
        index = self.focus if focused is None else focused
        field = ("map", "weather", "vehicle")[index] if index < 3 else None
        if field is not None:
            self.selected[field] = (self.selected[field] + direction) % len(self._options(field))
        elif index == 3:
            self.traffic = max(0, min(200, self.traffic + direction * count_step))
        elif index == 4:
            self.pedestrians = max(0, min(200, self.pedestrians + direction * count_step))

    def _session_config(self) -> SessionConfig:
        return replace(
            self.defaults,
            map_name=self.maps[self.selected["map"]],
            weather_preset=self.weather[self.selected["weather"]][0],
            vehicle_blueprint=self.vehicles[self.selected["vehicle"]].blueprint_id,
            traffic_vehicles=self.traffic,
            pedestrians=self.pedestrians,
        )

    def _draw(self) -> None:
        width, height = self.screen.get_size()
        self.screen.fill(BACKGROUND)
        pygame.draw.rect(self.screen, (10, 25, 37), (0, 0, width, 126))
        pygame.draw.rect(self.screen, ACCENT, (0, 0, width, 3))

        self._draw_header(width)
        left_panel, right_panel = self._draw_panels(width, height)
        self._draw_settings(left_panel)
        self._draw_overview(right_panel)
        self._draw_footer(width, height)
        if self.open_dropdown is not None:
            self._draw_dropdown(height)

    def _draw_header(self, width: int) -> None:
        logo = pygame.Rect(32, 31, 46, 46)
        pygame.draw.rect(self.screen, (20, 59, 70), logo, border_radius=13)
        pygame.draw.rect(self.screen, ACCENT, logo, width=1, border_radius=13)
        self._text("CD", logo, self.font_button, ACCENT, center=True)
        self._text("CARLA DRIVE", (92, 30), self.font_title, TEXT)
        self._text("MANUAL DRIVING  /  SESSION SETUP", (94, 73), self.font_small, MUTED)

        badge = pygame.Rect(width - 254, 39, 222, 34)
        self._pill(badge, (17, 47, 48), (38, 83, 75))
        pygame.draw.circle(self.screen, GREEN, (badge.x + 16, badge.centery), 4)
        self._text("CARLA SERVER CONNECTED", (badge.x + 29, badge.y + 9), self.font_small, GREEN)

    def _draw_panels(self, width: int, height: int) -> tuple[pygame.Rect, pygame.Rect]:
        margin = 32
        gap = 20
        available = width - margin * 2 - gap
        left_width = int(available * 0.63)
        right_width = available - left_width
        top = 145
        panel_height = height - 240
        left = pygame.Rect(margin, top, left_width, panel_height)
        right = pygame.Rect(left.right + gap, top, right_width, panel_height)
        for rect in (left, right):
            pygame.draw.rect(self.screen, PANEL, rect, border_radius=18)
            pygame.draw.rect(self.screen, PANEL_EDGE, rect, width=1, border_radius=18)
        return left, right

    def _draw_settings(self, panel: pygame.Rect) -> None:
        self._text("Configure your drive", (panel.x + 20, panel.y + 19), self.font_heading, TEXT)
        self._text("Select a value or use the arrow keys", (panel.x + 20, panel.y + 47), self.font_small, MUTED)

        labels = ("MAP", "WEATHER", "EGO VEHICLE", "VEHICLE TRAFFIC", "PEDESTRIANS")
        values = (
            friendly_map_name(self.maps[self.selected["map"]]),
            self.weather[self.selected["weather"]][1],
            self.vehicles[self.selected["vehicle"]].label,
            str(self.traffic),
            str(self.pedestrians),
        )
        self.row_rects = []
        self.counter_controls = {}
        row_x = panel.x + 18
        row_width = panel.w - 36
        row_height = 62
        row_gap = 9
        row_start = panel.y + 82
        mouse = pygame.mouse.get_pos()

        for index, (label, value) in enumerate(zip(labels, values)):
            row = pygame.Rect(row_x, row_start + index * (row_height + row_gap), row_width, row_height)
            self.row_rects.append(row)
            hovered = row.collidepoint(mouse)
            color = ROW_ACTIVE if index == self.focus else ROW_HOVER if hovered else ROW
            pygame.draw.rect(self.screen, color, row, border_radius=11)
            if index == self.focus:
                pygame.draw.rect(self.screen, ACCENT, row, width=1, border_radius=11)
                pygame.draw.rect(self.screen, ACCENT, (row.x, row.y + 12, 3, row.h - 24), border_radius=2)

            self._text(label, (row.x + 17, row.y + 8), self.font_small, MUTED)
            if index < 3:
                self._text(self._fit(value, self.font_value, row.w - 94), (row.x + 17, row.y + 30), self.font_value, TEXT)
                chevron = pygame.Rect(row.right - 42, row.y + 15, 26, 30)
                pygame.draw.rect(self.screen, (26, 55, 68), chevron, border_radius=8)
                self._draw_chevron(chevron.center, ACCENT)
            else:
                unit = "VEHICLES" if index == 3 else "PEOPLE"
                self._text(value, (row.x + 17, row.y + 28), self.font_value, TEXT)
                value_width = self.font_value.size(value)[0]
                self._text(unit, (row.x + 27 + value_width, row.y + 35), self.font_small, MUTED)
                minus = pygame.Rect(row.right - 80, row.y + 15, 30, 32)
                plus = pygame.Rect(row.right - 42, row.y + 15, 30, 32)
                self.counter_controls[index] = (minus, plus)
                self._draw_counter_button(minus, "-", minus.collidepoint(mouse))
                self._draw_counter_button(plus, "+", plus.collidepoint(mouse))

    def _draw_overview(self, panel: pygame.Rect) -> None:
        x = panel.x + 19
        self._text("SESSION OVERVIEW", (x, panel.y + 21), self.font_heading, TEXT)
        badge = pygame.Rect(panel.right - 106, panel.y + 17, 87, 27)
        self._pill(badge, (20, 47, 45), (39, 78, 69))
        map_count = len(self.maps)
        self._text(f"{map_count} MAP{'S' if map_count != 1 else ''}", badge, self.font_small, GREEN, center=True)

        map_card = pygame.Rect(x, panel.y + 66, panel.w - 38, 109)
        pygame.draw.rect(self.screen, (17, 39, 52), map_card, border_radius=13)
        pygame.draw.rect(self.screen, (34, 71, 83), map_card, width=1, border_radius=13)
        icon = pygame.Rect(map_card.x + 13, map_card.y + 17, 48, 48)
        pygame.draw.rect(self.screen, (24, 66, 75), icon, border_radius=11)
        pygame.draw.line(self.screen, ACCENT, (icon.x + 11, icon.y + 36), (icon.x + 36, icon.y + 11), 4)
        pygame.draw.line(self.screen, (211, 240, 238), (icon.x + 19, icon.y + 38), (icon.x + 41, icon.y + 16), 2)
        self._text("SELECTED MAP", (map_card.x + 75, map_card.y + 19), self.font_small, MUTED)
        map_name = friendly_map_name(self.maps[self.selected["map"]])
        self._text(self._fit(map_name, self.font_value, map_card.w - 88), (map_card.x + 75, map_card.y + 43), self.font_value, TEXT)
        self._text("Changing maps reloads the CARLA world", (map_card.x + 15, map_card.y + 79), self.font_small, MUTED)

        weather_name = self.weather[self.selected["weather"]][1]
        vehicle_name = self.vehicles[self.selected["vehicle"]].label
        self._draw_summary_row(x, panel.y + 194, "WEATHER", weather_name)
        self._draw_summary_row(x, panel.y + 247, "EGO VEHICLE", vehicle_name)

        divider_y = panel.y + 307
        pygame.draw.line(self.screen, PANEL_EDGE, (x, divider_y), (panel.right - 19, divider_y), 1)
        stat_y = divider_y + 14
        stat_gap = 10
        stat_width = (panel.w - 38 - stat_gap) // 2
        self._draw_stat_card(pygame.Rect(x, stat_y, stat_width, 62), "TRAFFIC", self.traffic, "VEHICLES")
        self._draw_stat_card(
            pygame.Rect(x + stat_width + stat_gap, stat_y, stat_width, 62),
            "PEDESTRIANS",
            self.pedestrians,
            "PEOPLE",
        )

        input_y = panel.bottom - 46
        pygame.draw.circle(self.screen, ACCENT, (x + 5, input_y + 8), 3)
        self._text("Xbox controller or keyboard", (x + 16, input_y), self.font_small, MUTED)
        if self.status:
            self._text(self._fit(self.status, self.font_small, panel.w - 38), (x, panel.bottom - 25), self.font_small, ACCENT)

    def _draw_summary_row(self, x: int, y: int, label: str, value: str) -> None:
        self._text(label, (x, y), self.font_small, MUTED)
        self._text(self._fit(value, self.font_body, 280), (x, y + 20), self.font_body, TEXT)

    def _draw_stat_card(self, rect: pygame.Rect, label: str, value: int, unit: str) -> None:
        pygame.draw.rect(self.screen, ROW, rect, border_radius=10)
        self._text(label, (rect.x + 11, rect.y + 8), self.font_small, MUTED)
        self._text(str(value), (rect.x + 11, rect.y + 28), self.font_value, TEXT)
        value_width = self.font_value.size(str(value))[0]
        self._text(unit, (rect.x + 18 + value_width, rect.y + 36), self.font_small, MUTED)

    def _draw_footer(self, width: int, height: int) -> None:
        self.github_rect = pygame.Rect(32, height - 64, 224, 40)
        pygame.draw.rect(self.screen, (15, 34, 48), self.github_rect, border_radius=11)
        pygame.draw.rect(self.screen, PANEL_EDGE, self.github_rect, width=1, border_radius=11)
        self._draw_github_mark((self.github_rect.x + 20, self.github_rect.centery))
        self._text("GitHub  /  @ArvinNotDev", (self.github_rect.x + 39, self.github_rect.y + 12), self.font_small, TEXT)

        hint = "UP / DOWN  FOCUS     LEFT / RIGHT  ADJUST     SPACE  OPTIONS     ENTER  START"
        hint_rect = self.font_small.render(hint, True, FAINT).get_rect(center=(width // 2, self.github_rect.centery))
        self.screen.blit(self.font_small.render(hint, True, FAINT), hint_rect)

        self.start_rect = pygame.Rect(width - 242, height - 68, 210, 48)
        mouse = pygame.mouse.get_pos()
        color = (37, 190, 172) if self.start_rect.collidepoint(mouse) else (29, 160, 149)
        pygame.draw.rect(self.screen, color, self.start_rect, border_radius=12)
        self._text("START DRIVING", self.start_rect, self.font_button, (5, 27, 33), center=True)
        pygame.draw.polygon(
            self.screen,
            (5, 27, 33),
            [
                (self.start_rect.right - 24, self.start_rect.centery - 5),
                (self.start_rect.right - 18, self.start_rect.centery),
                (self.start_rect.right - 24, self.start_rect.centery + 5),
            ],
        )

    def _draw_dropdown(self, height: int) -> None:
        if self.open_dropdown is None:
            return
        field_index = ("map", "weather", "vehicle").index(self.open_dropdown)
        if field_index >= len(self.row_rects):
            return
        anchor = self.row_rects[field_index]
        options = self._options(self.open_dropdown)
        item_height = 38
        padding = 6
        available_height = height - 89 - (anchor.bottom + 7)
        visible_count = max(1, min(6, len(options), (available_height - padding * 2) // item_height))
        menu_height = visible_count * item_height + padding * 2
        menu_y = anchor.bottom + 7
        self.dropdown_rect = pygame.Rect(anchor.x, menu_y, anchor.w, menu_height)
        pygame.draw.rect(self.screen, (10, 23, 35), self.dropdown_rect, border_radius=12)
        pygame.draw.rect(self.screen, (53, 99, 111), self.dropdown_rect, width=1, border_radius=12)

        max_scroll = max(0, len(options) - visible_count)
        self.menu_scroll = max(0, min(max_scroll, self.menu_scroll))
        if self.menu_highlight < self.menu_scroll:
            self.menu_scroll = self.menu_highlight
        elif self.menu_highlight >= self.menu_scroll + visible_count:
            self.menu_scroll = self.menu_highlight - visible_count + 1

        self.dropdown_option_rects = []
        mouse = pygame.mouse.get_pos()
        for visible_index in range(visible_count):
            option_index = self.menu_scroll + visible_index
            rect = pygame.Rect(
                self.dropdown_rect.x + padding,
                self.dropdown_rect.y + padding + visible_index * item_height,
                self.dropdown_rect.w - padding * 2,
                item_height - 2,
            )
            self.dropdown_option_rects.append((option_index, rect))

        hovered_index = next(
            (option_index for option_index, rect in self.dropdown_option_rects if rect.collidepoint(mouse)),
            None,
        )
        if hovered_index is not None:
            self.menu_highlight = hovered_index

        for option_index, rect in self.dropdown_option_rects:
            option = options[option_index]
            if option_index == self.menu_highlight:
                pygame.draw.rect(self.screen, (27, 63, 73), rect, border_radius=8)
            elif option_index == self.selected[self.open_dropdown]:
                pygame.draw.rect(self.screen, (20, 43, 54), rect, border_radius=8)
            color = ACCENT if option_index == self.selected[self.open_dropdown] else TEXT
            self._text(self._fit(option, self.font_body, rect.w - 38), (rect.x + 12, rect.y + 10), self.font_body, color)
            if option_index == self.selected[self.open_dropdown]:
                pygame.draw.circle(self.screen, ACCENT, (rect.right - 14, rect.centery), 3)

    def _open_github(self) -> None:
        try:
            opened = webbrowser.open_new_tab(GITHUB_URL)
        except (OSError, webbrowser.Error):
            opened = False
        self.status = "GitHub opened in your browser." if opened else "Open github.com/ArvinNotDev in your browser."

    def _draw_counter_button(self, rect: pygame.Rect, label: str, hovered: bool) -> None:
        pygame.draw.rect(self.screen, (29, 58, 70) if hovered else (24, 46, 59), rect, border_radius=8)
        self._text(label, rect, self.font_body, ACCENT if hovered else TEXT, center=True)

    def _draw_chevron(self, center: tuple[int, int], color: tuple[int, int, int]) -> None:
        x, y = center
        pygame.draw.lines(self.screen, color, False, [(x - 4, y - 1), (x, y + 3), (x + 4, y - 1)], 2)

    def _draw_github_mark(self, center: tuple[int, int]) -> None:
        pygame.draw.circle(self.screen, TEXT, center, 8)
        pygame.draw.circle(self.screen, (15, 34, 48), (center[0], center[1] + 2), 5)
        pygame.draw.circle(self.screen, TEXT, (center[0] - 3, center[1] - 1), 1)
        pygame.draw.circle(self.screen, TEXT, (center[0] + 3, center[1] - 1), 1)

    def _pill(self, rect: pygame.Rect, fill: tuple[int, int, int], edge: tuple[int, int, int]) -> None:
        pygame.draw.rect(self.screen, fill, rect, border_radius=rect.h // 2)
        pygame.draw.rect(self.screen, edge, rect, width=1, border_radius=rect.h // 2)

    def _fit(self, value: str, font: pygame.font.Font, max_width: int) -> str:
        if max_width <= 0:
            return ""
        if font.size(value)[0] <= max_width:
            return value
        clipped = value
        while clipped and font.size(clipped + "…")[0] > max_width:
            clipped = clipped[:-1]
        return clipped + "…" if clipped else "…"

    def _text(
        self,
        value: str,
        position: tuple[int, int] | pygame.Rect,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        *,
        center: bool = False,
    ) -> None:
        rendered = font.render(value, True, color)
        if isinstance(position, pygame.Rect):
            target = rendered.get_rect(center=position.center) if center else position
            self.screen.blit(rendered, target)
        else:
            self.screen.blit(rendered, position)


_CONTINUE = object()
