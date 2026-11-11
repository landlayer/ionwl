# SPDX-License-Identifier: GPL-3.0-or-later

"""Tab drag generator implementation.

Handles interactive dragging of a tab from one frame to another,
with ghost tab overlay rendering. On release, the tab is either
moved to the target frame, reordered within the same frame,
or floated to empty space.

Resting the pointer against a screen edge switches desktop in that
direction, so the tab can be dropped into a frame that lives there.
"""

from __future__ import annotations

__all__ = (
    "exec_generator",
)

from collections.abc import Generator

import ion
from ion.types import (
    ColorRGBA,
    Event,
    EventCancel,
    EventMotion,
    EventPointer,
    EventTimer,
    GeneratorStep,
    OverlayRect,
    OverlayTab,
    Point,
    Rect,
)

from ion_utils._internal.operators import DragEdgeSwitch, OverlayScope

# White at half opacity, shared by the drag highlights.
_HIGHLIGHT_COLOR = ColorRGBA((1.0, 1.0, 1.0, 0.5))
# Inset border width for the drag highlights, in logical pixels.
_HIGHLIGHT_MARGIN_PX = 4
# Nothing to highlight.
_EMPTY_RECT = Rect((0, 0), (0, 0))


def exec_generator(
    event: Event,
) -> Generator[GeneratorStep, Event]:
    """Drag a tab between frames.

    The generator consumes all input events until the initiating
    pointer button is released, then resolves the drop target.
    """
    result = ion._internal.tab_at_pointer()
    if result is None:
        return None

    window, source_frame, tab_rect, grab_offset = result

    assert isinstance(event, EventPointer)
    grab_button = event.button

    with OverlayScope() as scope:
        # Create ghost tab overlay. The position is the tab's top-left (the
        # pointer less where in the tab it was grabbed), so anchor it there
        # rather than at the default center.
        ghost = OverlayTab(window, source_frame)
        ghost.tab_size = tab_rect.size
        ghost.align = (-1, -1)
        ghost_pos = event.position - grab_offset
        ghost.position = ghost_pos
        scope.append(ghost)

        # Drop-target highlights: a 4px inner border on the frame the tab would
        # drop into, plus one on the slot the tab would occupy within it.
        # Appended after the ghost so they render below it (earlier overlays
        # render in front).
        frame_highlight = OverlayRect()
        frame_highlight.outline_color = _HIGHLIGHT_COLOR
        frame_highlight.outline_width = -_HIGHLIGHT_MARGIN_PX
        scope.append(frame_highlight)

        tab_highlight = OverlayRect()
        tab_highlight.outline_color = _HIGHLIGHT_COLOR
        tab_highlight.outline_width = -_HIGHLIGHT_MARGIN_PX
        scope.append(tab_highlight)

        _highlight_update(frame_highlight, tab_highlight, ghost_pos, tab_rect, window)

        # Nothing arms yet: the initial event is the press, on a tab, and
        # nothing has moved.
        edge = DragEdgeSwitch()
        position = event.position

        def hover_track(position: Point) -> None:
            # The highlights for the ghost held at *position*, and the hover
            # armed from there: over a tab bar, only pressed against the edge.
            over_tab_bar = _highlight_update(
                frame_highlight, tab_highlight, position - grab_offset, tab_rect, window,
            )
            edge.arm(position, pressed_only=over_tab_bar)

        cursor_token = ion.wm.cursor_push("grabbing")
        try:
            while True:
                event = yield edge.step()

                if isinstance(event, EventCancel):
                    return

                # The window can leave its frame under the drag, by closing or being
                # moved, and the frame can go with it; the drop would then resolve
                # against a frame the window has left.
                if not (source_frame.is_valid and window in source_frame.windows):
                    return

                if edge.landed():
                    # The highlights now resolve on the new desktop, armed from
                    # the last motion rather than the pointer: a touch drag leaves
                    # the pointer behind. Any event other than a tick that noticed
                    # the landing is handled below as usual.
                    hover_track(position)
                    if isinstance(event, EventTimer):
                        continue

                if isinstance(event, EventPointer) and not event.press and event.button == grab_button:
                    # Released during a switch: the slide runs to its end and
                    # the tab stays where it was.
                    if not edge.in_transit:
                        _drop_resolve(
                            event.position, window, source_frame,
                            grab_offset, tab_rect,
                        )
                    return

                if isinstance(event, EventMotion):
                    position = event.position
                    ghost.position = position - grab_offset
                    if not edge.in_transit:
                        hover_track(position)

                if isinstance(event, EventTimer) and edge.fire():
                    # A frame outline from the desktop being left would draw over
                    # the slide.
                    frame_highlight.rect = _EMPTY_RECT
                    tab_highlight.rect = _EMPTY_RECT
        finally:
            ion.wm.cursor_pop(cursor_token)


