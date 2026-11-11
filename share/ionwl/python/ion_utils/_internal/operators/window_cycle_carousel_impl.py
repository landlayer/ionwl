# SPDX-License-Identifier: GPL-3.0-or-later

"""Window carousel generator implementation.

Arranges all windows in a rotating circle controlled by the mouse.
Window overlays are placed on a vertical ellipse sized to fit the
combined output bounds. The top of the circle uses 10% scale and
the bottom uses 100% (native size), giving a 3D carousel effect.
Moving the mouse left/right rotates the circle. Input is matched
against the provided keymap for confirmation and cancellation.
"""

from __future__ import annotations

__all__ = (
    "exec_generator",
)

import math
from collections.abc import Generator

import ion
from ion.types import (
    ColorRGBA,
    Event,
    EventCancel,
    EventMotion,
    EventScroll,
    GeneratorStep,
    Keymap,
    KeymapHandler,
    Overlay,
    OverlayExclusive,
    OverlayGroup,
    OverlayRect,
    OverlayTextDynamicWindowTitle,
    OverlayWindow,
    OverlayWindowIcon,
    Point,
    Rect,
    Size,
    Window,
)

from ion_utils._internal.operators import OverlayScope

_STEP_MS = 16  # ~60 fps.

# Scale range: top of circle (far) to bottom (near).
_SCALE_MIN = 0.1
_SCALE_MAX = 1.0

# Padding between the outermost window edge and the screen edge.
_EDGE_PADDING = 20

# Highlight outline around the front window.
_HIGHLIGHT_WIDTH = 2

# How many pixels of horizontal mouse movement for a full rotation.
_PIXELS_PER_REVOLUTION = 1500.0

_BG_ALPHA = 0.85

_ICON_SIZE = 32
_TITLE_GAP = 4  # Gap between icon and title text.
_TITLE_COLOR = ColorRGBA((1.0, 1.0, 1.0, 1.0))


class _Entry:
    """Tracks a window and its overlay group."""

    __slots__ = ("group", "overlay", "win_size", "window")

    def __init__(
        self,
        window: Window,
        group: OverlayGroup,
        overlay: OverlayWindow,
    ) -> None:
        self.window = window
        self.group = group
        self.overlay = overlay
        # Use the window frame rect as the native size for layout. A window on
        # a never-shown floating workspace has a frame rect with zero size
        # because the split tree has not been laid out yet; fall back to
        # the committed XDG geometry (what `OverlayWindow` actually
        # renders), then to a constant.
        r = window.frame_rect
        if r is not None and r.size.x > 0 and r.size.y > 0:
            self.win_size = r.size
        elif window.size.x > 0 and window.size.y > 0:
            self.win_size = window.size
        else:
            self.win_size = Size((200, 200))


def _layout_circle(
    entries: list[_Entry],
    angle_offset: float,
    center: Point,
    radius: tuple[float, float],
    depth_map: dict[Overlay, float],
) -> _Entry:
    """Position each entry on the ellipse. Return the front entry.

    Populates ``depth_map`` with ``{group: cos_a}`` for z-order sorting.
    """
    rx, ry = radius
    n = len(entries)
    step = math.tau / n
    front_entry: _Entry = entries[0]
    front_cos = 2.0  # Larger than any real cos value.

    for i, e in enumerate(entries):
        a = angle_offset + step * i
        sin_a = math.sin(a)
        cos_a = math.cos(a)

        # Map depth from [-1, +1] (top to bottom) to [SCALE_MIN, SCALE_MAX].
        t = (1.0 - cos_a) * 0.5
        scale = _SCALE_MIN + t * (_SCALE_MAX - _SCALE_MIN)
        # Center the group on the ellipse point.
        ellipse_pos = Point((int(rx * sin_a), int(-ry * cos_a)))
        e.group.position = center + ellipse_pos - e.win_size * scale // 2
        e.group.scale = scale

        # Store depth for z-order sorting (higher cos = farther back).
        depth_map[e.group] = cos_a

        # Track the front-most entry (minimum cos = bottom of ellipse).
        if cos_a < front_cos:
            front_cos = cos_a
            front_entry = e

    return front_entry


