# SPDX-License-Identifier: GPL-3.0-or-later

"""Bounce all floating windows around the screen like pong balls.

Run via IPC::

   ionwl-cmd python-file scripts/ionwl_pong.py

Runs for 5 seconds then restores original positions.
Press Escape to stop early.
"""

from __future__ import annotations

__all__ = (
    "main",
)

from collections.abc import Generator

import ion  # pylint: disable=import-error
import ion.constants.keys as kbd  # pylint: disable=import-error
from ion.types import (  # pylint: disable=import-error
    DesktopItemFloatingFrame, Event, EventKey, EventTimer, GeneratorStep, Rect,
)

_DURATION_MS = 5000
_STEP_MS = 16  # ~60 fps.
_SPEED = 10  # Pixels per step.


class _Ball:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """Tracks a floating frame's position and velocity."""

    __slots__ = ("item", "x", "y", "w", "h", "dx", "dy", "orig_x", "orig_y")

    def __init__(self, item: DesktopItemFloatingFrame, rect: Rect) -> None:
        self.item = item
        self.x, self.y = rect.min
        self.w = rect.size_x
        self.h = rect.size_y
        self.dx = _SPEED
        self.dy = _SPEED
        self.orig_x, self.orig_y = rect.min


def _pong() -> Generator[GeneratorStep, Event, None]:
    desktop = ion.wm.desktops.active

    # Compute bounding box of all outputs.
    bounds = ion.wm.outputs.bounds_calc()
    if bounds is None:
        return
    ox, oy = bounds.min
    ow, oh = bounds.size_x, bounds.size_y

    # Collect floating frames with their initial state and velocity.
    balls: list[_Ball] = []
    for item in desktop.items_floating:
        if not isinstance(item, DesktopItemFloatingFrame):
            continue
        balls.append(_Ball(item, item.rect))

    if not balls:
        ion.utils.log("No floating windows to bounce.")
        return

    ion.utils.log("Pong: bouncing {:d} windows for {:d}ms.".format(len(balls), _DURATION_MS))

    elapsed = 0
    while elapsed < _DURATION_MS:
        event = yield GeneratorStep(time=_STEP_MS, consume_event=True)

        # Only advance animation on timer ticks.
        if not isinstance(event, EventTimer):
            # Exit early on Escape.
            if isinstance(event, EventKey) and event.press and event.key == kbd.ESCAPE:
                break
            continue

        for b in balls:
            b.x += b.dx
            b.y += b.dy

            # Bounce off edges.
            if b.x <= ox:
                b.x = ox
                b.dx = abs(b.dx)
            elif b.x + b.w >= ox + ow:
                b.x = ox + ow - b.w
                b.dx = -abs(b.dx)

            if b.y <= oy:
                b.y = oy
                b.dy = abs(b.dy)
            elif b.y + b.h >= oy + oh:
                b.y = oy + oh - b.h
                b.dy = -abs(b.dy)

            b.item.rect = Rect(
                (b.x, b.y),
                (b.x + b.w, b.y + b.h),
            )

        elapsed += _STEP_MS

    # Restore original positions.
    for b in balls:
        b.item.rect = Rect(
            (b.orig_x, b.orig_y),
            (b.orig_x + b.w, b.orig_y + b.h),
        )

    ion.utils.log("Pong: done.")


def main() -> None:
    """Entry point for the pong animation."""
    ion.utils.exec_generator(_pong())


if __name__ == "__main__":
    main()
