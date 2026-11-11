This module provides **operators** - named actions that
drive the compositor. Operators are bound to keys via
:mod:`ion.app` keymaps or called directly from Python callbacks.

Each operator is a ``NamedTuple`` class stored on :mod:`ion.ops`.
Calling the class creates an immutable operator *instance* with its
properties baked in - and it is that instance, never the class, that is
used: pass it to :meth:`~ion.types.KeymapItemsCollection.new` as
``operator=...``, or invoke it directly with ``instance.call(event)``.
Because a binding holds an instance, even parameterless operators need
empty parens.
Parameterized: ``ion.ops.tiling_split(direction="LEFT")``.
Parameterless: ``ion.ops.compositor_quit()``.

Called from inside a callback, ``instance.call(event)`` runs under that
callback's state and settles nothing itself: deferred work, relayout and
preference changes apply when the outer dispatch returns, or at a
generator's ``yield``. It returns ``False`` when poll refuses, ``None``
when exec passes the event through, and ``True`` once exec has run, even
if it returned ``False`` or raised.

Built-in operator names are prefixed by the entity they act on
(e.g. ``window_``, ``frame_``, ``workspace_``).

Custom operators can be defined with :func:`ion.ops.register` - the
operator provides an ``exec`` callback and an optional ``poll``
callback that controls when the operator is available.
