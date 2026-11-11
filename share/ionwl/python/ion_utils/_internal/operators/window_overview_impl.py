# SPDX-License-Identifier: GPL-3.0-or-later

"""Window overview generator implementation.

Shows all windows from all desktops as scaled-down live previews
arranged in a non-overlapping grid derived from the desktop spatial
layout, with animated zoom transitions. Each window's grid cell is
chosen to be as close as possible to where the window naturally sits
in the overview, preserving spatial relationships. Input is matched
against the provided keymap for navigation, confirmation, cancellation,
and pointer selection.
"""

from __future__ import annotations

__all__ = (
    "exec_generator",
)

import math
from collections.abc import Callable, Generator, Sequence
from typing import Final

import ion
from ion.types import (
    ColorRGB,
    ColorRGBA,
    Desktop,
    DesktopItemFloating,
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
    OverlayTextDynamicWindowTitle,
    OverlayWindow,
    OverlayWindowIcon,
    Point,
    Rect,
    Size,
    Window,
)

from ion_utils._internal.desktop_layout import DIRECTION_STEP, DesktopLayout, EdgeDirection
from ion_utils._internal.operators import OverlayScope

# Align to top-left so position acts as origin corner.
_ALIGN_MIN: Final = -1

_STEP_MS = 16  # ~60 fps.

# Animation duration in milliseconds.
_ANIM_DURATION_MS = 250

# Background overlay.
_BG_ALPHA = 0.85

# Fraction of cell area a window may fill.
_CELL_FILL = 0.85

# Highlight outline around the selected window (negative width = inset).
_HIGHLIGHT_WIDTH = -3
_HIGHLIGHT_COLOR = ColorRGBA((1.0, 1.0, 1.0, 0.5))
_HIGHLIGHT_HIDDEN = ColorRGBA((0.0, 0.0, 0.0, 0.0))

# Title and icon label styling.
_TITLE_COLOR = ColorRGBA((1.0, 1.0, 1.0, 0.9))
_TITLE_GAP = 4  # Pixels between bottom of window and title.
_ICON_SIZE = 64
_ICON_GAP = 2  # Pixels between bottom of title and icon.
_TITLE_LINE_HEIGHT = 14  # Approximate title text height in pixels.


def _window_overview_rect(w: Window) -> Rect | None:
    """Window's rect for overview layout, with fallbacks for windows without a placed rect.

    A fullscreen window takes its output's origin, since it is drawn there
    rather than in its frame. A floating frame suppressed by a fullscreen
    active tab has no placed rect, so its tabs take the floating item's
    origin. User-hidden floating frames are excluded.

    A window pushed onto a freshly-created floating workspace that has
    not yet been shown sits in a frame whose split-tree rect is still at
    its zero default. Synthesize a rect from the window's committed XDG
    geometry (what ``OverlayWindow`` actually renders) positioned at the
    workspace's eventual floating origin, so the overview entry
    has a hit target that matches the rendered window.

    The synthesized origin uses the workspace's ``floating_rect``,
    which is only conceptually correct for floating frames. For a tiled
    frame on a never-laid-out workspace the absolute position is wrong,
    but the overview only uses it for spatial ordering in cell
    assignment; the size (used for thumbnail scaling and the highlight)
    is accurate. Returns ``None`` when no usable size can be derived, so
    the caller's ``is not None`` filter drops the window rather than
    rendering it as an un-clickable zero-size entry.
    """
    r = w.frame_rect
    output = w.output_fullscreen
    if r is None:
        if not w.is_floating:
            return None
        desktop = ion.wm.desktops.find_by_window(w)
        item = None if desktop is None else _floating_item_find(w, desktop)
        if item is None or not item.visible:
            return None
        origin = (item.rect if output is None else output.rect).min
    elif output is not None:
        origin = output.rect.min
    elif r.size.x > 0 and r.size.y > 0:
        return r
    else:
        ws = ion.wm.workspaces.find_by_window(w)
        if ws is None:
            return None
        origin = ws.floating_rect.min
    size = w.size
    if size.x <= 0 or size.y <= 0:
        return None
    return Rect(origin, origin + size)


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
    """Tracks a window overlay group and its layout position."""

    __slots__ = (
        "group",
        "hidden_at_thumbnail",
        "icon_overlay",
        "label_group",
        "orig_rect",
        "target_rect",
        "thumb_rect",
        "title_overlay",
        "window",
    )

    def __init__(
        self,
        window: ion.types.Window,
        group: OverlayGroup,
        label_group: OverlayGroup,
        title_overlay: OverlayTextDynamicWindowTitle,
        icon_overlay: OverlayWindowIcon,
        orig_rect: Rect,
    ) -> None:
        self.window = window
        self.group = group
        self.label_group = label_group
        self.title_overlay = title_overlay
        self.icon_overlay = icon_overlay
        self.hidden_at_thumbnail = False
        self.orig_rect = orig_rect
        self.thumb_rect = Rect((0, 0), (0, 0))
        self.target_rect = Rect((0, 0), (0, 0))


