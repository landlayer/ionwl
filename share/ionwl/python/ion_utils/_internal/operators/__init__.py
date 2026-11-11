# SPDX-License-Identifier: GPL-3.0-or-later

"""What the operator generators share: the overlays a generator draws,
released together, the edge hover that switches desktop under a drag, and the
keymap check the modal operators start with.
"""

from __future__ import annotations

__all__ = (
    "SLIDE_STEP_MS",
    "DragEdgeSwitch",
    "OverlayScope",
    "modal_keymap_get",
)

from typing import TYPE_CHECKING, NamedTuple, Self

import ion
from ion.types import DesktopItemFloating, GeneratorStep, Overlay, Point

from ion_utils._internal.desktop_layout import EdgeDirection, desktop_adjacent, desktop_focus

if TYPE_CHECKING:
    from ion.types import Keymap
    from ion.utils import GeneratorHandle

# The desktop slide's step (milliseconds), which is also how often a drag
# that started one checks for its landing. Here rather than with the slide,
# which imports this module.
SLIDE_STEP_MS = 16  # ~60 fps.

# The narrowed edge margin, for a drag whose own drop target lies inside the
# band: only a cursor pressed against the screen edge counts there. A frame at
# the top of an output has its whole tab bar inside the `UP` band, so a pause
# while aiming at a slot would otherwise switch desktop, while a cursor pressed
# against the edge is not aiming at one. The pointer clamp stops on the
# output's outermost pixel, so one is exact. A drag-and-drop meets the same tab
# bar and resolves it the other way, its tab hover winning outright (see
# `dnd_hover_update`): a drop slot has no timer to win with, so here the band
# narrows instead.
_EDGE_PRESSED_MARGIN = 1


class OverlayScope:
    """The overlays a generator draws, removed together when its scope exits.

    Only those: a generator started from inside another's scope (a desktop
    slide from a tab drag) may exit first or last, and either way each scope
    must leave the other's overlays alone. Tracking what was appended is
    what allows that; a count or a snapshot of the collection cannot tell
    the two apart once both have appended.
    """
    __slots__ = (
        "_added",
    )

    def __init__(self) -> None:
        self._added: list[Overlay] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        overlays = ion.wm.overlay_root.overlays
        for overlay in reversed(self._added):
            overlays.remove(overlay)
        self._added.clear()

    def append(self, overlay: Overlay) -> None:
        """Append *overlay* to the root group, to be removed when the scope exits."""
        ion.wm.overlay_root.overlays.append(overlay)
        self._added.append(overlay)


class _Armed(NamedTuple):
    """The edge hover's timer: the edge it runs for and the delay it was armed with."""
    direction: EdgeDirection
    delay: int


class DragEdgeSwitch:
    """The edge hover a drag carries: resting the pointer against a screen
    edge for the hover delay switches desktop in that direction, so the drag
    can end on what lives there. A corner is the diagonal: the desktop there,
    or with none, no switch at all.

    The hover is the generator's own step timer, so it needs none of its
    own: while armed, each ``step`` names the delay, restarted for a new
    edge, and a step out of the band names no time. The generator hands its
    events back through ``arm`` (a motion), ``fire`` (its timer) and
    ``landed`` (checked first on every step, as any event may be the one
    that notices).

    The order is not fragile: ``arm`` and ``fire`` both decline while a switch
    is in transit, so a call out of order costs at most one re-arm on the next
    motion.
    """
    __slots__ = (
        "_armed",
        "_restart",
        "_transit",
    )

    def __init__(self) -> None:
        # The hover timer, while one runs, and whether the next step starts
        # it afresh: a new edge gets the full delay, however far the old
        # one's had run.
        self._armed: _Armed | None = None
        self._restart = False
        # The slide a started switch runs, until the step that notices it
        # has ended.
        self._transit: GeneratorHandle | None = None

    @property
    def in_transit(self) -> bool:
        """Whether a started switch is still sliding."""
        return self._transit is not None

    def step(self) -> GeneratorStep:
        """Return the step to yield next.

        The delay while armed, the slide's step while a switch slides, so
        the landing is noticed without waiting for the user to move, and no
        time otherwise.
        """
        restart, self._restart = self._restart, False
        if self._armed is not None:
            return GeneratorStep(time=self._armed.delay, consume_event=True, restart=restart)
        if self._transit is not None:
            return GeneratorStep(time=SLIDE_STEP_MS, consume_event=True)
        return GeneratorStep(consume_event=True)

    def arm(self, position: Point, pressed_only: bool = False) -> None:
        """Arm for the edge *position* rests against; away from every edge,
        disarm.

        *pressed_only* narrows the band to the outermost pixel, for a drag
        whose own drop target lies inside it. Ignored while a switch slides:
        the landing arms afresh.
        """
        if self._transit is not None:
            return
        prefs = ion.app.preferences.dnd
        delay = prefs.edge_switch_delay_ms
        if delay is None:
            self._armed = None
            return
        margin = prefs.edge_margin
        if pressed_only:
            # Never wider than the preference, so a margin of zero stays off.
            margin = min(_EDGE_PRESSED_MARGIN, margin)
        direction = ion._internal.edge_direction_at(position, margin)
        if direction is None:
            self._armed = None
        elif self._armed is None or self._armed.direction != direction:
            self._armed = _Armed(direction, delay)
            self._restart = True

    def landed(self) -> bool:
        """Return whether a started switch has ended since the last step.

        Ended however: a slide that was cancelled or died has ended too, and
        the drag carries on where it is. The caller arms afresh, so holding
        still crosses the next desktop too, after a full delay rather than
        on the step that noticed.
        """
        if self._transit is None or self._transit.pending:
            return False
        self._transit = None
        return True

    def fire(self, held: DesktopItemFloating | None = None) -> bool:
        """The step timer fired: start the switch the hover is armed for.

        Returns whether one started: not with the switch since turned off, and
        not at the end of the row, where nothing re-arms until the pointer
        moves.

        *held* is a floating item for the slide to draw above the desktops,
        the item the drag holds; see ``desktop_switch_impl.exec_generator``.
        """
        if self._armed is None or self._transit is not None:
            return False
        direction = self._armed.direction
        self._armed = None
        # Re-read, as the drag-and-drop's hover does: the preference may have
        # been cleared under an armed timer.
        if ion.app.preferences.dnd.edge_switch_delay_ms is None:
            return False
        target = desktop_adjacent(direction, ion.app.preferences.dnd.edge_wrap)
        if target is None:
            return False
        self._transit = desktop_focus(target, animate=True, held=held)
        return True


def modal_keymap_get(name: str) -> Keymap:
    """Return the keymap named *name* for a modal operator to match input
    against, raising ``ValueError`` when it does not exist.

    Whether the keymap binds an exit is left unchecked, since
    ``Ctrl-Alt-Escape`` ends any modal.
    """
    keymap = ion.app.keymaps.get(name)
    if keymap is None:
        raise ValueError("Modal keymap {!r} does not exist".format(name))
    return keymap
