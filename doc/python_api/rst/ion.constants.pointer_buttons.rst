Pointer button codes (Linux input event codes), passed as the first
argument to :class:`~ion.types.MatchPointer`. With the conventional
aliases ``import ion.constants.pointer_buttons as btn`` and
``import ion.constants.event_actions as act``, a binding reads
``MatchPointer(btn.LEFT, logo=True, action=act.PRESS)`` - the button
comes from this module while the ``action=`` value comes from
:mod:`ion.constants.event_actions`. The constructor takes an integer;
the alphabetic constants here exist to keep bindings readable.