def _floating_item_find(window: Window, desktop: Desktop) -> DesktopItemFloating | None:
    """The floating item that draws a window: its floating workspace or its own frame."""
    items = desktop.items_floating
    if (workspace := window.workspace) is not None:
        return items.find_by_workspace(workspace)
    frame = ion.wm.frames.find_by_window(window)
    return None if frame is None else items.find_by_frame(frame)


def _window_overlays_update(
    entries: list[_Entry],
    group: OverlayGroup,
    desktop_for_window: dict[Window, Desktop | None],
) -> None:
    """Sort window overlays and mark the windows the desktop does not draw."""
    active_desktop = ion.wm.desktops.active
    fullscreen_windows = {
        window
        for desktop in set(desktop_for_window.values())
        if desktop is not None and desktop.is_valid
        for output in ion.wm.outputs
        if (window := output.fullscreen_window_for_desktop(desktop)) is not None
    }
    depth_map: dict[Overlay, tuple[bool, bool, bool, int]] = {}
    for e in entries:
        window = e.window
        valid = window.is_valid
        frame = ion.wm.frames.find_by_window(window) if valid else None
        desktop = desktop_for_window[window]
        floating = (
            _floating_item_find(window, desktop)
            if valid and desktop is not None and desktop.is_valid else None
        )
        if floating is not None:
            floating_depth = -1 - floating.depth
        else:
            floating_depth = -1 if valid and window.is_floating else 0

        # A fullscreen window is drawn even when another tab is active.
        fullscreen = window in fullscreen_windows
        active_tab = frame is not None and frame.windows.active == window
        # The desktop draws fullscreen windows and the active tabs of placed frames.
        # Goto can switch tabs or clear fullscreen, so re-derive on each update.
        e.hidden_at_thumbnail = not (fullscreen or (active_tab and window.frame_rect is not None))
        # Lower keys are in front; floating depth counts from back to front.
        depth_map[e.group] = (
            not (fullscreen or active_tab),
            desktop != active_desktop,
            not fullscreen,
            floating_depth,
        )
    group.overlays.sort(key=depth_map.__getitem__)


def _position_labels(e: _Entry, rect: Rect) -> None:
    """Position title and icon overlays centered below the window rect."""
    title_y = rect.max.y + _TITLE_GAP
    e.title_overlay.position = Point((rect.center_floor_x(), title_y))
    # Place icon below title. The title height is not queryable, so
    # approximate with a fixed line-height that matches the default font.
    icon_y = title_y + _TITLE_LINE_HEIGHT + _ICON_GAP
    e.icon_overlay.position = Point((rect.center_floor_x(), icon_y))


def _entries_prune(entries: list[_Entry]) -> None:
    """Remove closed windows and their overlays without moving the survivors."""
    for e in [e for e in entries if not e.window.is_valid]:
        for overlay in (e.group, e.label_group):
            parent = overlay.parent
            assert parent is not None
            parent.overlays.remove(overlay)
        entries.remove(e)


