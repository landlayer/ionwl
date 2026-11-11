Modifier bitmask values - one bit per modifier. These are *not* used
by :class:`~ion.types.MatchKey` or :class:`~ion.types.MatchPointer`
(those take individual boolean kwargs). The bitmask values are for
direct comparison against ``event.modifiers`` inside operator
callbacks and hook handlers, where the raw modifier state is
available as a single integer.

``HYPER`` is held only where the keymap gives Hyper a modifier of its
own, as the xkb options ``caps:hyper`` and ``altwin:hyper_win`` do.
Where the keymap puts Hyper on Mod4 with Super (``hyper:mod4``) the two
cannot be told apart, and holding Hyper reads as ``LOGO``. The
``hyper`` argument of :class:`~ion.types.MatchKey` and
:class:`~ion.types.MatchPointer` behaves the same way.
