# SPDX-License-Identifier: GPL-3.0-or-later

"""Desktop switch slide animation generator.

Animates switching from the current desktop to a target desktop by
sliding all desktops side-by-side at full scale from the old position
to the new.
"""

from __future__ import annotations

__all__ = (
    "exec_generator",
)

from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from typing import Final

import ion
from ion.types import (
    ColorRGBA,
    Desktop,
    DesktopItemFloating,
    Event,
    EventCancel,
    EventTimer,
    GeneratorStep,
    OverlayDesktop,
    OverlayDesktopItem,
    OverlayRect,
    Point,
)

from ion_utils._internal.desktop_layout import DesktopLayout
from ion_utils._internal.operators import SLIDE_STEP_MS, OverlayScope

# Align to top-left so position acts as origin corner.
_ALIGN_MIN: Final = -1

# Background overlay.
_BG_ALPHA = 1.0


@contextmanager
def _holding(scope: OverlayScope, item: DesktopItemFloating | None) -> Iterator[Callable[[], None]]:
    """Draw *item* above the desktops for the duration, the desktop overlays
    skipping it meanwhile; ``None`` holds nothing.

    Yields a callable that moves the overlay onto the item's current rect;
    the slide calls it each step, so the overlay trails the drag by a step at
    most. The overlay goes into *scope* before the desktops do, so it draws
    in front of them. The skip is this context's: it is taken back on the
    way out however that comes, so no drag has to remember to.
    """
    if item is None:
        yield lambda: None
        return
    overlay = OverlayDesktopItem(item)
    overlay.align = (_ALIGN_MIN, _ALIGN_MIN)
    scope.append(overlay)

    def follow() -> None:
        # An item that closed under the slide has no rect, and its overlay
        # draws nothing.
        if item.is_valid:
            overlay.position = item.rect.min

    follow()
    item.skip_desktop_overlay = True
    try:
        yield follow
    finally:
        # A closed item's skip is inert, and the generator drain clears it.
        if item.is_valid:
            item.skip_desktop_overlay = False


def exec_generator(
    target: Desktop,
    held: DesktopItemFloating | None = None,
) -> Generator[GeneratorStep, Event]:
    """Slide from the active desktop to *target*.

    All desktops remain at full scale throughout, arranged side-by-side
    using the spatial layout from desktop layout providers.
    The view slides linearly from the old desktop's position to the new.

    *held* is a floating item drawn above the desktops at its own rect,
    and skipped by the desktop overlays meanwhile: the item a drag holds,
    which stays under the pointer while the desktops move beneath it. The
    drag keeps its rect following the pointer, and moves it across once the
    slide has landed.
    """
    active_desktop = ion.wm.desktops.active

    if target == active_desktop:
        return None

    # Compute combined output bounds.
    bounds = ion.wm.outputs.bounds_calc()
    if bounds is None:
        return None
    desktops = list(ion.wm.desktops)
    if len(desktops) <= 1:
        return None

    # Get spatial layout from providers (or fallback grid).
    dl = DesktopLayout(ion.wm.desktops.layout_calc())

    if dl.position(active_desktop) is None or dl.position(target) is None:
        return None

    # Total slide delta.
    dx, dy = dl.desktop_offset(target, active_desktop)
    delta = Point((
        round(-dx * bounds.size.x),
        round(-dy * bounds.size.y),
    ))

    # Create desktop overlays at their start positions (old at origin).
    # Desktops are side-by-side at full scale with no gaps.
    with OverlayScope() as scope, _holding(scope, held) as follow:
        overlays: list[OverlayDesktop] = []
        start_positions: list[Point] = []
        for d in desktops:
            if dl.position(d) is None:
                continue
            ox, oy = dl.desktop_offset(d, active_desktop)
            start = bounds.min + Point((
                round(ox * bounds.size.x),
                round(oy * bounds.size.y),
            ))
            start_positions.append(start)
            ov = OverlayDesktop(d)
            ov.position = start
            ov.align = (_ALIGN_MIN, _ALIGN_MIN)
            scope.append(ov)
            overlays.append(ov)

        # Opaque background on top to hide the live desktop beneath the overlays.
        bg_rect = OverlayRect()
        bg_rect.rect = bounds
        bg_rect.fill_color = ColorRGBA((0.0, 0.0, 0.0, _BG_ALPHA))
        scope.append(bg_rect)

        # Slide animation: apply a single integer delta to all overlays.
        # Only advance on timer events; consumed input events are ignored
        # so mouse motion does not accelerate the animation.
        # The preference is read once: a change mid-slide would rescale the
        # part already run.
        duration = ion.app.preferences.animate.desktop_slide_duration
        elapsed = 0
        while elapsed < duration:
            ev = yield GeneratorStep(time=SLIDE_STEP_MS, consume_event=True)
            if isinstance(ev, EventCancel):
                return
            follow()
            if not isinstance(ev, EventTimer):
                continue
            elapsed += SLIDE_STEP_MS
            t = min(elapsed / duration, 1.0)
            offset = Point((round(delta.x * t), round(delta.y * t)))

            for overlay, s in zip(overlays, start_positions):
                overlay.position = s + offset

        # Switch desktop before clearing overlays so the next rendered frame
        # shows the new desktop with no overlays.
        if target.is_valid:
            target.focus()
