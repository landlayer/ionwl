This module contains all type definitions used across
the ion API. Most types are reached through other modules - entity
proxies via :mod:`ion.wm` collections, configuration objects via
:mod:`ion.app`. The types you'll typically import directly are the
input matchers and geometry primitives.

.. WARNING: Do not add listings of sub-modules, documentation generation can do this,
   such lists must never be hand-maintained.

See :ref:`proxy-objects` for the lifetime semantics of entity proxies.

.. _live-values:

Live values
   A :class:`Point`, :class:`Size`, :class:`Rect`, :class:`ColorRGB` or
   :class:`ColorRGBA` read from a writable property is a live view of it:
   reading the value reads the property, and changing it (``point.x = 0``,
   ``point += (5, 0)``, ``rect.translate((5, 0))``, ``color[3] = 0.5``)
   assigns the whole value back, so the setter's checks apply. A view
   holds no value of its own; use ``copy()`` for one that keeps its value.
   A view can't be frozen or hashed, as its value can change; freeze a copy
   instead, as in ``d[rect.copy().freeze()] = v``.

   Snapshots
      A value read from a read-only property is a frozen snapshot, which
      refuses every change. So are a rectangle's corners
      (:attr:`Rect.min`, :attr:`Rect.max`, ``rect[0]`` and iteration): set
      a corner through the rectangle instead, as in ``rect.min = (0, 0)``.
   :attr:`Rect.size`
      A read-only view that follows the rectangle, as a size alone gives
      no corner to resize around; a frozen rectangle's size is a frozen
      snapshot.
   Own values
      A value that is constructed, copied or the result of arithmetic has
      its own value and can be changed. ``freeze()`` makes it a frozen,
      hashable value.
   ``owner``, ``is_valid`` and ``is_read_only``
      The object a view reads from, whether it can still be read, and
      whether the value refuses every change. A view whose owner is gone
      raises as the owner does, but its ``repr()`` still names the owner.
