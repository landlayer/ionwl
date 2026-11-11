Symbolic constants for input matchers, raw event modifier checks and floating
resize edges. Constants are integers - keysyms and pointer buttons pass
directly to the input matchers in :mod:`ion.types`; modifier bitmasks are
intended for direct comparison against ``event.modifiers``, not for the
matchers' bool kwargs.