def _animate_entries(
    entries: list[_Entry],
    handler: KeymapHandler,
    scale_from: float,
    scale_to: float,
    easing: Callable[[float], float],
    forward: bool,
    bg_rects: list[tuple[OverlayRect, ColorRGB]] | None = None,
) -> Generator[GeneratorStep, Event, bool]:
    """Animate all entry groups between thumbnail and target positions.

    When *forward* is true, lerps from ``thumb_rect`` to ``target_rect``;
    when false, lerps from ``target_rect`` to ``thumb_rect``.
    Prunes closed windows from *entries* before each step.
    *bg_rects* are per-desktop background rectangles whose alpha blends
    from opaque to transparent (forward) or vice versa.
    Returns true if cancelled by an ``EventCancel`` or no windows remain.
    """
    elapsed = 0
    while elapsed < _ANIM_DURATION_MS:
        event = yield GeneratorStep(time=_STEP_MS, consume_event=True)
        if isinstance(event, EventCancel):
            return True
        _entries_prune(entries)
        if not entries:
            return True
        handler.process_event(event)
        if not isinstance(event, EventTimer):
            continue
        elapsed += _STEP_MS
        t = easing(min(elapsed / _ANIM_DURATION_MS, 1.0))

        s = _lerp(scale_from, scale_to, t)
        alpha = t if forward else 1.0 - t
        for e in entries:
            if forward:
                lr = e.thumb_rect.lerp(e.target_rect, t)
            else:
                lr = e.target_rect.lerp(e.thumb_rect, t)
            e.group.position = lr.min
            e.group.scale = s
            if e.hidden_at_thumbnail:
                e.group.alpha = alpha
            _position_labels(e, lr)
            e.label_group.alpha = alpha

        if bg_rects is not None:
            bg_alpha = 1.0 - alpha
            for rect_ov, base_rgb in bg_rects:
                rect_ov.fill_color = base_rgb.to_rgba(bg_alpha)
    return False


def _animate_desktops(
    desk_overlays: list[tuple[Desktop, OverlayDesktop]],
    handler: KeymapHandler,
    dl: DesktopLayout,
    bounds: Rect,
    pivot: Desktop,
    center_from: Point,
    center_to: Point,
    scale_from: float,
    scale_to: float,
    easing: Callable[[float], float],
) -> Generator[GeneratorStep, Event, bool]:
    """Animate desktop overlays between full-screen and thumbnail positions.

    Uses ``desktop_offset`` to keep desktops side-by-side throughout.
    Returns true if cancelled by an ``EventCancel``.
    """
    elapsed = 0
    while elapsed < _ANIM_DURATION_MS:
        event = yield GeneratorStep(time=_STEP_MS, consume_event=True)
        if isinstance(event, EventCancel):
            return True
        handler.process_event(event)
        if not isinstance(event, EventTimer):
            continue
        elapsed += _STEP_MS
        t = easing(min(elapsed / _ANIM_DURATION_MS, 1.0))

        s = _lerp(scale_from, scale_to, t)
        center = center_from.lerp(center_to, t)
        for desktop, overlay in desk_overlays:
            dx, dy = dl.desktop_offset(desktop, pivot)
            overlay.position = Point((
                int(center.x + dx * bounds.size_x * s),
                int(center.y + dy * bounds.size_y * s),
            ))
            overlay.scale = s
    return False


def _entry_at_position(
    entries: list[_Entry], x: int, y: int, label_extra_h: int,
) -> _Entry | None:
    """Find the entry whose target bounds (including label area) contain a screen position."""
    for e in entries:
        tr = e.target_rect
        if (tr.min.x <= x < tr.max.x
                and tr.min.y <= y < tr.max.y + label_extra_h):
            return e
    return None


def _find_adjacent(entries: list[_Entry], selected_idx: int, direction: EdgeDirection) -> int:
    """Find the nearest entry in the given direction (spatial)."""
    sc = entries[selected_idx].target_rect.center_floor()
    dx, dy = DIRECTION_STEP[direction]
    best_idx = selected_idx
    best_dist = float('inf')

    for i, e in enumerate(entries):
        if i == selected_idx:
            continue
        delta = e.target_rect.center_floor() - sc
        # Skip entries not lying the way the step points.
        if delta.x * dx + delta.y * dy <= 0:
            continue

        dist = delta.x * delta.x + delta.y * delta.y
        if dist < best_dist:
            best_dist = dist
            best_idx = i

    return best_idx


