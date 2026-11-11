# SPDX-License-Identifier: GPL-3.0-or-later

"""Desktop item carousel generator implementation.

Arranges all desktop items (floating frames, floating workspaces,
tiled frames, and fullscreen windows) on a rotating circle controlled by
the mouse. Items are rendered with their borders and decorations via
:class:`OverlayDesktopItem`, fullscreen windows via :class:`OverlayWindow`.
The top of the circle uses 10% scale and the bottom uses 100% (native
size), giving a 3D carousel effect. Moving the mouse left/right rotates
the circle. Input is matched against the provided keymap for confirmation
and cancellation.
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
    DesktopItemFloatingFrame,
    DesktopItemFloatingWorkspace,
    DesktopItemTilingFrame,
    DesktopItemTilingWorkspace,
    Event,
    EventCancel,
    EventMotion,
    EventScroll,
    GeneratorStep,
    Keymap,
    KeymapHandler,
    Overlay,
    OverlayDesktopItem,
    OverlayExclusive,
    OverlayGroup,
    OverlayRect,
    OverlayText,
    OverlayWindow,
    Point,
    Rect,
    Size,
    Window,
)

from ion_utils._internal.operators import OverlayScope

# Source for a carousel entry: a desktop item or a fullscreen window.
_EntrySource = (
    DesktopItemFloatingFrame
    | DesktopItemFloatingWorkspace
    | DesktopItemTilingFrame
    | DesktopItemTilingWorkspace
    | Window
)

# Overlay type for a carousel entry (both have position, scale, align).
_EntryOverlay = OverlayDesktopItem | OverlayWindow

_STEP_MS = 16  # ~60 fps.

# Scale range: top of circle (far) to bottom (near).
_SCALE_MIN = 0.1
_SCALE_MAX = 1.0

# Padding between the outermost item edge and the screen edge.
_EDGE_PADDING = 20

# Highlight outline around the front item.
_HIGHLIGHT_WIDTH = 2

# How many pixels of horizontal mouse movement for a full rotation.
_PIXELS_PER_REVOLUTION = 1500.0

_BG_ALPHA = 0.85

_LABEL_COLOR = ColorRGBA((1.0, 1.0, 1.0, 1.0))


def _entry_label(source: _EntrySource) -> str:
    """Build a label string for a carousel entry source."""
    if isinstance(source, Window):
        return str(source.title) if source.title else "Window"
    if isinstance(source, (DesktopItemFloatingFrame, DesktopItemTilingFrame)):
        w = source.frame.windows.active
        if w is not None and w.title:
            return str(w.title)
        return "Frame"
    return "Workspace: {:s}".format(source.workspace.name)


def _entry_focus(source: _EntrySource) -> None:
    """Focus the selected carousel entry and warp the pointer."""
    if isinstance(source, Window):
        ion.wm.windows.active_goto(source)
        return
    if isinstance(source, (DesktopItemFloatingFrame, DesktopItemTilingFrame)):
        w = source.frame.windows.active
        if w is not None:
            ion.wm.windows.active_goto(w)
    else:
        # Go to the last-focused window in the workspace.
        frame = source.workspace.frames.active
        if frame is not None:
            w = frame.windows.active
            if w is not None:
                ion.wm.windows.active_goto(w)


class _Entry:
    """Tracks a carousel entry and its overlay group."""

    __slots__ = ("group", "item_size", "overlay", "source")

    def __init__(
        self,
        source: _EntrySource,
        group: OverlayGroup,
        overlay: _EntryOverlay,
        item_rect: Rect,
    ) -> None:
        self.source = source
        self.group = group
        self.overlay = overlay
        self.item_size = item_rect.size


def _layout_circle(
    entries: list[_Entry],
    angle_offset: float,
    center: Point,
    radius: tuple[float, float],
    depth_map: dict[Overlay, float],
) -> _Entry:
    """Position each entry group on the ellipse. Return the front entry.

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
        e.group.position = center + ellipse_pos - e.item_size * scale // 2
        e.group.scale = scale

        # Store depth for z-order sorting (higher cos = farther back).
        depth_map[e.group] = cos_a

        # Track the front-most entry (minimum cos = bottom of ellipse).
        if cos_a < front_cos:
            front_cos = cos_a
            front_entry = e

    return front_entry


def _collect_items() -> list[tuple[_EntrySource, Rect]]:
    """Collect all carousel items from all desktops with their bounding rects.

    Fullscreen windows are collected separately (shown via OverlayWindow).
    Frames containing only fullscreen windows are skipped since the window
    is already shown standalone.
    """
    items: list[tuple[_EntrySource, Rect]] = []

    # Collect fullscreen windows first, and track their IDs so we can
    # skip frames that contain only fullscreen windows.
    fullscreen_wids: set[int] = set()
    for w in ion.wm.windows:
        if w.fullscreen:
            r = w.frame_rect
            if r is not None:
                items.append((w, r))
                fullscreen_wids.add(w.id)

    def _frame_has_non_fullscreen(frame_windows: ion.types.FrameWindowCollection) -> bool:
        """Check if a frame has any non-fullscreen window."""
        for w in frame_windows:
            if w.id not in fullscreen_wids:
                return True
        return False

    for desktop in ion.wm.desktops:
        # Floating items (frames and workspaces), their rects copied as the
        # property returns a live view.
        for floating in desktop.items_floating:
            if isinstance(floating, DesktopItemFloatingFrame):
                if _frame_has_non_fullscreen(floating.frame.windows):
                    items.append((floating, floating.rect.copy()))
            elif isinstance(floating, DesktopItemFloatingWorkspace) and not floating.workspace.is_empty:
                items.append((floating, floating.rect.copy()))

        # Tiling items: expand each workspace into individual frames,
        # using the output rect for sizing. Skip empty frames and frames
        # containing only fullscreen windows.
        for tiling in desktop.items_tiling:
            if isinstance(tiling, DesktopItemTilingWorkspace):
                output_rect = tiling.rect
                for frame in tiling.workspace.frames:
                    if _frame_has_non_fullscreen(frame.windows):
                        items.append((DesktopItemTilingFrame(frame), output_rect))

    return items


