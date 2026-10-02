"""Interactive controller tuning and button-mapping screen."""

from __future__ import annotations

from dataclasses import fields, replace

import pygame

from carla_drive.config import ControllerConfig
from carla_drive.input.preferences import save_controller_preferences


SLIDERS = (
    ("steering_sensitivity", "Steering sensitivity", 0.5, 2.0, 0.05),
    ("steering_deadzone", "Steering deadzone", 0.0, 0.30, 0.01),
    ("steering_response", "Steering response curve", 0.5, 2.0, 0.05),
    ("steering_smoothing", "Steering smoothing", 0.0, 0.50, 0.01),
    ("trigger_deadzone", "Trigger deadzone", 0.0, 0.25, 0.01),
    ("throttle_response", "Throttle response", 0.5, 2.0, 0.05),
    ("brake_response", "Brake response", 0.5, 2.0, 0.05),
)

BUTTON_PAGES = {
    "axes": (
        ("joystick_index", "Controller device index"),
        ("steering_axis", "Steering axis"),
        ("throttle_axis", "Throttle axis"),
        ("brake_axis", "Brake axis"),
        ("trigger_rest_value", "Trigger rest calibration"),
        ("trigger_full_value", "Trigger full calibration"),
    ),
    "dpad": (
        ("dpad_mode", "D-pad input mode"),
        ("dpad_hat", "D-pad hat index"),
        ("dpad_left_button", "D-pad left"),
        ("dpad_right_button", "D-pad right"),
        ("dpad_up_button", "D-pad up"),
        ("dpad_down_button", "D-pad down"),
    ),
    "buttons": (
        ("settings_button", "Options / open settings"),
        ("pause_button", "Pause"),
        ("reverse_button", "Toggle reverse"),
        ("camera_next_button", "Next camera"),
        ("camera_previous_button", "Previous camera"),
        ("handbrake_button", "Handbrake"),
        ("reset_button", "Reset vehicle"),
    ),
}
BUTTON_FIELDS = {
    "settings_button",
    "pause_button",
    "reverse_button",
    "camera_next_button",
    "camera_previous_button",
    "handbrake_button",
    "reset_button",
    "dpad_left_button",
    "dpad_right_button",
    "dpad_up_button",
    "dpad_down_button",
}

BACKGROUND = (5, 12, 20)
CARD = (13, 27, 41)
ROW = (18, 39, 53)
EDGE = (41, 70, 86)
TEXT = (237, 245, 248)
MUTED = (136, 160, 173)
ACCENT = (77, 208, 190)