def _assign_cells(
    nat_positions: Sequence[tuple[float, float]],
    area: Rect,
    cell_cols: int,
    cell_rows: int,
) -> list[tuple[int, int]]:
    """Assign each entry to the nearest unoccupied grid cell.

    Returns a list of ``(col, row)`` cell assignments, one per entry.
    Uses a greedy algorithm sorted by distance so that windows closest
    to their natural cell get first pick.
    """
    n = len(nat_positions)

    cell_w = area.size_x / cell_cols
    cell_h = area.size_y / cell_rows

    # Precompute cell centers.
    cell_centers = [
        (area.min.x + c * cell_w + cell_w * 0.5,
         area.min.y + r * cell_h + cell_h * 0.5)
        for r in range(cell_rows) for c in range(cell_cols)
    ]
    cell_indices = [
        (c, r) for r in range(cell_rows) for c in range(cell_cols)
    ]

    # Build all (distance_sq, entry_index, cell_index) pairs.
    pairs: list[tuple[float, int, int]] = []
    for i, (nx, ny) in enumerate(nat_positions):
        for ci, (cx, cy) in enumerate(cell_centers):
            dx = nx - cx
            dy = ny - cy
            pairs.append((dx * dx + dy * dy, i, ci))
    pairs.sort()

    # Greedy: first-come, first-served by distance.
    assigned_cells: set[int] = set()
    result: dict[int, tuple[int, int]] = {}
    for _, i, ci in pairs:
        if i in result or ci in assigned_cells:
            continue
        result[i] = cell_indices[ci]
        assigned_cells.add(ci)
        if len(result) == n:
            break

    return [result[i] for i in range(n)]


