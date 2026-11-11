This module shows the transient UI the compositor draws itself: context
menus, messages and tooltips. Only one popup is shown at a time, and
:func:`popup_dismiss` takes down whichever is current.

Menus
   :func:`popup_menu` takes the entries directly, which suits a menu whose
   contents depend on what was clicked. A menu that is reused, or that
   wants a name to bind a key to, belongs in
   :class:`~ion.types.MenuRegistry` instead.

   Either way every operator is polled before the menu appears, so an entry
   whose operator refuses is drawn greyed rather than looking live and
   doing nothing when clicked. Build the entries unconditionally and let
   the poll decide what is available.

.. code-block:: python

   import ion

   ion.ui.popup_menu([
       ("Close", ion.ops.window_close()),
       ("Fullscreen", ion.ops.window_fullscreen_set()),
   ])
