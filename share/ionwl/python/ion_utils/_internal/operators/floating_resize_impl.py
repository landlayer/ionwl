# SPDX-License-Identifier: GPL-3.0-or-later

"""Floating resize generator implementation.

Handles interactive resizing of a floating item (window frame or
workspace) by dragging with the pointer. The resize edge
is determined by the pointer quadrant relative to the item center.
"""

from __future__ import annotations

__all__ = (
    "exec_generator",
)

from collections.abc import Generator

import ion
import ion.constants.resize_edges as edges
from ion.types import (
    Event,
    EventCancel,
    EventMotion,
    EventPointer,
    GeneratorStep,
    Point,
    Rect,
    Size,
)

_CURSOR_NAMES = {
    edges.TOP_LEFT: "nw-resize",
    edges.TOP_RIGHT: "ne-resize",
    edges.BOTTOM_LEFT: "sw-resize",
    edges.BOTTOM_RIGHT: "se-resize",
    edges.TOP: "n-resize",
    edges.BOTTOM: "s-resize",
    edges.LEFT: "w-resize",
    edges.RIGHT: "e-resize",
}

# tan(22.5 deg) = sqrt(2) - 1.  Boundary between edge and corner sectors
# when dividing the rect into 8 equal angular zones.
_TAN_22_5 = 0.41421356


def _edge_from_border(pos: Point, rect: Rect, corner_size: int) -> int:
    """Determine resize edge for a drag initiated from the window border.

    Corners are detected within *corner_size* pixels of each corner.
    The remaining border regions are straight edges, selected by the
    nearest side.
    """
    left = rect.min.x
    top = rect.min.y
    right = rect.max.x
    bottom = rect.max.y

    # Corners (extend corner_size pixels along each edge).
    if pos.x < left + corner_size and pos.y < top + corner_size:
        return edges.TOP_LEFT
    if pos.x >= right - corner_size and pos.y < top + corner_size:
        return edges.TOP_RIGHT
    if pos.x < left + corner_size and pos.y >= bottom - corner_size:
        return edges.BOTTOM_LEFT
    if pos.x >= right - corner_size and pos.y >= bottom - corner_size:
        return edges.BOTTOM_RIGHT

    # Straight edges - nearest side.
    dy_top = pos.y - top
    dy_bottom = bottom - pos.y
    dx_left = pos.x - left
    dx_right = right - pos.x

    if min(dy_top, dy_bottom) <= min(dx_left, dx_right):
        return edges.TOP if dy_top <= dy_bottom else edges.BOTTOM
    return edges.LEFT if dx_left <= dx_right else edges.RIGHT


def _edge_from_interior(pos: Point, rect: Rect) -> int:
    """Determine resize edge for a drag initiated inside the window.

    Divides the rect into 8 equal angular sectors (aspect-ratio-corrected):
    4 corner zones centered on the diagonals and 4 edge zones centered
    on the axes.
    """
    # Signed offset from center, cross-multiplied to normalize for
    # aspect ratio (the common factor of 2 cancels in the comparison).
    w = rect.max.x - rect.min.x
    h = rect.max.y - rect.min.y
    sx = (2 * pos.x - rect.min.x - rect.max.x) * h
    sy = (2 * pos.y - rect.min.y - rect.max.y) * w
    ax = abs(sx)
    ay = abs(sy)

    if ax >= ay:
        if ay < ax * _TAN_22_5:
            return edges.LEFT if sx < 0 else edges.RIGHT
        if sx < 0:
            return edges.TOP_LEFT if sy < 0 else edges.BOTTOM_LEFT
        return edges.TOP_RIGHT if sy < 0 else edges.BOTTOM_RIGHT
    if ax < ay * _TAN_22_5:
        return edges.TOP if sy < 0 else edges.BOTTOM
    if sy < 0:
        return edges.TOP_LEFT if sx < 0 else edges.TOP_RIGHT
    return edges.BOTTOM_LEFT if sx < 0 else edges.BOTTOM_RIGHT


