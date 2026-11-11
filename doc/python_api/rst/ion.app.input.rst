This module exposes the input devices the compositor currently knows about,
one collection per kind. Each collection is a live view: devices appear and
disappear as hardware is plugged and unplugged, so a device is looked up when
it is needed rather than stored at config load.

Device handles
   A device object is a handle that re-resolves on every access, not a
   snapshot. Holding one past the device's removal is safe - ``is_valid``
   reports the device is gone, and any other access raises. Two handles to
   one device compare equal and hash alike, so a device works as a
   dictionary key.

Looking a device up
   A collection is indexed by name, by zero-based index (negative indices
   count from the end), or by slice, which yields a tuple. ``active`` is the
   device that most recently produced input, which is the one to reach for
   when responding to an event.

   Names are unique within a collection: a device reporting a name already
   taken gets a ``.1``, ``.2`` ... suffix. Which of two identical devices
   gets it follows the order they were added, which can change between
   sessions; ``port_id`` tells them apart when they are plugged into
   different ports.

One seat
   Every device drives the same seat: there is one keyboard focus, one pointer
   and one clipboard for the session, whatever is plugged in. The collections
   enumerate devices rather than seats, so a second keyboard is another way to
   drive the one focus, not a focus of its own. The keyboard layout follows
   whichever device was last used, which is what ``active`` reports.

Settings and defaults
   Writing a setting on a device changes only that device. On the active
   device the change reaches the seat when the current callback returns; on
   any other it is stored and applied when that device next becomes active.
   The matching ``ion.app.preferences.input`` defaults apply to every device
   of that kind, and writing one discards the per-device values, so declare
   the defaults first and override individual devices after.

.. code-block:: python

   import ion

   for keyboard in ion.app.input.keyboards:
       print(keyboard.name, keyboard.layout)