def exec_generator(
    keymap: Keymap,
    event: Event,
) -> Generator[GeneratorStep, Event]:
    """Window overview generator.

    Zooms out to show all windows in a non-overlapping grid derived
    from the desktop spatial layout, waits for the user to select one,
    then zooms into the chosen window.
    """
    # Compute combined output bounds.
    bounds = ion.wm.outputs.bounds_calc()
    if bounds is None:
        ion.utils.log("Window overview: no outputs.")
        return None
    # Collect all windows with valid rects.
    windows = [w for w in ion.wm.windows if _window_overview_rect(w) is not None]
    if not windows:
        ion.utils.log("Window overview: no windows.")
        return None

    active_window = ion.wm.windows.active
    active_desktop = ion.wm.desktops.active
    desktops = list(ion.wm.desktops)

    # Pre-compute desktop for each window.
    desktop_for_window = {w: ion.wm.desktops.find_by_window(w) for w in windows}
    desktops_with_windows = {d for d in desktop_for_window.values() if d is not None}
    # Windows on orphaned workspaces not assigned to any desktop.
    orphan_windows = [w for w in windows if desktop_for_window[w] is None]
    if not desktops_with_windows:
        ion.utils.log("Window overview: no desktops.")
        return None

    # Compute layout from all desktops so spatial relationships are
    # preserved, then trim rows and columns with no windows.
    all_layout = ion.wm.desktops.layout_calc(desktops)
    pos_for_desktop = {d: pos for pos, d in all_layout}

    occupied_rows: set[int] = set()
    occupied_cols: set[int] = set()
    for d in desktops_with_windows:
        if d in pos_for_desktop:
            col, row = pos_for_desktop[d]
            occupied_rows.add(row)
            occupied_cols.add(col)

    row_remap = {old: new for new, old in enumerate(sorted(occupied_rows))}
    col_remap = {old: new for new, old in enumerate(sorted(occupied_cols))}

    overview_layout: list[tuple[tuple[int, int], Desktop]] = []
    overview_desktops: list[Desktop] = []
    for pos, d in all_layout:
        col, row = pos
        if row in row_remap and col in col_remap:
            overview_layout.append(((col_remap[col], row_remap[row]), d))
            overview_desktops.append(d)

    # Desktops with windows, for per-desktop cell grid assignment.
    window_desktops = sorted(
        desktops_with_windows,
        key=lambda d: desktops.index(d) if d in desktops else 0,
    )

    # Desktop spatial layout and overview geometry.
    dl = DesktopLayout(overview_layout)
    total_grid_rows = dl.rows + (1 if orphan_windows else 0)
    grid_scale = min(1.0 / dl.cols, 1.0 / total_grid_rows)
    thumb = bounds.size * grid_scale
    total = Size((
        round(dl.cols * thumb.x),
        round(total_grid_rows * thumb.y),
    ))
    grid_origin = bounds.min + (bounds.size - total) // 2

    # Per-desktop precomputation: thumbnail rects and background colors.
    prefs = ion.app.preferences
    desk_thumb_rects: dict[Desktop, Rect] = {}
    desk_bg_colors: dict[Desktop, ColorRGB] = {}
    for wd in overview_desktops:
        dgx, dgy = dl.grid_position(wd)
        desk_min = grid_origin + (dgx * thumb.x, dgy * thumb.y)
        desk_thumb_rects[wd] = Rect(desk_min, desk_min + thumb)
        # A copy, as the property returns a live view.
        desk_bg_colors[wd] = prefs.decor.desktop_color.copy()

    # Pivot desktop for zoom animations (active desktop when available).
    pivot_desktop = (
        active_desktop if active_desktop in desk_thumb_rects
        else window_desktops[0]
    )

    n = len(windows)

    # Group windows by desktop for per-desktop grid layout, orphans under `None`.
    windows_per_desktop: dict[Desktop | None, list[Window]] = {}
    for w in windows:
        windows_per_desktop.setdefault(desktop_for_window[w], []).append(w)

    # Cell grids sized to each desktop's window count, the orphans' under `None`.
    thumb_aspect = thumb.x / thumb.y if thumb.y > 0 else 1.0
    desk_grids: dict[Desktop | None, tuple[int, int]] = {}
    for grid_key, d_wins in windows_per_desktop.items():
        k = len(d_wins)
        d_cols = max(1, round(math.sqrt(k * thumb_aspect)))
        d_rows = max(1, math.ceil(k / d_cols))
        while d_cols * d_rows < k:
            d_cols += 1
        desk_grids[grid_key] = (d_cols, d_rows)

    # Orphan section: thumbnail rect for the extra bottom row.
    if orphan_windows:
        orphan_min = grid_origin + (
            (total - thumb).x // 2,
            dl.rows * thumb.y,
        )
        orphan_thumb_rect = Rect(orphan_min, orphan_min + thumb)
        # Spawn rect: thumb-sized region just below `bounds`, horizontally
        # centered. Orphan windows have no desktop to animate from, so they
        # enter from this off-screen "no desktop" tray and exit back to it.
        orphan_spawn_min = Point((
            bounds.center_floor_x() - thumb.x // 2,
            bounds.max.y,
        ))
        orphan_spawn_rect = Rect(
            orphan_spawn_min, orphan_spawn_min + thumb,
        )

    # The output bounds moved to the origin, for mapping window sizes at target scale.
    origin = Point((0, 0))
    bounds_at_origin = Rect(origin, origin + bounds.size)

    with OverlayScope() as scope:
        # Fixed root structure: highlight (front), windows, labels,
        # bg rects, desktops, background (back). Never re-sorted.
        highlight = OverlayRect()
        highlight.rect = Rect((0, 0), (1, 1))
        highlight.outline_color = _HIGHLIGHT_HIDDEN
        highlight.outline_width = _HIGHLIGHT_WIDTH
        scope.append(highlight)
        overlay_group_windows = OverlayGroup()
        scope.append(overlay_group_windows)
        overlay_group_labels = OverlayGroup()
        scope.append(overlay_group_labels)
        overlay_group_bg_rects = OverlayGroup()
        scope.append(overlay_group_bg_rects)
        overlay_group_desktops = OverlayGroup()
        scope.append(overlay_group_desktops)
        bg = OverlayExclusive()
        bg.color = ColorRGBA((0.0, 0.0, 0.0, _BG_ALPHA))
        scope.append(bg)

        # Set up keymap handler for input matching.
        handler = KeymapHandler(event)

        ion.utils.log(
            "Window overview: {:d} windows, {:d} desktops, {:d} orphan.".format(
                n, len(overview_desktops), len(orphan_windows)))

        # ---- Phase 1A: Desktop zoom-out. ----
        desk_overlays: list[tuple[Desktop, OverlayDesktop]] = []
        depth_map: dict[Overlay, float] = {}
        for wd in overview_desktops:
            dov = OverlayDesktop(wd)
            dov.position = bounds.min
            dov.align = (_ALIGN_MIN, _ALIGN_MIN)
            overlay_group_desktops.overlays.append(dov)
            desk_overlays.append((wd, dov))
            depth_map[dov] = -1.0 if wd == pivot_desktop else 0.0

        overlay_group_desktops.overlays.sort(key=lambda o: depth_map[o])

        pivot_target = desk_thumb_rects[pivot_desktop].min
        if (yield from _animate_desktops(
                desk_overlays, handler, dl, bounds,
                pivot_desktop, bounds.min, pivot_target,
                1.0, grid_scale, _ease_out_cubic)):
            return

        # Snap desktops to final thumbnail positions.
        for wd, dov in desk_overlays:
            dov.position = desk_thumb_rects[wd].min
            dov.scale = grid_scale

        # ---- Transition: desktop overlays -> per-window groups. ----
        entries: list[_Entry] = []
        for w in windows:
            if not w.is_valid or (window_rect := _window_overview_rect(w)) is None:
                continue
            group = OverlayGroup()
            group.scale = grid_scale
            overlay_group_windows.overlays.append(group)

            win_ov = OverlayWindow(w)
            win_ov.align = (_ALIGN_MIN, _ALIGN_MIN)
            group.overlays.append(win_ov)

            # Labels are outside the window group so they do not scale
            # with it. A per-entry label group controls fade-in/out alpha.
            lbl_group = OverlayGroup()
            lbl_group.alpha = 0.0
            overlay_group_labels.overlays.append(lbl_group)
            title_ov = OverlayTextDynamicWindowTitle(w)
            title_ov.color = _TITLE_COLOR
            title_ov.align = (0, _ALIGN_MIN)
            lbl_group.overlays.append(title_ov)
            icon_ov = OverlayWindowIcon(w)
            icon_ov.align = (0, _ALIGN_MIN)
            icon_ov.size = _ICON_SIZE
            lbl_group.overlays.append(icon_ov)

            e = _Entry(w, group, lbl_group, title_ov, icon_ov, window_rect)
            entries.append(e)

        if not entries:
            return

        # Use the current sizes, which may have changed during the zoom-out.
        target_scale = 1.0
        for e in entries:
            cols, rows = desk_grids[desktop_for_window[e.window]]
            target_scale = min(
                target_scale,
                thumb.x / cols * _CELL_FILL / max(1, e.orig_rect.size.x),
                thumb.y / rows * _CELL_FILL / max(1, e.orig_rect.size.y),
            )
        target_at_origin = Rect(origin, origin + bounds.size * target_scale)

        # Compute thumb_rect and target_rect per desktop.
        entries_per_desktop: dict[Desktop, list[_Entry]] = {}
        orphan_entries: list[_Entry] = []
        for e in entries:
            ed = desktop_for_window.get(e.window)
            if ed is not None:
                entries_per_desktop.setdefault(ed, []).append(e)
            else:
                orphan_entries.append(e)

        # Stable sort key: tabbed windows share the same rect, so without
        # a tiebreaker their order depends on which tab is active. Use the
        # frame's tile rect (identical for all tabs) with tab index.
        def _entry_sort_key(e: _Entry) -> tuple[int, int, int, int, int]:
            frame = ion.wm.frames.find_by_window(e.window)
            if frame is not None:
                split_node = frame.split_node
                r = split_node.rect if split_node is not None else e.orig_rect
                tab_index = frame.windows.index(e.window)
            else:
                r = e.orig_rect
                tab_index = 0
            return (*r.min, *r.max, tab_index)

        for wd in window_desktops:
            d_rect = desk_thumb_rects[wd]
            d_cols, d_rows = desk_grids[wd]
            d_entries = entries_per_desktop.get(wd, [])
            d_entries.sort(key=_entry_sort_key)

            nat_positions = []
            for e in d_entries:
                e.thumb_rect = bounds.rect_remap_floor(
                    e.orig_rect, d_rect)
                e.group.position = e.thumb_rect.min
                _position_labels(e, e.thumb_rect)
                # Match centers, not the top-left corner: cells are assigned
                # by distance to cell centers, so comparing corners biases
                # windows up-left and can bump a neighbour across a monitor
                # boundary.
                nat_positions.append(e.thumb_rect.center_floor().to_tuple())

            grid_space = Rect((0, 0), (d_cols, d_rows))
            assignments = _assign_cells(
                nat_positions, d_rect, d_cols, d_rows)
            for i, (c, r) in enumerate(assignments):
                e = d_entries[i]
                scaled = bounds_at_origin.rect_remap_floor(
                    Rect(origin, origin + e.orig_rect.size), target_at_origin)
                cell = grid_space.rect_remap_floor(
                    Rect((c, r), (c + 1, r + 1)), d_rect)
                target_min = cell.center_floor() - scaled.center_floor()
                e.target_rect = Rect(target_min, target_min + scaled.size)

        # Assign cells for orphan windows (shown last, below desktops).
        if orphan_entries:
            orphan_entries.sort(key=_entry_sort_key)

            # Natural positions live in `orphan_spawn_rect` (off-screen,
            # below `bounds`) so the enter/exit animation flies in from
            # there. Since every orphan's nat-y is the same, cell
            # assignment against `orphan_thumb_rect` is driven purely by
            # x distance; for `o_rows > 1` this means vertical ordering
            # within the orphan band is arbitrary. Acceptable because
            # orphans (windows on workspaces not assigned to any desktop)
            # have no meaningful vertical relationship to preserve.
            nat_positions = []
            for e in orphan_entries:
                e.thumb_rect = bounds.rect_remap_floor(
                    e.orig_rect, orphan_spawn_rect)
                e.group.position = e.thumb_rect.min
                _position_labels(e, e.thumb_rect)
                nat_positions.append(e.thumb_rect.min.to_tuple())

            o_cols, o_rows = desk_grids[None]
            grid_space = Rect((0, 0), (o_cols, o_rows))
            assignments = _assign_cells(
                nat_positions, orphan_thumb_rect, o_cols, o_rows)
            for i, (c, r) in enumerate(assignments):
                e = orphan_entries[i]
                scaled = bounds_at_origin.rect_remap_floor(
                    Rect(origin, origin + e.orig_rect.size), target_at_origin)
                cell = grid_space.rect_remap_floor(
                    Rect((c, r), (c + 1, r + 1)), orphan_thumb_rect)
                target_min = cell.center_floor() - scaled.center_floor()
                e.target_rect = Rect(target_min, target_min + scaled.size)

        # Replace desktop overlays with per-desktop background rectangles.
        bg_rect_list: list[tuple[OverlayRect, ColorRGB]] = []
        for wd in overview_desktops:
            rect_ov = OverlayRect()
            rect_ov.rect = desk_thumb_rects[wd]
            rect_ov.fill_color = desk_bg_colors[wd].to_rgba(1.0)
            overlay_group_bg_rects.overlays.append(rect_ov)
            bg_rect_list.append((rect_ov, desk_bg_colors[wd]))
        if orphan_entries:
            rect_ov = OverlayRect()
            rect_ov.rect = orphan_thumb_rect
            rect_ov.fill_color = prefs.decor.desktop_color.to_rgba(1.0)
            overlay_group_bg_rects.overlays.append(rect_ov)
            bg_rect_list.append((rect_ov, prefs.decor.desktop_color.copy()))

        overlay_group_desktops.overlays.clear()
        _window_overlays_update(entries, overlay_group_windows, desktop_for_window)
        for e in entries:
            if e.hidden_at_thumbnail:
                e.group.alpha = 0.0

        # ---- Phase 1B: Window spread animation. ----
        # Background rectangles fade from desktop color to transparent.
        if (yield from _animate_entries(
                entries, handler, grid_scale, target_scale,
                _ease_out_cubic, forward=True,
                bg_rects=bg_rect_list)):
            return

        # Remove background rectangles and snap to final grid positions.
        overlay_group_bg_rects.overlays.clear()
        for e in entries:
            e.group.position = e.target_rect.min
            e.group.scale = target_scale
            e.label_group.alpha = 1.0
            _position_labels(e, e.target_rect)

        # Total label height below each window for hit-testing.
        label_extra_h = _TITLE_GAP + _TITLE_LINE_HEIGHT + _ICON_GAP + _ICON_SIZE

        # Start with the active window selected (or first entry).
        selected_idx = next(
            (i for i, e in enumerate(entries) if e.window == active_window), 0)

        def highlight_update(idx: int) -> None:
            """Move the highlight around the selected entry."""
            highlight.rect = entries[idx].target_rect

        # Show highlight for the interactive phase.
        highlight.outline_color = _HIGHLIGHT_COLOR
        highlight_update(selected_idx)

        # ---- Phase 2: Interactive selection. ----
        goto_window = None

        while True:
            event = yield GeneratorStep(time=_STEP_MS, consume_event=True)
            if isinstance(event, EventCancel):
                return
            selected_entry = entries[selected_idx]
            _entries_prune(entries)
            if not entries:
                return
            if selected_entry in entries:
                selected_idx = entries.index(selected_entry)
            else:
                selected_idx = min(selected_idx, len(entries) - 1)
                highlight_update(selected_idx)
            handler.process_event(event)
            result = handler.match_keymaps([keymap])
            if result is None:
                continue

            item, props = result
            idname = type(item.operator)._ion_operator_id  # type: ignore[attr-defined]
            ion.utils.log(
                "Window overview: matched {:s} {:s}".format(idname, str(props)))

            if idname == 'window_overview_confirm':
                goto_window = entries[selected_idx].window
                break
            elif idname == 'window_overview_cancel':
                break
            elif idname == 'window_overview_navigate':
                direction = props.get('direction')
                if direction is not None:
                    new_idx = _find_adjacent(
                        entries, selected_idx, direction)
                    if new_idx != selected_idx:
                        selected_idx = new_idx
                        highlight_update(selected_idx)
            elif idname == 'window_overview_select':
                hit = _entry_at_position(
                    entries, event.position.x, event.position.y,
                    label_extra_h)
                if hit is not None:
                    selected_idx = entries.index(hit)
                    goto_window = hit.window
                    break

        # ---- Phase 3: Determine zoom target. ----
        if goto_window is not None:
            zoom_entry = entries[selected_idx]
        else:
            # Cancelled: zoom back to the active window.
            zoom_entry = next(
                (e for e in entries if e.window == active_window),
                entries[0],
            )
        zoom_desktop = (
            desktop_for_window.get(zoom_entry.window) or pivot_desktop)

        # Switch now so Phase 3A desktop overlays show the target window
        # active and on top. The overlays cover the real scene during
        # animation, so the switch is invisible until they clear.
        if goto_window is not None and goto_window.is_valid:
            ion.wm.windows.active_goto(goto_window)

        # ---- Phase 3B: Window gather. ----
        highlight.outline_color = _HIGHLIGHT_HIDDEN

        # Per-desktop background rectangles starting transparent.
        bg_rect_list_out: list[tuple[OverlayRect, ColorRGB]] = []
        for wd in overview_desktops:
            rect_ov = OverlayRect()
            rect_ov.rect = desk_thumb_rects[wd]
            rect_ov.fill_color = desk_bg_colors[wd].to_rgba(0.0)
            overlay_group_bg_rects.overlays.append(rect_ov)
            bg_rect_list_out.append((rect_ov, desk_bg_colors[wd]))
        if orphan_entries:
            rect_ov = OverlayRect()
            rect_ov.rect = orphan_thumb_rect
            rect_ov.fill_color = prefs.decor.desktop_color.to_rgba(0.0)
            overlay_group_bg_rects.overlays.append(rect_ov)
            bg_rect_list_out.append((rect_ov, prefs.decor.desktop_color.copy()))

        _window_overlays_update(entries, overlay_group_windows, desktop_for_window)

        # Animate windows from grid cells back to thumbnail positions.
        # Background rectangles fade from transparent to desktop color.
        if (yield from _animate_entries(
                entries, handler, target_scale, grid_scale,
                _ease_in_cubic, forward=False,
                bg_rects=bg_rect_list_out)):
            return

        # Replace window groups, labels, and bg rects with desktop overlays.
        overlay_group_windows.overlays.clear()
        overlay_group_labels.overlays.clear()
        overlay_group_bg_rects.overlays.clear()

        desk_overlays_out: list[tuple[Desktop, OverlayDesktop]] = []
        for wd in overview_desktops:
            tr = desk_thumb_rects[wd]
            dov = OverlayDesktop(wd)
            dov.position = tr.min
            dov.scale = grid_scale
            dov.align = (_ALIGN_MIN, _ALIGN_MIN)
            overlay_group_desktops.overlays.append(dov)
            desk_overlays_out.append((wd, dov))
            depth_map[dov] = -1.0 if wd == zoom_desktop else 0.0

        overlay_group_desktops.overlays.sort(key=lambda o: depth_map[o])

        # ---- Phase 3A: Desktop zoom-in. ----
        zoom_target = desk_thumb_rects[zoom_desktop].min
        if (yield from _animate_desktops(
                desk_overlays_out, handler, dl, bounds,
                zoom_desktop, zoom_target, bounds.min,
                grid_scale, 1.0, _ease_in_cubic)):
            return

    ion.utils.log("Window overview: done.")