def exec_generator(
    keymap: Keymap,
    event: Event,
) -> Generator[GeneratorStep, Event]:
    """Window carousel generator.

    Shows all windows on a 3D carousel ellipse controlled by the mouse.
    Input is matched against the provided keymap for confirmation and
    cancellation.
    """
    # Compute bounding box of all outputs.
    bounds = ion.wm.outputs.bounds_calc()
    if bounds is None:
        return None
    output_size = bounds.size

    # Collect all windows across all desktops.
    windows = [w for w in ion.wm.windows if w.frame_rect is not None]

    if not windows:
        ion.utils.log("Window carousel: no windows.")
        return None

    n = len(windows)

    # Create one group per window containing the window, icon, and title.
    with OverlayScope() as scope:
        entries: list[_Entry] = []
        overlay_group_windows = OverlayGroup()
        scope.append(overlay_group_windows)
        for w in windows:
            group = OverlayGroup()
            group.scale = _SCALE_MIN
            overlay_group_windows.overlays.append(group)

            win_ov = OverlayWindow(w)
            win_ov.align = (-1, -1)
            group.overlays.append(win_ov)

            # Icon at top-left of the group, title to its right.
            icon_ov = OverlayWindowIcon(w)
            icon_ov.align = (-1, -1)
            icon_ov.size = _ICON_SIZE
            group.overlays.append(icon_ov)
            title_ov = OverlayTextDynamicWindowTitle(w)
            title_ov.position = Point((_ICON_SIZE + _TITLE_GAP, 0))
            title_ov.align = (-1, -1)
            group.overlays.append(title_ov)

            entries.append(_Entry(w, group, win_ov))

        # Find the largest native window dimensions across all entries.
        max_size = Size((
            max(e.win_size.x for e in entries),
            max(e.win_size.y for e in entries),
        ))

        # Compute ellipse radii to fill available space.
        mid_scale = (_SCALE_MIN + _SCALE_MAX) * 0.5
        rx = (output_size.x - max_size.x * mid_scale) * 0.5 - _EDGE_PADDING
        ry = output_size.y * 0.5 - max_size.y * _SCALE_MAX * 0.5 - _EDGE_PADDING

        # Clamp to avoid negative radii with very large windows.
        rx = max(rx, 50.0)
        ry = max(ry, 50.0)

        center = bounds.center_floor()

        # Rotate the list so the focused window starts at the bottom (front).
        active_window = ion.wm.windows.active
        focused_index = 0
        if active_window is not None:
            for i, e in enumerate(entries):
                if e.window == active_window:
                    focused_index = i
                    break
        entries = entries[focused_index:] + entries[:focused_index]

        # Create a highlight overlay around the front window.
        highlight = OverlayRect()
        highlight.rect = Rect((0, 0), (1, 1))
        highlight.outline_color = ColorRGBA((1.0, 1.0, 1.0, 1.0))
        highlight.outline_width = _HIGHLIGHT_WIDTH
        scope.append(highlight)

        # Exclusive background: fills the display with a solid color and
        # suppresses all normal scene rendering. Must be added last so it
        # is behind all other overlays.
        bg_color = ion.app.preferences.decor.desktop_color
        bg = OverlayExclusive()
        bg.color = ColorRGBA((bg_color[0], bg_color[1], bg_color[2], _BG_ALPHA))
        scope.append(bg)

        # Depth map populated by `_layout_circle`, used as sort key.
        # Highlight and background are in the root group (fixed order).
        depth_map: dict[Overlay, float] = {}

        # Set up keymap handler for input matching.
        handler = KeymapHandler(event)

        ion.utils.log("Window carousel: {:d} windows.".format(n))

        # Start at pi so entry 0 is at the bottom (front) of the ellipse,
        # ensuring a single window appears in front instead of at the back.
        angle_offset = math.pi
        mouse_x_prev: float | None = None
        radians_per_pixel = math.tau / _PIXELS_PER_REVOLUTION
        radius = (rx, ry)

        def relayout() -> _Entry:
            """Recompute positions, z-order, and highlight."""
            front = _layout_circle(entries, angle_offset, center, radius, depth_map)
            overlay_group_windows.overlays.sort(key=lambda o: depth_map[o])
            pos = front.group.position
            highlight.rect = Rect(
                pos, pos + front.win_size * front.group.scale)
            return front

        front = relayout()
        goto_window = None

        while True:
            event = yield GeneratorStep(time=_STEP_MS, consume_event=True)
            if isinstance(event, EventCancel):
                return

            # Prune entries whose windows were closed during the generator.
            # New windows are not picked up (acceptable limitation).
            if (entries_invalid := [e for e in entries if not e.window.is_valid]):
                for e in entries_invalid:
                    overlay_group_windows.overlays.remove(e.group)
                    del depth_map[e.group]
                entries = [e for e in entries if e.window.is_valid]
                if not entries:
                    break
                n = len(entries)
                front = relayout()

            handler.process_event(event)

            # Motion and scroll are handled directly (not via keymap).
            if isinstance(event, EventMotion):
                px = event.position.x
                if mouse_x_prev is not None:
                    angle_offset += (mouse_x_prev - px) * radians_per_pixel
                mouse_x_prev = px
                front = relayout()

            elif isinstance(event, EventScroll):
                dx, dy = event.delta_x, event.delta_y
                delta = dx if abs(dx) > abs(dy) else dy
                if delta != 0.0:
                    # Use sign only so each scroll step advances exactly one window.
                    angle_offset += math.copysign(math.tau / n, delta)
                    front = relayout()

            else:
                result = handler.match_keymaps([keymap])
                if result is not None:
                    item, props = result
                    idname = type(item.operator)._ion_operator_id  # type: ignore[attr-defined]
                    ion.utils.log("Window carousel: matched {:s} {:s}".format(idname, str(props)))

                    if idname == 'window_carousel_confirm':
                        goto_window = front.window
                        break
                    elif idname == 'window_carousel_cancel':
                        break
    if goto_window is not None:
        # Yield to let the cleared overlays settle, then jump to the window.
        yield GeneratorStep()
        if goto_window.is_valid:
            ion.wm.windows.active_goto(goto_window)

    ion.utils.log("Window carousel: done.")
