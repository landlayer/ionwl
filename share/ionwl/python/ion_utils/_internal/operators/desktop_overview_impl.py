# SPDX-License-Identifier: GPL-3.0-or-later

"""Desktop overview generator implementation.

Shows all desktops as scaled-down live previews arranged using the
spatial layout from desktop layout providers, with animated zoom
transitions. Input is matched against the provided keymap for
navigation, confirmation, cancellation, and pointer selection.
"""

from __future__ import annotations

__all__ = (
    "exec_generator",
)

from collections.abc import Generator
from typing import Final

import ion
from ion.types import (
    ColorRGBA,
    Desktop,
    Event,
    EventCancel,
    EventTimer,
    GeneratorStep,
    Keymap,
    KeymapHandler,
    Overlay,
    OverlayDesktop,
    OverlayExclusive,
    OverlayGroup,
    OverlayRect,
    Point,
    Rect,
    Size,
)

from ion_utils._internal.desktop_layout import DesktopLayout
from ion_utils._internal.operators import OverlayScope

# Align to top-left so position acts as origin corner.
_ALIGN_MIN: Final = -1

_STEP_MS = 16  # ~60 fps.

# Animation duration in milliseconds.
_ANIM_DURATION_MS = 250

# Background overlay.
_BG_ALPHA = 0.85

