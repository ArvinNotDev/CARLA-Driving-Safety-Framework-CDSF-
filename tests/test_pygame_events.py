import pygame

import carla_drive.ui.events as events


def test_event_polling_clears_bad_sdl_batch_and_recovers(monkeypatch):
    calls = 0
    cleared = []
    monkeypatch.setattr(events, "_RECOVERY_LOGGED", False)

    def get_events():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SystemError("built-in function get returned a result with an exception set") from KeyError(0)
        return ["next event"]

    monkeypatch.setattr(pygame.event, "get", get_events)
    monkeypatch.setattr(pygame.event, "clear", lambda **kwargs: cleared.append(kwargs))

    assert events.get_events() == []
    assert cleared == [{"pump": False}]
    assert events.get_events() == ["next event"]
    assert events._RECOVERY_LOGGED is False
