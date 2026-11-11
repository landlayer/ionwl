Keysym constants accepted by :class:`~ion.types.MatchKey`.

:class:`~ion.types.MatchKey` accepts an integer keysym from this
module (``MatchKey(RETURN)``), or an xkb keysym name for a key this
module does not list (``MatchKey("Menu")``).
Modifier requirements are passed as boolean keyword arguments on
:class:`~ion.types.MatchKey`, e.g. ``MatchKey(RETURN, logo=True)``;
the raw modifier bitmasks for direct comparison against
``event.modifiers`` live in :mod:`ion.constants.modifiers`, not here.