def exec_generator(
    keymap: Keymap,
    event: Event,
) -> Generator[GeneratorStep, Event]:
    """Desktop item carousel generator.

    Shows all desktop items on a 3D carousel ellipse controlled by the mouse.
    Input is matched against the provided keymap for confirmation and
    cancellation.
    """
    # Compute bounding box of all outputs.
    bounds = ion.wm.outputs.bounds_calc()
    if bounds is None:
        return None

    output_size = bounds.size

    # Collect all desktop items from all desktops.
    collected = _collect_items()

    if not collected:
        ion.utils.log("Desktop item carousel: no items.")
        return None

    n = len(collected)

    # Create one group per item containing the item overlay and label.
    with OverlayScope() as scope:
        entries: list[_Entry] = []
        overlay_group_items = OverlayGroup()
        scope.append(overlay_group_items)
        for source, item_rect in collected:
            group = OverlayGroup()
            group.scale = _SCALE_MIN
            overlay_group_items.overlays.append(group)

            item_ov: _EntryOverlay
            if isinstance(source, Window):
                item_ov = OverlayWindow(source)
            else:
                item_ov = OverlayDesktopItem(source)
            item_ov.align = (-1, -1)
            group.overlays.append(item_ov)

            # Label centered below the item (x offset is half item width,
            # but since it uses center alignment the group handles this).
            label_ov = OverlayText()
            label_ov.text = _entry_label(source)
            label_ov.position = Point((item_rect.size.x // 2, item_rect.size.y))
            label_ov.color = _LABEL_COLOR
            label_ov.align = (0, -1)
            group.overlays.append(label_ov)

            entries.append(_Entry(source, group, item_ov, item_rect))

        # Find the largest native item dimensions across all entries.
        max_size = Size((
            max(e.item_size.x for e in entries),
            max(e.item_size.y for e in entries),
        ))

        # Compute ellipse radii to fill available space.
        mid_scale = (_SCALE_MIN + _SCALE_MAX) * 0.5
        rx = (output_size.x - max_size.x * mid_scale) * 0.5 - _EDGE_PADDING
        ry = output_size.y * 0.5 - max_size.y * _SCALE_MAX * 0.5 - _EDGE_PADDING

        # Clamp to avoid negative radii with very large items.
        rx = max(rx, 50.0)
        ry = max(ry, 50.0)

        center = bounds.center_floor()

        # Rotate the list so the focused item starts at the bottom (front).
        # Find the entry that contains the currently active window.
        focused_index = 0
        active_window = ion.wm.windows.active
        if active_window is not None:
            for i, e in enumerate(entries):
                src = e.source
                if isinstance(src, Window):
                    if src == active_window:
                        focused_index = i
                        break
                elif isinstance(src, (DesktopItemFloatingFrame, DesktopItemTilingFrame)):
                    if active_window in src.frame.windows:
                        focused_index = i
                        break
                elif active_window in src.workspace.windows:
                    focused_index = i
                    break
        entries = entries[focused_index:] + entries[:focused_index]

        # Create a highlight overlay around the front item.
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

        ion.utils.log("Desktop item carousel: {:d} items.".format(n))

        # Start at pi so entry 0 is at the bottom (front) of the ellipse,
        # ensuring a single item appears in front instead of at the back.
        angle_offset = math.pi
        mouse_x_prev: float | None = None
        radians_per_pixel = math.tau / _PIXELS_PER_REVOLUTION
        radius = (rx, ry)

        def relayout() -> _Entry:
            """Recompute positions, z-order, and highlight."""
            front = _layout_circle(entries, angle_offset, center, radius, depth_map)
            overlay_group_items.overlays.sort(key=lambda o: depth_map[o])
            pos = front.group.position
            highlight.rect = Rect(
                pos, pos + front.item_size * front.group.scale)
            return front

        front = relayout()
        focus_source = None

        while True:
            event = yield GeneratorStep(time=_STEP_MS, consume_event=True)
            if isinstance(event, EventCancel):
                return

            # Prune entries whose items were removed during the generator.
            if (entries_invalid := [e for e in entries if not e.source.is_valid]):
                for e in entries_invalid:
                    overlay_group_items.overlays.remove(e.group)
                    del depth_map[e.group]
                entries = [e for e in entries if e.source.is_valid]
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
                    # Use sign only so each scroll step advances exactly one item.
                    angle_offset += math.copysign(math.tau / n, delta)
                    front = relayout()

            else:
                result = handler.match_keymaps([keymap])
                if result is not None:
                    item, props = result
                    idname = type(item.operator)._ion_operator_id  # type: ignore[attr-defined]
                    ion.utils.log("Desktop item carousel: matched {:s} {:s}".format(idname, str(props)))

                    if idname == 'desktop_item_carousel_confirm':
                        focus_source = front.source
                        break
                    elif idname == 'desktop_item_carousel_cancel':
                        break

    if focus_source is not None:
        # Yield to let the cleared overlays settle, then focus the item.
        yield GeneratorStep()
        if focus_source.is_valid:
            _entry_focus(focus_source)

    ion.utils.log("Desktop item carousel: done.")
