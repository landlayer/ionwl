# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

__all__ = (
    "DIRECTION_STEP",
    "DesktopLayout",
    "EdgeDirection",
    "desktop_adjacent",
    "desktop_focus",
    "desktop_layout_calc",
    "desktop_layout_grid",
    "layout_find_adjacent",
)

from typing import TYPE_CHECKING, Literal

import ion

if TYPE_CHECKING:
    from ion.types import Desktop, DesktopItemFloating
    from ion.utils import GeneratorHandle

# A step across the desktop layout: to a neighboring cell, or a diagonal
# to a corner one.
EdgeDirection = Literal[
    'LEFT', 'RIGHT', 'UP', 'DOWN',
    'UP_LEFT', 'UP_RIGHT', 'DOWN_LEFT', 'DOWN_RIGHT',
]

# The grid step each direction takes.
DIRECTION_STEP: dict[EdgeDirection, tuple[int, int]] = {
    'LEFT': (-1, 0),
    'RIGHT': (1, 0),
    'UP': (0, -1),
    'DOWN': (0, 1),
    'UP_LEFT': (-1, -1),
    'UP_RIGHT': (1, -1),
    'DOWN_LEFT': (-1, 1),
    'DOWN_RIGHT': (1, 1),
}


def _grid_cols(n: int) -> int:
    """Return the number of columns for a grid of *n* items (ceiling square root)."""
    cols = 1
    while cols * cols < n:
        cols += 1
    return cols


