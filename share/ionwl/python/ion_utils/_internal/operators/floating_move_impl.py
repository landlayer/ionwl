# SPDX-License-Identifier: GPL-3.0-or-later

"""Floating move generator implementation.

Handles interactive moving of a floating item (window frame or
workspace) by dragging with the pointer.

Resting the pointer against a screen edge switches desktop in that
direction, and the item comes along: once the slide lands it is on the
new desktop, under the pointer, still held.
"""

from __future__ import annotations

__all__ = (
    "exec_generator",
)

from collections.abc import Generator

import ion
from ion.types import (
    Event,
    EventCancel,
    EventMotion,
    EventPointer,
    EventTimer,
    GeneratorStep,
    Rect,
)

from ion_utils._internal.operators import DragEdgeSwitch


def exec_generator(
    event: Event,
) -> Generator[GeneratorStep, Event]:
    """Move the floating item under the pointer.

    The generator consumes all input events until the initiating
    pointer button is released.
    """
    item = ion._internal.floating_item_at_pointer()
    if item is None:
        return None

    assert isinstance(event, EventPointer)
    grab_button = event.button

    ion._internal.floating_focus_raise(item)

    initial_pos = event.position
    # A copy, as the drag assigns the property this would be a live view of.
    initial_rect = item.rect.copy()

    # Nothing arms yet: the initial event is the press, on the item, and
    # nothing has moved.
    edge = DragEdgeSwitch()
    position = initial_pos

    cursor_token = ion.wm.cursor_push("grabbing")
    try:
        while True:
            event = yield edge.step()

            if isinstance(event, EventCancel):
                return

            # The item can go under the drag, its last window closing. Nothing
            # left to move, and a write to it would raise.
            if not item.is_valid:
                return

            if edge.landed():
                # The slide drew the item where it is; the item itself is still
                # on the desktop the switch left, so carry it over. It followed
                # every motion, so its rect already puts it under the pointer.
                # The switch focused a frame of the new desktop and the move
                # appends the item topmost; the frame the user is holding is the
                # one that should have focus.
                # Armed from the last motion rather than the pointer: a touch drag
                # leaves the pointer behind.
                item = item.move_to_desktop(ion.wm.desktops.active)
                ion._internal.floating_focus_raise(item)
                edge.arm(position)
                if isinstance(event, EventTimer):
                    continue

            if isinstance(event, EventPointer) and not event.press and event.button == grab_button:
                # Button released, move complete. During a switch the slide
                # runs to its end and the item stays on the desktop it left.
                return

            if isinstance(event, EventMotion):
                position = event.position
                delta = position - initial_pos
                new_min = initial_rect.min + delta
                new_max = initial_rect.max + delta
                item.rect = Rect(new_min, new_max)
                edge.arm(position)

            if isinstance(event, EventTimer):
                edge.fire(held=item)
    finally:
        ion.wm.cursor_pop(cursor_token)
