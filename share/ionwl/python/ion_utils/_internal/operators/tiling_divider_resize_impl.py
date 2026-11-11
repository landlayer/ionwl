# SPDX-License-Identifier: GPL-3.0-or-later

"""
Divider resize generator implementation.

Handles interactive resizing of a tiling split divider via pointer
drag. Holding Ctrl during the drag snaps the ratio to the nearest
of 1/4, 1/3, 1/2, 2/3, 3/4.
"""

from __future__ import annotations

__all__ = (
    "exec_generator",
)

from collections.abc import Generator

import ion
from ion.constants.modifiers import CTRL
from ion.types import (
    Event,
    EventCancel,
    EventKey,
    EventMotion,
    EventPointer,
    GeneratorStep,
)

_SNAP_RATIOS = (0.25, 1.0 / 3.0, 0.5, 2.0 / 3.0, 0.75)


def exec_generator(
    event: Event,
) -> Generator[GeneratorStep, Event]:
    """
    Resize the split divider under the pointer.

    The generator consumes all input events until the initiating
    pointer button is released.
    """
    result = ion._internal.divider_at_pointer()
    if result is None:
        return None
    split_node, axis, cursor_offset = result

    # The button that initiated the drag (currently held).
    assert isinstance(event, EventPointer)
    grab_button = event.button

    divider_pos = None
    cursor_token = ion.wm.cursor_push("col-resize" if axis == 0 else "row-resize")
    try:
        while True:
            event = yield GeneratorStep(consume_event=True)

            if isinstance(event, EventCancel):
                return

            # The split can go under the drag, a frame removed by IPC or a hook
            # collapsing it. Nothing left to resize, and a write to it would raise.
            if not split_node.is_valid:
                return

            if isinstance(event, EventPointer) and not event.press and event.button == grab_button:
                # Button released, resize complete.
                return

            if isinstance(event, (EventMotion, EventPointer, EventKey)):
                # Track the unsnapped divider position from pointer events.
                if isinstance(event, (EventMotion, EventPointer)):
                    if axis == 0:
                        divider_pos = event.position.x - cursor_offset
                    else:
                        divider_pos = event.position.y - cursor_offset

                if divider_pos is not None:
                    if event.modifiers & CTRL:
                        # Snap to the closest candidate ratio and apply only that.
                        # Setting the raw position first would reconfigure the
                        # windows for the unsnapped size before snapping. The set
                        # is a no-op when the snapped ratio is unchanged, so the
                        # windows hold steady as the cursor moves within a zone.
                        ratio = split_node.split_divider_position_to_ratio(divider_pos)
                        if ratio is not None:
                            best = min(_SNAP_RATIOS, key=lambda r: abs(r - ratio))
                            split_node.split_ratio = best
                    else:
                        split_node.split_divider_position_set(divider_pos)
    finally:
        ion.wm.cursor_pop(cursor_token)