def desktop_layout_grid(desktops: list[Desktop]) -> list[tuple[tuple[int, int], Desktop]]:
    """Arrange desktops in a grid layout (fallback when no provider handles it).

    Returns ``((x_index, y_index), desktop)`` pairs in a grid with ``_grid_cols`` columns.
    """
    n = len(desktops)
    if n == 0:
        return []
    cols = _grid_cols(n)
    result: list[tuple[tuple[int, int], Desktop]] = []
    for i, d in enumerate(desktops):
        result.append(((i % cols, i // cols), d))
    return result


def desktop_layout_calc(desktops: list[Desktop]) -> list[tuple[tuple[int, int], Desktop]]:
    """Query desktop layout providers, falling back to a grid.

    Iterates `ion.app.preferences.system.desktop_layout_providers` in order. The first
    provider that returns a non-``None`` list wins. If all providers
    return ``None``, :func:`desktop_layout_grid` is used.

    A provider that raises, or returns an invalid layout, is reported
    with :func:`ion.utils.error_report` and skipped.
    """
    import ion

    for provider in ion.app.preferences.system.desktop_layout_providers:
        try:
            result = provider(desktops)
            if result:
                _layout_validate(result)
        except Exception as ex:
            ion.utils.error_report("Desktop layout provider {!r}".format(provider), ex)
            continue
        if result is not None:
            return result
    return desktop_layout_grid(desktops)


def _layout_validate[T](layout: list[tuple[tuple[int, int], T]]) -> None:
    """Raise ``ValueError`` if the layout has duplicate desktops or positions."""
    n = len(layout)
    if len({id(item) for _, item in layout}) != n:
        raise ValueError("duplicate desktops")
    if len({pos for pos, _ in layout}) != n:
        raise ValueError("duplicate positions")


class DesktopLayout:
    """Spatial desktop layout using integer grid-cell positions.

    Each desktop occupies a single cell at ``(x_index, y_index)`` where both
    indices are non-negative integers.
    """

    __slots__ = ('_map', '_min_x_index', '_min_y_index', 'cols', 'layout', 'rows')

    def __init__(self, layout: list[tuple[tuple[int, int], Desktop]]) -> None:
        self.layout = layout
        self._map: dict[Desktop, tuple[int, int]] = {d: pos for pos, d in layout}
        x_indices = [x_index for (x_index, _), _ in layout]
        y_indices = [y_index for (_, y_index), _ in layout]
        min_x_index = min(x_indices)
        min_y_index = min(y_indices)
        self._min_x_index = min_x_index
        self._min_y_index = min_y_index
        self.cols = max(x_indices) - min_x_index + 1
        self.rows = max(y_indices) - min_y_index + 1

    def position(self, desktop: Desktop) -> tuple[int, int] | None:
        """Grid position for a desktop, or ``None``."""
        return self._map.get(desktop)

    def desktop_offset(self, desktop: Desktop, ref: Desktop) -> tuple[int, int]:
        """Offset from *ref* to *desktop* in grid cells."""
        d = self._map[desktop]
        o = self._map[ref]
        return (d[0] - o[0], d[1] - o[1])

    def grid_position(self, desktop: Desktop) -> tuple[int, int]:
        """Position relative to grid origin."""
        pos = self._map[desktop]
        return (pos[0] - self._min_x_index, pos[1] - self._min_y_index)

    def find_adjacent(
        self,
        current: Desktop,
        direction: EdgeDirection,
        wrap: bool = True,
    ) -> Desktop | None:
        """Find the adjacent desktop in the layout."""
        return layout_find_adjacent(self.layout, current, direction, wrap=wrap)


def layout_find_adjacent[T](
    layout: list[tuple[tuple[int, int], T]],
    current: T,
    direction: EdgeDirection,
    wrap: bool = True,
) -> T | None:
    """Find the adjacent item in a spatial layout.

    *layout* is a list of ``((x_index, y_index), item)`` pairs. Returns the
    item in the neighboring cell in the given direction, or ``None``. A
    diagonal names the corner cell alone: an empty corner is not either of
    the cells beside it.

    When *wrap* is true, a straight direction wraps to the opposite end of
    the same row or column, and a diagonal wraps each axis it steps off the
    layout on to the opposite end.
    """
    curr_pos = next((pos for pos, item in layout if item == current), None)
    if curr_pos is None:
        return None

    curr_x_index, curr_y_index = curr_pos
    dx, dy = DIRECTION_STEP[direction]

    # Direct neighbor lookup.
    pos_map: dict[tuple[int, int], T] = {pos: item for pos, item in layout}
    result = pos_map.get((curr_x_index + dx, curr_y_index + dy))
    if result is not None or not wrap:
        return result

    if dx and dy:
        xs = [pos[0] for pos, _ in layout]
        ys = [pos[1] for pos, _ in layout]
        x_index = _index_wrap(curr_x_index + dx, min(xs), max(xs))
        y_index = _index_wrap(curr_y_index + dy, min(ys), max(ys))
        # An axis one cell wide has no opposite end: wrapping it lands back
        # on the current index, and the cell there is the current one or a
        # straight neighbor, neither of which is the corner.
        if x_index == curr_x_index or y_index == curr_y_index:
            return None
        return pos_map.get((x_index, y_index))

    # Wrap to the opposite end of the same row or column: the cells on the
    # stepped axis's line, at its far end.
    axis, line, forward = (0, 1, dx > 0) if dx else (1, 0, dy > 0)
    candidates = [
        (pos, item) for pos, item in layout
        if pos[line] == curr_pos[line] and item != current
    ]
    if not candidates:
        return None

    def along_axis(candidate: tuple[tuple[int, int], T]) -> int:
        return candidate[0][axis]

    if forward:
        return min(candidates, key=along_axis)[1]
    return max(candidates, key=along_axis)[1]


def _index_wrap(index: int, lo: int, hi: int) -> int:
    """Return *index*, or the opposite bound when it steps outside *lo* to *hi* inclusive."""
    if index > hi:
        return lo
    if index < lo:
        return hi
    return index


def desktop_adjacent(direction: EdgeDirection, wrap: bool) -> Desktop | None:
    """Return the desktop beside the active one in *direction* of the spatial
    layout, or ``None``; *wrap* as ``find_adjacent`` takes it.
    """
    desktops = ion.wm.desktops
    return desktops.find_adjacent(desktops.layout_calc(), desktops.active, direction, wrap=wrap)


def desktop_focus(
    desktop: Desktop,
    animate: bool,
    held: DesktopItemFloating | None = None,
) -> GeneratorHandle | None:
    """Focus *desktop*, sliding to it when *animate*.

    *held* is a floating item for the slide to draw above the desktops;
    see ``desktop_switch_impl.exec_generator``. Returns the slide's handle,
    ``None`` when the focus was immediate.
    """
    if animate:
        from ion_utils._internal.operators.desktop_switch_impl import exec_generator
        return ion.utils.exec_generator(exec_generator(desktop, held))
    desktop.focus()
    return None
