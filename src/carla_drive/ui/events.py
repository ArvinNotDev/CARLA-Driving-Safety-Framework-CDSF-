"""Recover from SDL events that Pygame cannot decode on some gamepads."""

from __future__ import annotations

import logging

import pygame

LOG = logging.getLogger(__name__)
_RECOVERY_LOGGED = False


def get_events() -> list[pygame.event.Event]:
    """Return queued events, discarding a malformed SDL batch if Pygame fails."""
    global _RECOVERY_LOGGED

    try:
        events = pygame.event.get()
    except (KeyError, SystemError) as exc:
        if not _RECOVERY_LOGGED:
            cause = exc.__context__ or exc.__cause__
            detail = f"{type(cause).__name__}: {cause}" if cause else str(exc)
            LOG.warning("Discarding an unreadable SDL event batch and continuing: %s", detail)
            _RECOVERY_LOGGED = True
        try:
            pygame.event.clear(pump=False)
        except pygame.error:
            LOG.exception("Could not clear Pygame's event queue after a decoding error")
        return []

    if _RECOVERY_LOGGED:
        LOG.info("Pygame's SDL event queue recovered")
        _RECOVERY_LOGGED = False
    return events
