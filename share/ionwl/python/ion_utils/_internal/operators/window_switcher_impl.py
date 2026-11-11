# SPDX-License-Identifier: GPL-3.0-or-later

"""Alt-Tab style window switcher.

Shows every window on the current desktop in a centered grid of
icon+title cells. Tab advances the selection, Shift+Tab retreats.
The modifiers held at invocation are remembered; once the user
releases all of them, the selected window is activated and the
operator exits.
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
    EventKey,
    GeneratorStep,
    Keymap,
    KeymapHandler,
    OverlayGroup,
    OverlayRect,
    OverlayTextDynamicWindowTitle,
    OverlayWindowIcon,
    Point,
    Rect,
    Window,
)

from ion_utils._internal.operators import OverlayScope

_STEP_MS = 16  # ~60 fps.

_BG_ALPHA = 0.85

_ICON_SIZE = 64
_ENTRY_WIDTH = 160
_ENTRY_HEIGHT = _ICON_SIZE + 24  # Icon + gap + one line of title.
_CELL_GAP_X = 24
_CELL_GAP_Y = 24
_SCREEN_PAD = 40
_BACKDROP_PAD = 24  # Inset of the backdrop past the outer grid cells.

# White square around the current selection.
_HIGHLIGHT_WIDTH = 2
_HIGHLIGHT_PAD = 4  # Outset from the cell rect so icon/text aren't clipped.
_HIGHLIGHT_COLOR = ColorRGBA((1.0, 1.0, 1.0, 1.0))

_TITLE_COLOR = ColorRGBA((1.0, 1.0, 1.0, 0.95))
_TITLE_GAP = 4  # Gap between icon and title.


class _Entry:
    """Tracks a window and its overlays for one grid cell."""

    __slots__ = ("cell_rect", "group", "icon", "title", "window")

    def __init__(
        self,
        window: Window,
        group: OverlayGroup,
        icon: OverlayWindowIcon,
        title: OverlayTextDynamicWindowTitle,
        cell_rect: Rect,
    ) -> None:
        self.window = window
        self.group = group
        self.icon = icon
        self.title = title
        self.cell_rect = cell_rect


def _grid_layout(n: int, bounds: Rect) -> tuple[int, Point]:
    """Return (cols, origin) for n cells centered in bounds.

    Fills rows left-to-right, wrapping when the row would exceed the
    available width. `origin` is the top-left of the first cell.
    """
    usable_w = max(1, bounds.size.x - 2 * _SCREEN_PAD)
    cols = max(1, (usable_w + _CELL_GAP_X) // (_ENTRY_WIDTH + _CELL_GAP_X))
    cols = min(cols, n)
    rows = math.ceil(n / cols)

    total_w = cols * _ENTRY_WIDTH + (cols - 1) * _CELL_GAP_X
    total_h = rows * _ENTRY_HEIGHT + (rows - 1) * _CELL_GAP_Y
    center = bounds.center_floor()
    origin = Point((center.x - total_w // 2, center.y - total_h // 2))
    return cols, origin


def _cell_rect(index: int, cols: int, origin: Point) -> Rect:
    """Rect of the `index`-th cell in a row-major grid starting at origin."""
    col = index % cols
    row = index // cols
    x = origin.x + col * (_ENTRY_WIDTH + _CELL_GAP_X)
    y = origin.y + row * (_ENTRY_HEIGHT + _CELL_GAP_Y)
    return Rect(Point((x, y)), Point((x + _ENTRY_WIDTH, y + _ENTRY_HEIGHT)))


def _entry_anchor(entry: _Entry) -> None:
    """Snap `entry.icon` / `entry.title` to `entry.cell_rect`."""
    cx = entry.cell_rect.min.x + _ENTRY_WIDTH // 2
    top = entry.cell_rect.min.y
    entry.icon.position = Point((cx, top))
    entry.title.position = Point((cx, top + _ICON_SIZE + _TITLE_GAP))


def _backdrop_rect(n: int, cols: int, origin: Point) -> Rect:
    """Rect tight around an `n`-cell, `cols`-wide grid plus padding."""
    rows = math.ceil(n / cols)
    grid_w = cols * _ENTRY_WIDTH + (cols - 1) * _CELL_GAP_X
    grid_h = rows * _ENTRY_HEIGHT + (rows - 1) * _CELL_GAP_Y
    pad = _BACKDROP_PAD
    return Rect(
        Point((origin.x - pad, origin.y - pad)),
        Point((origin.x + grid_w + pad, origin.y + grid_h + pad)),
    )


def _current_desktop_windows() -> list[Window]:
    """Windows on the active desktop with a valid frame rect, natural order."""
    active_desktop = ion.wm.desktops.active
    return [
        w for w in ion.wm.windows
        if w.frame_rect is not None
        and ion.wm.desktops.find_by_window(w) == active_desktop
    ]


def exec_generator(
    keymap: Keymap,
    direction: int,
    event: Event,
) -> Generator[GeneratorStep, Event]:
    """Window switcher generator.

    Renders a grid of icon+title cells; the initially-focused window is
    highlighted. ``Tab`` / ``Shift-Tab`` move the selection (matched via
    the provided keymap as ``window_switcher_next`` / ``_prev``).
    Releasing every modifier that was held at invocation time
    activates the selection and returns.

    ``direction`` is the initial step to apply from the active window:
    ``1`` leaves the active window selected (forward-shortcut invocation),
    ``-1`` steps one backwards (reverse-shortcut invocation).
    """
    # Snapshot the modifiers held when the operator was invoked. When
    # all of these are no longer held in a later key event, exit.
    initial_mods = event.modifiers

    bounds = ion.wm.outputs.bounds_calc()
    if bounds is None:
        return None

    windows = _current_desktop_windows()
    if not windows:
        ion.utils.log("Window switcher: no windows on current desktop.")
        return None

    cols, origin = _grid_layout(len(windows), bounds)

    active_window = ion.wm.windows.active
    selected = 0
    for i, w in enumerate(windows):
        if w == active_window:
            selected = i
            break

    # Negative `direction` seeds one step backward so a reverse-cycle
    # binding shows the "previous" window on first invocation.
    if direction < 0:
        selected = (selected - 1) % len(windows)

    with OverlayScope() as scope:
        # Add order matters: earlier overlays draw on top of later ones,
        # so the backdrop must be added last to sit behind everything.
        highlight = OverlayRect()
        highlight.rect = Rect(Point((0, 0)), Point((1, 1)))
        highlight.outline_color = _HIGHLIGHT_COLOR
        highlight.outline_width = _HIGHLIGHT_WIDTH
        scope.append(highlight)

        entries: list[_Entry] = []
        cells_group = OverlayGroup()
        scope.append(cells_group)

        for i, w in enumerate(windows):
            cell = _cell_rect(i, cols, origin)
            group = OverlayGroup()
            cells_group.overlays.append(group)

            icon = OverlayWindowIcon(w)
            icon.size = _ICON_SIZE
            icon.align = (0, -1)
            group.overlays.append(icon)

            title = OverlayTextDynamicWindowTitle(w)
            title.color = _TITLE_COLOR
            title.align = (0, -1)
            group.overlays.append(title)

            entry = _Entry(w, group, icon, title, cell)
            _entry_anchor(entry)
            entries.append(entry)

        # Translucent backdrop hugging the grid. Added last so it
        # renders behind the cells/highlight but over the live scene -
        # unlike `OverlayExclusive` it does not suppress scene rendering,
        # so the real windows show through around and behind it.
        bg_color = ion.app.preferences.decor.desktop_color
        backdrop = OverlayRect()
        backdrop.rect = _backdrop_rect(len(entries), cols, origin)
        backdrop.fill_color = ColorRGBA((
            bg_color[0], bg_color[1], bg_color[2], _BG_ALPHA,
        ))
        scope.append(backdrop)

        def highlight_update() -> None:
            cr = entries[selected].cell_rect
            pad = _HIGHLIGHT_PAD
            highlight.rect = Rect(
                Point((cr.min.x - pad, cr.min.y - pad)),
                Point((cr.max.x + pad, cr.max.y + pad)),
            )

        highlight_update()

        handler = KeymapHandler(event)

        ion.utils.log("Window switcher: {:d} windows.".format(len(entries)))

        goto_window = None

        while True:
            event = yield GeneratorStep(time=_STEP_MS, consume_event=True)
            if isinstance(event, EventCancel):
                return

            # Drop entries whose windows closed mid-operator, relayout
            # the survivors, and clamp the selection if it pointed past
            # the end of the trimmed list.
            entries_live = [e for e in entries if e.window.is_valid]
            if len(entries_live) < len(entries):
                live = set(map(id, entries_live))
                for e in entries:
                    if id(e) not in live:
                        cells_group.overlays.remove(e.group)
                if not entries_live:
                    break
                entries = entries_live
                cols, origin = _grid_layout(len(entries), bounds)
                for i, e in enumerate(entries):
                    e.cell_rect = _cell_rect(i, cols, origin)
                    _entry_anchor(e)
                backdrop.rect = _backdrop_rect(len(entries), cols, origin)
                if selected >= len(entries):
                    selected = len(entries) - 1
                highlight_update()

            # Exit when the modifiers held at invocation have all been
            # released. Checked on key events only: timers/motions carry
            # a synthesized modifier mask that would exit prematurely.
            if isinstance(event, EventKey) and (event.modifiers & initial_mods) == 0:
                goto_window = entries[selected].window
                break

            handler.process_event(event)
            result = handler.match_keymaps([keymap])
            if result is None:
                continue

            item, props = result
            idname = type(item.operator)._ion_operator_id  # type: ignore[attr-defined]
            ion.utils.log(
                "Window switcher: matched {:s} {:s}".format(idname, str(props)))

            if idname == 'window_switcher_next':
                selected = (selected + 1) % len(entries)
                highlight_update()
            elif idname == 'window_switcher_prev':
                selected = (selected - 1) % len(entries)
                highlight_update()
            elif idname == 'window_switcher_cancel':
                break

    if goto_window is not None:
        # Yield once so the overlays settle before the focus jump.
        yield GeneratorStep()
        if goto_window.is_valid:
            ion.wm.windows.active_goto(goto_window)

    ion.utils.log("Window switcher: done.")