# Highlight outline around the selected desktop (negative width = inset).
_HIGHLIGHT_WIDTH = -3
_HIGHLIGHT_COLOR = ColorRGBA((1.0, 1.0, 1.0, 0.5))
_HIGHLIGHT_HIDDEN = ColorRGBA((0.0, 0.0, 0.0, 0.0))


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation from a to b."""
    return a + (b - a) * t


def _ease_out_cubic(t: float) -> float:
    """Ease-out cubic curve (deceleration)."""
    t = 1.0 - t
    return 1.0 - t * t * t


def _ease_in_cubic(t: float) -> float:
    """Ease-in cubic curve (acceleration)."""
    return t * t * t


class _Entry:
    """Tracks a desktop overlay and its grid position."""

    __slots__ = ("desktop", "overlay", "target_rect")

    def __init__(self, desktop: Desktop, overlay: OverlayDesktop) -> None:
        self.desktop = desktop
        self.overlay = overlay
        self.target_rect = Rect((0, 0), (0, 0))


def _entry_at_position(entries: list[_Entry], pos: Point) -> _Entry | None:
    """Find the entry under a screen position."""
    for e in entries:
        if e.target_rect.contains(pos):
            return e
    return None


def exec_generator(
    keymap: Keymap,
    event: Event,
    trim_empty: bool = False,
) -> Generator[GeneratorStep, Event]:
    """Desktop overview generator.

    Zooms out to show all desktops using the spatial layout, waits for
    the user to select one, then zooms into the chosen desktop.
    """
    # Compute combined output bounds.
    bounds = ion.wm.outputs.bounds_calc()
    if bounds is None:
        ion.utils.log("Desktop overview: no outputs.")
        return None
    desktops = list(ion.wm.desktops)
    if not desktops:
        ion.utils.log("Desktop overview: no desktops.")
        return None

    active_desktop = ion.wm.desktops.active

    # Trim empty desktops from the endpoints (active desktop always included).
    if trim_empty and len(desktops) > 1:
        active_i = desktops.index(active_desktop)
        first = len(desktops)
        last = 0
        for i, d in enumerate(desktops):
            if not d.is_empty:
                first = min(first, i)
                last = i
        if first > last:
            # All desktops empty, show all.
            first = 0
            last = len(desktops) - 1
        first = min(first, active_i)
        last = max(last, active_i)
        desktops = desktops[first:last + 1]

    if len(desktops) <= 1:
        ion.utils.log("Desktop overview: need at least 2 desktops.")
        return None

    # Get spatial layout from providers (or fallback grid).
    dl = DesktopLayout(ion.wm.desktops.layout_calc(desktops))

    # Compute overview thumbnail scale and positions.
    grid_scale = min(1.0 / dl.cols, 1.0 / dl.rows)
    thumb = bounds.size * grid_scale
    total = Size((
        round(dl.cols * thumb.x),
        round(dl.rows * thumb.y),
    ))
    grid_origin = bounds.min + (bounds.size - total) // 2

    with OverlayScope() as scope:
        # Create highlight overlay (hidden until interactive phase).
        # Added first so it is in front of the desktops it outlines.
        highlight = OverlayRect()
        highlight.rect = Rect((0, 0), (1, 1))
        highlight.outline_color = _HIGHLIGHT_HIDDEN
        highlight.outline_width = _HIGHLIGHT_WIDTH
        scope.append(highlight)

        # Create a desktop overlay for each desktop at full screen.
        entries: list[_Entry] = []
        entry_map: dict[Desktop, _Entry] = {}
        overlay_group_desktops = OverlayGroup()
        scope.append(overlay_group_desktops)
        for d in desktops:
            overlay = OverlayDesktop(d)
            overlay.position = bounds.min
            overlay.align = (_ALIGN_MIN, _ALIGN_MIN)
            overlay_group_desktops.overlays.append(overlay)
            e = _Entry(d, overlay)
            gx, gy = dl.grid_position(d)
            desk_min = grid_origin + (round(gx * thumb.x), round(gy * thumb.y))
            e.target_rect = Rect(desk_min, desk_min + thumb)
            entries.append(e)
            entry_map[d] = e

        # Exclusive background: fills the display with a solid color and
        # suppresses all normal scene rendering. Must be added last so it
        # is behind all other overlays.
        bg = OverlayExclusive()
        bg.color = ColorRGBA((0.0, 0.0, 0.0, _BG_ALPHA))
        scope.append(bg)

        # Sort: active desktop on top during zoom-out so the initial
        # frame matches the current view.
        depth_map: dict[Overlay, float] = {}
        for e in entries:
            depth_map[e.overlay] = -1.0 if e.desktop == active_desktop else 0.0
        overlay_group_desktops.overlays.sort(key=lambda o: depth_map[o])

        # Select the active desktop initially.
        selected = entry_map.get(active_desktop, entries[0])

        def highlight_update(entry: _Entry) -> None:
            """Move the highlight around the selected entry."""
            highlight.rect = entry.target_rect

        ion.utils.log("Desktop overview: {:d} desktops.".format(len(entries)))

        # Set up keymap handler for input matching.
        handler = KeymapHandler(event)

        # ---- Phase 1: Zoom-out animation. ----
        # Use layout coordinates to position desktops relative to the active one
        # at every scale, keeping them side-by-side throughout the animation.
        origin = bounds.min
        active_target = selected.target_rect.min

        # Only advance on timer events; consumed input events are fed to the
        # keymap handler but do not advance the animation.
        elapsed = 0
        while elapsed < _ANIM_DURATION_MS:
            event = yield GeneratorStep(time=_STEP_MS, consume_event=True)
            if isinstance(event, EventCancel):
                return
            handler.process_event(event)
            if not isinstance(event, EventTimer):
                continue
            elapsed += _STEP_MS
            t = _ease_out_cubic(min(elapsed / _ANIM_DURATION_MS, 1.0))

            s = _lerp(1.0, grid_scale, t)
            center = origin.lerp(active_target, t)
            for e in entries:
                dx, dy = dl.desktop_offset(e.desktop, selected.desktop)
                e.overlay.position = Point((
                    int(center.x + dx * bounds.size.x * s),
                    int(center.y + dy * bounds.size.y * s)))
                e.overlay.scale = s

        # Snap to final grid positions.
        for e in entries:
            e.overlay.position = e.target_rect.min
            e.overlay.scale = grid_scale

        # Show highlight for interactive phase.
        highlight.outline_color = _HIGHLIGHT_COLOR
        highlight_update(selected)

        # ---- Phase 2: Interactive selection. ----
        goto_desktop = None

        while True:
            event = yield GeneratorStep(time=_STEP_MS, consume_event=True)
            if isinstance(event, EventCancel):
                return
            handler.process_event(event)
            result = handler.match_keymaps([keymap])
            if result is None:
                continue

            item, props = result
            idname = type(item.operator)._ion_operator_id  # type: ignore[attr-defined]
            ion.utils.log("Desktop overview: matched {:s} {:s}".format(idname, str(props)))

            if idname == 'desktop_overview_confirm':
                goto_desktop = selected.desktop
                break
            elif idname == 'desktop_overview_cancel':
                break
            elif idname == 'desktop_overview_navigate':
                direction = props.get('direction')
                if direction is not None:
                    adjacent = dl.find_adjacent(selected.desktop, direction, wrap=True)
                    if adjacent is not None:
                        selected = entry_map[adjacent]
                        highlight_update(selected)
            elif idname == 'desktop_overview_select':
                hit = _entry_at_position(entries, event.position)
                if hit is not None:
                    selected = hit
                    goto_desktop = hit.desktop
                    break

        # ---- Phase 3: Zoom-in animation. ----
        # Determine which desktop to zoom into.
        if goto_desktop is not None:
            zoom_target = entry_map.get(goto_desktop, selected)
        else:
            # Cancelled: zoom back into the active desktop.
            zoom_target = entry_map.get(active_desktop, entries[0])

        # Hide highlight and put the zoom target on top.
        highlight.outline_color = _HIGHLIGHT_HIDDEN
        for e in entries:
            depth_map[e.overlay] = -1.0 if e is zoom_target else 0.0
        overlay_group_desktops.overlays.sort(key=lambda o: depth_map[o])

        # Zoom into the target desktop.
        zoom_target_pos = zoom_target.target_rect.min

        elapsed = 0
        while elapsed < _ANIM_DURATION_MS:
            event = yield GeneratorStep(time=_STEP_MS, consume_event=True)
            if isinstance(event, EventCancel):
                return
            handler.process_event(event)
            if not isinstance(event, EventTimer):
                continue
            elapsed += _STEP_MS
            t = _ease_in_cubic(min(elapsed / _ANIM_DURATION_MS, 1.0))

            s = _lerp(grid_scale, 1.0, t)
            center = zoom_target_pos.lerp(origin, t)
            for e in entries:
                dx, dy = dl.desktop_offset(e.desktop, zoom_target.desktop)
                e.overlay.position = Point((
                    int(center.x + dx * bounds.size.x * s),
                    int(center.y + dy * bounds.size.y * s)))
                e.overlay.scale = s

        # Switch desktop before clearing overlays so the next rendered frame
        # shows the new desktop with no overlays. Doing both in the same
        # generator step avoids a one-frame flash of the old desktop.
        if goto_desktop is not None and goto_desktop.is_valid and goto_desktop != active_desktop:
            goto_desktop.focus()

    ion.utils.log("Desktop overview: done.")
