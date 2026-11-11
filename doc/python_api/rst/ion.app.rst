This module is the configuration entry point. It hosts
both persistent application services - lifecycle and environment
functions plus dynamic data - and the declarative registries that the
config file populates and the compositor consults at runtime.

.. WARNING: Do not add listings of sub-modules, documentation generation can do this,
   such lists must never be hand-maintained.

When code runs
   Top-level config code runs at load time - that is where the
   declarative registries and preferences are populated. Live state in
   :mod:`ion.wm` only exists once the compositor is running, so window,
   frame, and workspace manipulation belongs in callbacks (keybindings,
   hooks, operator ``exec``) that fire later, not at config load.

Reloading
   The ``compositor_reload`` operator re-runs the config; one that calls
   ``ion_utils.config.reset_defaults()`` under its ``reload`` flag
   converges to exactly what it declares.

   A failed reload is not rolled back: the config keeps whatever it
   declared before raising. ``Super-R`` and ``Super-Q`` are then added
   unconditionally, without inspecting what survived, so a config that
   raised before declaring either still has a reload and a quit key.
   They go on the end of the ``global`` keymap, so a config that rebound
   those keys to something else before raising shadows them - unusual,
   and ``ionwl-cmd`` is the way back when it happens.

   A reload runs from a key or pointer binding, a menu item, a generator
   or ``ionwl-cmd``, and never from a hook callback (see below).

   The ``compositor_reload_pre`` hook fires before the config re-runs,
   with the callbacks the previous load attached, and
   ``compositor_reload_post`` fires after it, with the callbacks this
   load attached. A pre callback can capture state the reload clears for
   a post callback to restore, and a post callback can re-attach hooks
   watching state that outlives the reload, such as ``data`` on windows.
   A reset clears hooks before re-registering the built-in operators, so
   the built-ins' callbacks are always this load's.

   What survives a reload:

   The ``ion_init`` module's globals
      The module re-executes in its own namespace, so a global the
      previous load set is still there, which is how the config's
      ``reload`` flag detects a reload.

   Other modules
      Only ``ion_init`` re-executes. A module the config imports keeps
      its state unless the config reloads it itself
      (``importlib.reload``).

   Groups a reset skips
      ``reset_defaults()`` clears only the registries and preference
      groups its flags select. The rest keep what earlier loads and
      runtime calls declared.

   Startup-only preferences
      ``startup.use_xwayland``, and the ``XCURSOR`` environment child
      processes inherit, take effect only at startup, so a change
      applies after a restart. Other preference writes apply as the
      current callback returns.

   Windows and outputs
      Every window and output stays, with its ``data``. Unless the
      reset is passed ``desktops=False``, it merges the desktops into the
      active one, which keeps its name, layout and ``data``. Another
      desktop's floating frames and floating workspaces move onto it
      whole, keeping their ``data``, and its tiled windows move onto the
      active desktop's workspace for their output. That desktop and its
      tiled frames and workspaces are removed, with their ``data``. A
      workspace no desktop holds keeps its windows.

   Overlays
      The tree under :data:`ion.wm.overlay_root` stays as it is, with
      each overlay's ``data``.

   Generators
      Running modals (generators consuming input) are cancelled before
      the pre hook fires, other than one running the reload, as
      Ctrl-Alt-Escape does, so they end against the keymaps and
      operators they started with. Other generators keep running.

   One-shot setup
      :data:`is_init` is False while a reload re-runs the config, so
      setup gated on it (launching a bar, exporting the session
      environment) happens at startup only, and what it started keeps
      running.

Registries
   Hooks, operators, menus and keymaps are registries a config fills,
   each with its own rules for a repeat, a removal and a listing:

   :data:`ion.app.hooks`
      Each hook is a list of its callbacks, so one added twice runs
      twice. ``remove`` raises ``ValueError`` for a callback not
      attached, and ``clear()`` detaches every one.

   :mod:`ion.ops`
      ``register`` with an idname already registered replaces the
      operator, exiting the old one's ``lifetime``. ``unregister``
      returns whether there was one. ``ion.ops.__all__`` lists them.

   :data:`ion.app.menus`
      ``new`` with an idname already registered replaces the menu.
      ``remove`` raises ``KeyError`` for an unknown menu, and ``clear()``
      removes every one. The registry is a mapping.

   :data:`ion.app.keymaps`
      ``new`` raises ``ValueError`` for a name already registered, where
      ``ensure`` returns that keymap. ``remove`` raises ``ValueError``
      for a built-in keymap. The registry is a mapping.

Hook callbacks
   A hook fires in the middle of the operation that raised it, and the
   operation carries on once its callbacks return. That shapes what a
   callback can do:

   - It cannot cancel or alter the operation. Return values are ignored,
     so a ``*_pre`` hook is a notification, not a veto.
   - An exception is reported like any other callback error, and the
     remaining callbacks and the operation still run.
   - Causing the event it handles fires the same hook again, from inside
     the callback. Nothing suppresses the recursion.
   - The argument of a hook fired after a removal (``window_close_post``,
     ``workspace_delete_post``, ``desktop_remove_post``,
     ``output_remove_post``) names something already gone. Read what the
     callback needs in the matching ``*_pre`` hook.
   - It cannot reload the config: ``ion_utils.config.reload()`` and
     ``ion_utils.config.reset_defaults()`` raise ``RuntimeError``, and
     the ``compositor_reload`` operator's poll refuses it. A reset
     removes desktops the operation may still hold, and fires hooks the
     reloaded config registers again, so a reload from one of those
     would recurse.