def _resize_rect_calc(
    initial: Rect,
    edge: int,
    delta: Point,
    size_min: Size,
    size_max: Size | None,
) -> Rect:
    """Compute new rect from initial rect, edge, and pointer delta."""

    # Clamp to min/max size (max component 0 = unconstrained).
    def clamp_w(v: int) -> int:
        v = max(v, size_min.x)
        if size_max is not None and size_max.x > 0:
            v = min(v, size_max.x)
        return v

    def clamp_h(v: int) -> int:
        v = max(v, size_min.y)
        if size_max is not None and size_max.y > 0:
            v = min(v, size_max.y)
        return v

    if edge == edges.TOP_LEFT:
        new_size = Size((
            clamp_w(initial.size.x - delta.x),
            clamp_h(initial.size.y - delta.y),
        ))
        new_min = initial.min + (initial.size - new_size)
    elif edge == edges.TOP_RIGHT:
        new_size = Size((
            clamp_w(initial.size.x + delta.x),
            clamp_h(initial.size.y - delta.y),
        ))
        new_min = initial.min + (0, initial.size.y - new_size.y)
    elif edge == edges.BOTTOM_LEFT:
        new_size = Size((
            clamp_w(initial.size.x - delta.x),
            clamp_h(initial.size.y + delta.y),
        ))
        new_min = initial.min + (initial.size.x - new_size.x, 0)
    elif edge == edges.BOTTOM_RIGHT:
        new_size = Size((
            clamp_w(initial.size.x + delta.x),
            clamp_h(initial.size.y + delta.y),
        ))
        new_min = initial.min
    elif edge == edges.TOP:
        new_size = Size((
            initial.size.x,
            clamp_h(initial.size.y - delta.y),
        ))
        new_min = initial.min + (0, initial.size.y - new_size.y)
    elif edge == edges.BOTTOM:
        new_size = Size((
            initial.size.x,
            clamp_h(initial.size.y + delta.y),
        ))
        new_min = initial.min
    elif edge == edges.LEFT:
        new_size = Size((
            clamp_w(initial.size.x - delta.x),
            initial.size.y,
        ))
        new_min = initial.min + (initial.size.x - new_size.x, 0)
    else:
        # `edges.RIGHT`.
        new_size = Size((
            clamp_w(initial.size.x + delta.x),
            initial.size.y,
        ))
        new_min = initial.min

    return Rect(new_min, new_min + new_size)


def exec_generator(
    event: Event,
    *,
    border: bool = False,
) -> Generator[GeneratorStep, Event]:
    """Resize the floating item under the pointer.

    The generator consumes all input events until the initiating
    pointer button is released.
    """
    item = ion._internal.floating_item_at_pointer()
    if item is None:
        return None

    assert isinstance(event, EventPointer)
    grab_button = event.button

    initial_pos = event.position
    # A copy, as the drag assigns the property this would be a live view of.
    initial_rect = item.rect.copy()
    if border:
        # Read the edge ionwl resolved for the resize cursor, and do it before
        # raising the item below: raising can invalidate the pointer-over cache
        # this reads (it does when `pointer_click_to_raise` is set, which
        # raises the item), so a query afterwards may miss. Matching the
        # cursor's edge keeps the drag and the displayed resize cursor in
        # agreement.
        edge = ion._internal.floating_resize_edge_at_pointer()
        if edge is None:
            # No cached resize border to read. The drag binding warps back to
            # the press position and recomputes the cache before this runs, so
            # a border hit is the norm; the miss is a safety net for when the
            # item under the press is no longer a resize border (e.g. it moved
            # or closed between press and drag). Without the cache, classify
            # against the item rect: it can differ slightly from the cache's
            # content-rect edges, but no resize cursor was shown to disagree
            # with.
            corner_size = ion.app.preferences.floating.corner_resize_size
            edge = _edge_from_border(initial_pos, initial_rect, corner_size)
    else:
        edge = _edge_from_interior(initial_pos, initial_rect)

    ion._internal.floating_focus_raise(item)

    # Effective size constraints: preference minimum floor plus
    # client-advertised hints when the item is a frame.
    pref_min = ion.app.preferences.floating.size_min
    size_min = Size((pref_min, pref_min))
    size_max: Size | None = None
    frame = getattr(item, "frame", None)
    if frame is not None:
        cl_min, cl_max = ion._internal.floating_frame_resize_begin(frame, edge)
        size_min = Size((max(size_min.x, cl_min.x), max(size_min.y, cl_min.y)))
        size_max = cl_max

    cursor_token = ion.wm.cursor_push(_CURSOR_NAMES[edge])
    try:
        while True:
            event = yield GeneratorStep(consume_event=True)

            if isinstance(event, EventCancel):
                return

            # The item can go under the drag, its last window closing. Nothing
            # left to resize, and a write to it would raise.
            if not item.is_valid:
                return

            if isinstance(event, EventPointer) and not event.press and event.button == grab_button:
                return

            if isinstance(event, EventMotion):
                delta = event.position - initial_pos
                item.rect = _resize_rect_calc(
                    initial_rect, edge, delta, size_min, size_max,
                )
    finally:
        ion.wm.cursor_pop(cursor_token)
        if frame is not None:
            ion._internal.floating_frame_resize_end()
