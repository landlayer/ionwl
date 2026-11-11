Event actions identify the input gesture matched by
:class:`~ion.types.MatchKey` and :class:`~ion.types.MatchPointer`,
passed as the ``action=`` kwarg. When omitted the default differs by
matcher: :class:`~ion.types.MatchKey` defaults to ``PRESS`` while
:class:`~ion.types.MatchPointer` defaults to ``CLICK``. Some actions
fire on raw key/button transitions, others are derived gestures
synthesised from press/release sequences - so a single physical press
can trigger several matchers.
The ``consume`` argument of :meth:`~ion.types.KeymapItemsCollection.new`
controls whether earlier matches suppress later ones.