def _highlight_update(
    frame_highlight: ion.types.OverlayRect,
    tab_highlight: ion.types.OverlayRect,
    ghost: ion.types.Point,
    tab_rect: ion.types.Rect,
    window: ion.types.Window,
) -> bool:
    """Update the drop-target highlights for the frame under the ghost.

    Marks the target frame's window area - its region excluding the tab bar -
    and over a tab bar also the slot the tab would occupy once dropped, with the
    siblings resized to make room. Each collapses to an empty rect where there
    is nothing to mark (no frame, or no tab bar under the ghost).

    Returns whether the ghost is over a tab bar, which narrows the edge hover
    to a cursor pressed against the screen edge.
    """
    target_frame, drop_index = ion._internal.tab_drop_resolve(
        Rect(ghost, ghost + tab_rect.size),
    )

    content_rect = target_frame.content_rect if target_frame is not None else None
    frame_highlight.rect = content_rect if content_rect is not None else _EMPTY_RECT

    slot = None
    if target_frame is not None and drop_index is not None:
        slot = ion._internal.tab_drop_slot(target_frame, drop_index, window)
    tab_highlight.rect = slot if slot is not None else _EMPTY_RECT
    return drop_index is not None


def _drop_resolve(
    pos: ion.types.Point,
    window: ion.types.Window,
    source_frame: ion.types.Frame,
    grab_offset: ion.types.Point,
    tab_rect: ion.types.Rect,
) -> None:
    """Resolve the tab drop after button release."""

    # Compute ghost position from current pointer position.
    ghost = pos - grab_offset

    target_frame, drop_index = ion._internal.tab_drop_resolve(
        Rect(ghost, ghost + tab_rect.size),
    )

    if target_frame is not None:
        if target_frame != source_frame:
            # Cross-frame move. Only activate the dropped tab if it
            # was active in the source frame.
            source_windows = source_frame.windows
            active_idx = source_frame.active_index
            was_active = (
                active_idx < len(source_windows)
                and source_windows[active_idx] == window
            )
            if drop_index is None:
                # Dropped on frame body: insert after the active tab.
                drop_index = target_frame.active_index + 1
            window.move_to_frame(target_frame, drop_index, was_active)
        elif drop_index is not None:
            # Same-frame reorder (only when ghost overlaps tab bar).
            source_frame.window_reorder(window, drop_index)
    else:
        # Dropped into empty space: float the window.
        _drop_to_float(window, source_frame, ghost)


def _drop_to_float(
    window: ion.types.Window,
    source_frame: ion.types.Frame,
    ghost: ion.types.Point,
) -> None:
    """Float a window at the ghost position.

    Single-tab floating sources reposition the existing frame
    instead of creating a new one.
    """
    # Single-tab floating optimization: reposition existing frame. A frame
    # on the desktop a switch left behind moves with its window.
    if source_frame.is_floating:
        windows = list(source_frame.windows)
        if len(windows) <= 1:
            desktop = ion.wm.desktops.find_by_window(window)
            item = desktop.items_floating.find_by_frame(source_frame) if desktop is not None else None
            if item is not None:
                moved = item.move_to_desktop(ion.wm.desktops.active)
                moved.rect = Rect(ghost, ghost + moved.rect.size)
                return

    # Multi-tab floating source: detach window into a new floating frame. The
    # new frame lands on the source frame's desktop, which a switch has left
    # behind, so carry it over; the move keeps the rect the detach gave it.
    if source_frame.is_floating:
        win_rect = window.frame_rect
        size = win_rect.size if win_rect is not None else (640, 480)
        item = ion._internal.window_detach_to_floating(
            window, source_frame, Rect(ghost, ghost + size),
        )
        if item is not None:
            item.move_to_desktop(ion.wm.desktops.active)
        return

    # Tiled source: create a new floating frame at the drop position.
    desktop = ion.wm.desktops.active
    win_rect = window.frame_rect
    size = win_rect.size if win_rect is not None else (640, 480)
    window.move_to_floating(desktop, Rect(ghost, ghost + size))