class ControllerSettings:
    PAGES = ("drive", "axes", "dpad", "buttons")

    def __init__(
        self,
        screen: pygame.Surface,
        defaults: ControllerConfig,
        preference_path=None,
        controller_name: str = "",
    ):
        self.screen = screen
        self.defaults = defaults
        self.values = {setting.name: getattr(defaults, setting.name) for setting in fields(ControllerConfig)}
        self.preference_path = preference_path
        self.controller_name = controller_name
        self.clock = pygame.time.Clock()
        self.title_font = pygame.font.SysFont("Segoe UI", 29, bold=True)
        self.body_font = pygame.font.SysFont("Segoe UI", 17)
        self.small_font = pygame.font.SysFont("Segoe UI", 14)
        self.button_font = pygame.font.SysFont("Segoe UI", 16, bold=True)
        self.page = "drive"
        self.focus = 0
        self.dragging: str | None = None
        self.capture_target: str | None = None
        self.status = ""
        self.quit_requested = False
        self.tabs: dict[str, pygame.Rect] = {}
        self.slider_rows: dict[str, tuple[pygame.Rect, pygame.Rect]] = {}
        self.control_rows: dict[str, tuple[pygame.Rect, pygame.Rect]] = {}
        self.save_rect = pygame.Rect(0, 0, 0, 0)
        self.cancel_rect = pygame.Rect(0, 0, 0, 0)
        self.reset_rect = pygame.Rect(0, 0, 0, 0)

    def run(self) -> ControllerConfig | None:
        pygame.display.set_caption("CARLA Drive | Controller Settings")
        while True:
            self.clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit_requested = True
                    return None
                if event.type == pygame.KEYDOWN:
                    result = self._handle_key(event.key)
                    if result is not _CONTINUE:
                        return result
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    result = self._handle_click(event.pos)
                    if result is not _CONTINUE:
                        return result
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self.dragging = None
                elif event.type == pygame.MOUSEMOTION and self.dragging:
                    self._set_slider_from_mouse(self.dragging, event.pos[0])
                elif self.capture_target:
                    self._capture_event(event)
            self._draw()
            pygame.display.flip()

    def _handle_key(self, key: int):
        if self.capture_target:
            if key == pygame.K_ESCAPE:
                self.capture_target = None
                self.status = "Button capture cancelled"
            return _CONTINUE
        if key == pygame.K_ESCAPE:
            return None
        if key == pygame.K_TAB:
            self.page = self.PAGES[(self.PAGES.index(self.page) + 1) % len(self.PAGES)]
            self.focus = 0
        elif key in (pygame.K_UP, pygame.K_w):
            self.focus = (self.focus - 1) % self._focus_count()
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.focus = (self.focus + 1) % self._focus_count()
        elif key in (pygame.K_LEFT, pygame.K_a):
            self._adjust_focus(-1)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self._adjust_focus(1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            return self._activate_focus()
        return _CONTINUE

    def _handle_click(self, position: tuple[int, int]):
        for page, rect in self.tabs.items():
            if rect.collidepoint(position):
                self.page = page
                self.focus = 0
                return _CONTINUE
        if self.cancel_rect.collidepoint(position):
            return None
        if self.reset_rect.collidepoint(position):
            self.values = {setting.name: getattr(self.defaults, setting.name) for setting in fields(ControllerConfig)}
            self.status = "Changes reverted to the values at screen entry"
            return _CONTINUE
        if self.save_rect.collidepoint(position):
            return self._save()
        if self.page == "drive":
            for index, (field, _, _, _, _) in enumerate(SLIDERS):
                row, rail = self.slider_rows[field]
                if row.collidepoint(position):
                    self.focus = index
                    if rail.collidepoint(position):
                        self.dragging = field
                        self._set_slider_from_mouse(field, position[0])
                    return _CONTINUE
            invert_row = self._invert_row()
            if invert_row.collidepoint(position):
                self.focus = len(SLIDERS)
                self.values["steering_axis_inverted"] = not self.values["steering_axis_inverted"]
                return _CONTINUE
        else:
            for index, (field, (row, button)) in enumerate(self.control_rows.items()):
                if row.collidepoint(position):
                    self.focus = index
                    if button.collidepoint(position):
                        self._activate_mapping(field)
                    else:
                        self._adjust_mapping(field, 1)
                    return _CONTINUE
        return _CONTINUE

    def _focus_count(self) -> int:
        if self.page == "drive":
            return len(SLIDERS) + 1
        return len(BUTTON_PAGES[self.page])

    def _adjust_focus(self, direction: int) -> None:
        if self.page == "drive":
            if self.focus == len(SLIDERS):
                return
            field, _, minimum, maximum, step = SLIDERS[self.focus]
            value = float(self.values[field]) + direction * step
            self.values[field] = round(max(minimum, min(maximum, value)), 3)
            return
        field = BUTTON_PAGES[self.page][self.focus][0]
        self._adjust_mapping(field, direction)

    def _activate_focus(self):
        if self.page == "drive":
            if self.focus == len(SLIDERS):
                self.values["steering_axis_inverted"] = not self.values["steering_axis_inverted"]
            return _CONTINUE
        field = BUTTON_PAGES[self.page][self.focus][0]
        if field == "dpad_mode":
            modes = ("auto", "hat", "buttons")
            self.values[field] = modes[(modes.index(self.values[field]) + 1) % len(modes)]
        else:
            self._activate_mapping(field)
        return _CONTINUE

    def _adjust_mapping(self, field: str, direction: int) -> None:
        if field == "dpad_mode":
            modes = ("auto", "hat", "buttons")
            self.values[field] = modes[(modes.index(self.values[field]) + direction) % len(modes)]
        elif field == "settings_button":
            self.values[field] = max(-1, int(self.values[field]) + direction)
        elif field.endswith("_button") or field in {"dpad_hat", "joystick_index", "steering_axis", "throttle_axis", "brake_axis"}:
            self.values[field] = max(0, int(self.values[field]) + direction)
        elif field in {"trigger_rest_value", "trigger_full_value", "joystick_index"}:
            self.values[field] = round(max(-1.0, min(1.0, float(self.values[field]) + direction * 0.05)), 2)

    def _activate_mapping(self, field: str) -> None:
        if field == "dpad_mode":
            self._adjust_mapping(field, 1)
        elif field in {"trigger_rest_value", "trigger_full_value"}:
            self._adjust_mapping(field, 1)
        else:
            self.capture_target = field
            self.status = f"Press the physical control for {self._mapping_label(field)}"

    def _capture_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.JOYBUTTONDOWN and self.capture_target in BUTTON_FIELDS:
            field = self.capture_target
            self.values[field] = int(event.button)
            if field.startswith("dpad_") and field.endswith("_button"):
                self.values["dpad_mode"] = "buttons"
            self.status = f"{self._mapping_label(field)} bound to button {event.button}"
            self.capture_target = None
        elif event.type == pygame.JOYAXISMOTION and self.capture_target in {"steering_axis", "throttle_axis", "brake_axis"} and abs(event.value) >= 0.2:
            field = self.capture_target
            self.values[field] = int(event.axis)
            self.status = f"{self._mapping_label(field)} bound to axis {event.axis}"
            self.capture_target = None
        elif event.type == pygame.JOYHATMOTION and self.capture_target == "dpad_hat":
            self.values["dpad_hat"] = int(event.hat)
            self.values["dpad_mode"] = "hat"
            self.status = f"D-pad hat {event.hat} detected"
            self.capture_target = None
        elif event.type == pygame.JOYHATMOTION and self.capture_target.startswith("dpad_"):
            direction = self.capture_target.removeprefix("dpad_").removesuffix("_button")
            expected = {"left": (-1, 0), "right": (1, 0), "up": (0, 1), "down": (0, -1)}.get(direction)
            value = event.value
            if expected is not None and (value == expected or (expected[0] and value[0] == expected[0]) or (expected[1] and value[1] == expected[1])):
                self.values["dpad_hat"] = int(event.hat)
                self.values["dpad_mode"] = "hat"
                self.status = f"D-pad hat {event.hat} detected"
                self.capture_target = None

    def _save(self) -> ControllerConfig | None:
        settings = replace(self.defaults, **self.values)
        try:
            save_controller_preferences(settings, self.preference_path)
        except (OSError, TypeError, ValueError) as exc:
            self.status = f"Could not save settings: {exc}"
            return _CONTINUE
        return settings

    def _set_slider_from_mouse(self, field: str, mouse_x: int) -> None:
        _, minimum, maximum, _ = next((name, low, high, step) for name, _, low, high, step in SLIDERS if name == field)
        _, rail = self.slider_rows[field]
        ratio = max(0.0, min(1.0, (mouse_x - rail.x) / max(1, rail.w)))
        value = minimum + ratio * (maximum - minimum)
        step = next(item[4] for item in SLIDERS if item[0] == field)
        self.values[field] = round(round(value / step) * step, 3)

    def _draw(self) -> None:
        width, height = self.screen.get_size()
        self.screen.fill(BACKGROUND)
        card = pygame.Rect((width - 960) // 2, 24, 960, height - 48)
        pygame.draw.rect(self.screen, CARD, card, border_radius=20)
        pygame.draw.rect(self.screen, EDGE, card, width=1, border_radius=20)
        self._text("CONTROLLER SETTINGS", (card.x + 32, card.y + 24), self.title_font, TEXT)
        detail = self.controller_name or "Tune the connected gamepad or keyboard fallback"
        self._text(detail, (card.x + 34, card.y + 63), self.small_font, MUTED)
        self._draw_tabs(card)
        self.slider_rows = {}
        self.control_rows = {}
        if self.page == "drive":
            self._draw_sliders(card)
        else:
            self._draw_mappings(card)
        if self.status:
            self._text(self.status, (card.x + 32, card.bottom - 55), self.small_font, ACCENT)
        self.cancel_rect = pygame.Rect(card.right - 360, card.bottom - 61, 110, 38)
        self.reset_rect = pygame.Rect(card.right - 240, card.bottom - 61, 132, 38)
        self.save_rect = pygame.Rect(card.right - 98, card.bottom - 61, 84, 38)
        self._button(self.cancel_rect, "CANCEL", (29, 49, 62))
        self._button(self.reset_rect, "REVERT", (29, 49, 62))
        self._button(self.save_rect, "SAVE", (24, 112, 105))

    def _draw_tabs(self, card: pygame.Rect) -> None:
        self.tabs = {}
        labels = {"drive": "Driving", "axes": "Axes", "dpad": "D-pad", "buttons": "Buttons"}
        for index, page in enumerate(self.PAGES):
            rect = pygame.Rect(card.x + 32 + index * 164, card.y + 98, 150, 38)
            self.tabs[page] = rect
            fill = (27, 63, 73) if self.page == page else (19, 39, 53)
            pygame.draw.rect(self.screen, fill, rect, border_radius=9)
            self._text(labels[page], rect, self.button_font, ACCENT if self.page == page else TEXT, center=True)

    def _draw_sliders(self, card: pygame.Rect) -> None:
        for index, (field, label, minimum, maximum, _) in enumerate(SLIDERS):
            row = pygame.Rect(card.x + 32, card.y + 153 + index * 53, card.w - 64, 47)
            rail = pygame.Rect(card.right - 371, row.y + 24, 265, 7)
            self.slider_rows[field] = row, rail
            pygame.draw.rect(self.screen, ROW, row, border_radius=9)
            if self.focus == index:
                pygame.draw.rect(self.screen, ACCENT, row, width=1, border_radius=9)
            self._text(label, (row.x + 16, row.y + 14), self.body_font, TEXT)
            value = float(self.values[field])
            self._text(f"{value:.2f}", (rail.right + 18, row.y + 14), self.body_font, ACCENT)
            pygame.draw.rect(self.screen, (41, 62, 75), rail, border_radius=4)
            ratio = (value - minimum) / (maximum - minimum)
            fill = pygame.Rect(rail.x, rail.y, max(5, int(rail.w * ratio)), rail.h)
            pygame.draw.rect(self.screen, ACCENT, fill, border_radius=4)
            pygame.draw.circle(self.screen, TEXT, (fill.right, rail.centery), 7)

        invert = self._invert_row()
        pygame.draw.rect(self.screen, ROW, invert, border_radius=9)
        if self.focus == len(SLIDERS):
            pygame.draw.rect(self.screen, ACCENT, invert, width=1, border_radius=9)
        self._text("Invert steering axis", (invert.x + 16, invert.y + 14), self.body_font, TEXT)
        self._text("ON" if self.values["steering_axis_inverted"] else "OFF", (invert.right - 72, invert.y + 14), self.button_font, ACCENT)
        self._text("Lower response curve = quicker near center; deadzone filters stick drift.", (card.x + 34, invert.bottom + 12), self.small_font, MUTED)

    def _draw_mappings(self, card: pygame.Rect) -> None:
        items = BUTTON_PAGES[self.page]
        for index, (field, label) in enumerate(items):
            row = pygame.Rect(card.x + 32, card.y + 153 + index * 61, card.w - 64, 54)
            action = pygame.Rect(row.right - 149, row.y + 8, 132, 38)
            self.control_rows[field] = row, action
            pygame.draw.rect(self.screen, ROW, row, border_radius=9)
            if self.focus == index:
                pygame.draw.rect(self.screen, ACCENT, row, width=1, border_radius=9)
            self._text(label, (row.x + 16, row.y + 17), self.body_font, TEXT)
            value = self._mapping_value(field)
            self._text(value, (row.right - 267, row.y + 18), self.small_font, MUTED)
            button_label = "CHANGE" if field == "dpad_mode" else "ADJUST" if field.startswith("trigger_") or field == "joystick_index" else "BIND"
            self._button(action, button_label, (28, 54, 68))
        if self.capture_target:
            instruction = "Move the requested axis past 20%; Esc cancels." if self.capture_target.endswith("_axis") else "Press the requested button or D-pad direction; Esc cancels."
            self._text(instruction, (card.x + 34, card.bottom - 82), self.small_font, ACCENT)
        elif self.page == "axes":
            self._text("Bind axes by moving them; use Left / Right to adjust device index and trigger calibration.", (card.x + 34, card.bottom - 82), self.small_font, MUTED)
        elif self.page == "dpad":
            self._text("Auto uses SDL gamepad mapping, then hats; Buttons mode supports raw-button devices.", (card.x + 34, card.bottom - 82), self.small_font, MUTED)

    def _mapping_value(self, field: str) -> str:
        value = self.values[field]
        if field == "dpad_mode":
            return {"auto": "Auto", "hat": "Hat", "buttons": "Buttons"}[value]
        if field == "settings_button" and value == -1:
            return "Auto (Options)"
        if field in {"trigger_rest_value", "trigger_full_value"}:
            return f"{value:.2f}"
        if field.endswith("_axis"):
            return f"Axis {value}"
        if field == "joystick_index":
            return f"Device {value}"
        if field == "dpad_hat":
            return f"Hat {value}"
        return f"Index {value}"

    def _mapping_label(self, field: str) -> str:
        for page in BUTTON_PAGES.values():
            for name, label in page:
                if name == field:
                    return label
        return field

    def _invert_row(self) -> pygame.Rect:
        card = pygame.Rect((self.screen.get_width() - 960) // 2, 24, 960, self.screen.get_height() - 48)
        return pygame.Rect(card.x + 32, card.y + 153 + len(SLIDERS) * 53, card.w - 64, 43)

    def _button(self, rect: pygame.Rect, label: str, color: tuple[int, int, int]) -> None:
        pygame.draw.rect(self.screen, color, rect, border_radius=9)
        pygame.draw.rect(self.screen, EDGE, rect, width=1, border_radius=9)
        self._text(label, rect, self.small_font, TEXT, center=True)

    def _text(self, value: str, position, font: pygame.font.Font, color, *, center: bool = False) -> None:
        surface = font.render(value, True, color)
        rect = surface.get_rect(center=position.center) if center else surface.get_rect(topleft=position)
        self.screen.blit(surface, rect)


_CONTINUE = object()
