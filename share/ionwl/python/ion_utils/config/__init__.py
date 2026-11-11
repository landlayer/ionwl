# SPDX-License-Identifier: GPL-3.0-or-later

# Shared configuration helpers.

from __future__ import annotations

__all__ = (
    "fallback_bindings_setup",
    "reload",
    "reset_defaults",
    "setup_defaults",
    "setup_session",
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import ion


def _divider_at_edge(axis: int, frame_is_min_child: bool) -> ion.types.SplitNodeContainer | None:
    """Resolve the divider bordering the context frame on one edge.

    Walks up from the context frame to the nearest ancestor split on `axis` where
    the frame's subtree is that split's min or max child as given -- the divider
    owning that edge. Returns None when no divider lies that way (a layout edge).

    Reads `context.frame` (the focused frame, or a region's override) to match
    the other divider operators, which resolve their target through the context.
    """
    from ion.wm import context
    frame = context.frame
    if frame is None:
        return None
    current: ion.types.SplitNode | None = frame.split_node
    if current is None:
        return None
    while (parent := current.parent) is not None:
        if parent.split_axis == axis and (parent.child_min == current) == frame_is_min_child:
            return parent
        current = parent
    return None


def _hook_running_refuse(name: str) -> None:
    """Raise ``RuntimeError`` while a hook callback is running.

    See *Hook callbacks* in :mod:`ion.app` for why.
    """
    import ion
    if ion._internal.hook_running():
        raise RuntimeError("{:s}() can't run from a hook callback".format(name))


def reset_defaults(
        *,
        keymaps: bool = True,
        menus: bool = True,
        hooks: bool = True,
        operators: bool = True,
        looks: bool = True,
        preferences_cursor: bool = True,
        preferences_idle: bool = True,
        preferences_focus: bool = True,
        preferences_dnd: bool = True,
        preferences_floating: bool = True,
        preferences_tiling: bool = True,
        preferences_input: bool = True,
        preferences_fonts: bool = True,
        preferences_animate: bool = True,
        preferences_startup: bool = True,
        preferences_decor: bool = True,
        preferences_system: bool = True,
        desktops: bool = True,
) -> None:
    """
    Clear registries a reloading config is about to re-declare.

    Call from the config when its ``reload`` flag is set, before the
    declarations run. Each ``preferences_*`` flag resets one preference
    group to its defaults for the config to re-declare; the resets apply
    once the reload's dispatch returns.

    :param keymaps: Remove user-defined keymaps and clear the built-in
       keymaps' bindings, then re-create the keymaps the built-in operators
       use, empty. Removed keymaps vanish from Python immediately; the
       compositor frees them once idle.
    :param menus: Remove all menus.
    :param hooks: Detach all callbacks from every hook, including callbacks
       registered at runtime and those an operator's ``lifetime`` attached,
       which stay detached unless ``operators`` re-registers it.
    :param operators: Unregister all operators, then re-register the
       built-ins, which re-attach their hooks. Operators registered at
       runtime are removed; the config re-declares its own.
    :param looks: Reset window decorations (look and geometry) to the
       defaults, undoing changes applied at runtime (e.g. via the "Looks"
       menu).
    :param preferences_cursor: Reset :class:`~ion.types.CursorPreferences`.
    :param preferences_idle: Reset :class:`~ion.types.IdlePreferences`.
    :param preferences_focus: Reset :class:`~ion.types.FocusPreferences`.
    :param preferences_dnd: Reset :class:`~ion.types.DndPreferences`.
    :param preferences_floating: Reset :class:`~ion.types.FloatingPreferences`.
    :param preferences_tiling: Reset :class:`~ion.types.TilingPreferences`.
    :param preferences_input: Reset :class:`~ion.types.InputPreferences`. Input
       devices reset to the re-declared defaults even when those are unchanged,
       discarding per-device runtime overrides such as a keyboard's layout.
    :param preferences_fonts: Reset :class:`~ion.types.FontPreferences`.
    :param preferences_animate: Reset :class:`~ion.types.AnimatePreferences`.
    :param preferences_startup: Reset :class:`~ion.types.StartupPreferences`.
    :param preferences_decor: Reset :class:`~ion.types.DecorPreferences`.
    :param preferences_system: Reset :class:`~ion.types.SystemPreferences`.
    :param desktops: Merge every desktop into the active one, which keeps its
       name and layout, then remove the others. A tiled window from another
       desktop lands on the active desktop's workspace for the output it was
       already on, so a reset does not move windows between monitors.
       Floating windows and floating workspaces stay floating, keeping their
       stacking order, tab grouping and visibility. What the merge keeps is
       listed under *Reloading* in :mod:`ion.app`.
    :raises RuntimeError: When called from a hook callback (see :mod:`ion.app`).
    """
    import ion

    _hook_running_refuse("reset_defaults")

    if keymaps:
        import ion_utils.builtins

        registry = ion.app.keymaps
        for km in registry.values():
            # Always clear - no need to keep bindings, slight memory reduction.
            km.items.clear()
            if not km.is_builtin:
                registry.remove(km)
        # Re-created empty, as at startup.
        ion_utils.builtins.keymaps_ensure()

    if menus:
        ion.app.menus.clear()

    # Before the operators: registering a built-in attaches its hooks.
    if hooks:
        hooks_registry = ion.app.hooks
        for name in dir(hooks_registry):
            getattr(hooks_registry, name).clear()

    if operators:
        import ion_utils.builtins.operators

        # Unregister every operator - unregister() ignores non-operator
        # attributes - then restore the built-ins, as at startup.
        for idname in dir(ion.ops):
            ion.ops.unregister(idname)
        ion_utils.builtins.operators.register()

    if looks:
        ion.app.decor.look = ion.types.DecorLook()
        ion.app.decor.geom = ion.types.DecorGeom()

    prefs = ion.app.preferences
    if preferences_cursor:
        prefs.cursor.reset()
    if preferences_idle:
        prefs.idle.reset()
    if preferences_focus:
        prefs.focus.reset()
    if preferences_dnd:
        prefs.dnd.reset()
    if preferences_floating:
        prefs.floating.reset()
    if preferences_tiling:
        prefs.tiling.reset()
    if preferences_input:
        prefs.input.reset()
    if preferences_fonts:
        prefs.fonts.reset()
    if preferences_animate:
        prefs.animate.reset()
    if preferences_startup:
        prefs.startup.reset()
    if preferences_decor:
        prefs.decor.reset()
    if preferences_system:
        prefs.system.reset()

    # A first load runs before the startup seed, so there may be no desktop to
    # merge into yet.
    if desktops and len(ion.wm.desktops):
        wm = ion.wm
        # The active desktop stays, keeping its layout; the others merge into it.
        desktop = wm.desktops.active
        desktops_src = [d for d in wm.desktops if d != desktop]

        # A window moved into a frame becomes its visible tab, so each frame
        # gets back the tab it showed.
        tabs_active = []
        ws_fallback = None
        for item_tiling in desktop.items_tiling:
            assert isinstance(item_tiling, ion.types.DesktopItemTilingWorkspace)
            if ws_fallback is None:
                ws_fallback = item_tiling.workspace
            for frame in item_tiling.workspace.frames:
                if (window_active := frame.windows.active) is not None:
                    tabs_active.append((frame, window_active))

        for desktop_src in desktops_src:
            # Floating items move whole in z-order, keeping their state intact.
            for item in list(desktop_src.items_floating):
                item.move_to_desktop(desktop)

            # Tiled windows land on the workspace for the output they were
            # already on, so a reset does not drag windows across monitors. An
            # entry spanning every output has no single output and takes the
            # fallback.
            for item_src in list(desktop_src.items_tiling):
                assert isinstance(item_src, ion.types.DesktopItemTilingWorkspace)
                if (
                        (output := item_src.output) is not None
                        and (item_dst := desktop.items_tiling.find_by_output(output)) is not None
                ):
                    assert isinstance(item_dst, ion.types.DesktopItemTilingWorkspace)
                    ws_dst = item_dst.workspace
                else:
                    # Only a desktop with no tiled workspace, as without
                    # outputs, needs one created.
                    if ws_fallback is None:
                        ws_fallback = wm.workspaces.new(ion.types.Rect((0, 0), (800, 600)))
                        desktop.items_tiling.add(ws_fallback)
                    ws_dst = ws_fallback
                # Moves tiled windows; `move_to_tiling` would treat them as a
                # no-op, leaving the source desktop non-empty and unremovable.
                for window in list(item_src.workspace.windows):
                    window.move_to_workspace(ws_dst)

            wm.desktops.remove(desktop_src)

        # The focused frame's tab brings its window's focus back with it.
        for frame, window_active in tabs_active:
            if frame.windows.active != window_active:
                frame.windows.active = window_active


def reload() -> None:
    """
    Re-run the ``ion_init`` module.

    Clearing is the config's responsibility: a config that supports
    reloading calls :func:`reset_defaults` guarded by its ``reload``
    flag, so re-declaration converges instead of stacking duplicates.

    Reloading rewrites the keymap, menu, operator and hook registries.
    It runs from a key or pointer binding (the ``compositor_reload``
    builtin is the usual caller), a menu item, a generator or
    ``ionwl-cmd``, but not from a hook callback (see :mod:`ion.app`).

    Running modals (generators consuming input) are cancelled first; what a
    reload keeps and what it ends is listed under *Reloading* in
    :mod:`ion.app`.

    The ``compositor_reload_pre`` hook fires before the config re-runs,
    and ``compositor_reload_post`` after it, even when it raised.

    A session started without a config picks one up here, so writing
    ``ion_init.py`` and reloading works without a restart.

    A raise mid-reload is not rolled back: whatever the config
    re-declared before raising stays. :func:`fallback_bindings_setup`
    then adds a reload and a quit key, which recovers a config that
    raised before declaring either - see there for the case it misses.

    :raises RuntimeError: When called from a hook callback (see :mod:`ion.app`).
    """
    import importlib
    import os
    import sys
    import traceback

    import ion

    _hook_running_refuse("reload")

    module = sys.modules.get('ion_init')
    config_dir = ion.app.config_dir()
    if module is None and not os.path.isfile(os.path.join(config_dir, 'ion_init.py')):
        # Nothing to load and nothing broken: report it plainly rather than
        # through the failure path, which would notify and install emergency
        # bindings over a session that simply has no config.
        ion.utils.log("reload: no config in {:s}".format(config_dir))
        return

    # Modals end against the registries they started with, which the reload
    # replaces under them.
    ion._internal.generator_cancel_consuming()
    ion._internal.hook_invoke('compositor_reload_pre')
    try:
        if module is None:
            # Startup adds the config directory to `sys.path` only when there
            # was a config to import, so a first load from here supplies it.
            if config_dir not in sys.path:
                sys.path.append(config_dir)
            importlib.import_module('ion_init')
        else:
            importlib.reload(module)
    except Exception as ex:
        # A broken config may have cleared bindings and left most keys
        # dead: make the failure visible and the session recoverable.
        # The re-raise reports it, with the notes added here; a failure
        # installing the fallbacks must not eat it.
        try:
            fallback_bindings_setup()
        except Exception as fallback_ex:
            # Attached to the re-raised error rather than reported on its own:
            # that report's popup would be replaced at once by the re-raise's.
            ex.add_note("Installing the fallback bindings also failed:\n{:s}".format(
                "".join(traceback.format_exception(fallback_ex, chain=False)).rstrip(),
            ))
            message = "Reload failed - see log"
        else:
            hint = "Super-R reloads, Super-Q quits"
            ex.add_note("{:s}.".format(hint))
            message = "Reload failed - see log ({:s})".format(hint)
        # The report shows the failure in a popup, or to an IPC client;
        # without `notify_on_error`, a reload from a key press is only logged.
        if not ion.app.preferences.system.notify_on_error:
            ion.utils.notify(message, urgency='critical')
        raise
    finally:
        # A config that raised may have cleared hooks before it did.
        ion._internal.hook_invoke('compositor_reload_post')


def fallback_bindings_setup() -> None:
    """
    Install emergency bindings so a failed reload stays recoverable.

    ``Super-R`` reloads and ``Super-Q`` quits. Called whenever a reload
    raises, because a config that raised partway keeps only what it
    declared first - which need not include either.

    Added unconditionally, without inspecting what survived: the keys
    have to be there. A config that resets before raising clears them
    each time round; one that raises earlier can end up with duplicates,
    which cost nothing since the first match consumes the press. The
    next successful reload's :func:`reset_defaults` clears them.

    That last point is also the limit of what this guarantees. The
    bindings go on the end of ``global``, which is last in the cascade,
    and the first match consumes the press - so a binding the config
    declared on the same key wins and the fallback never runs. Reaching
    that needs a config that rebound ``Super-R`` away from reload before
    it raised; unusual, and ``ionwl-cmd`` covers it, so the keymap is
    left alone rather than clearing whatever holds those keys.

    :rtype: None
    """
    import ion
    import ion.constants.keys as kbd
    from ion import ops
    from ion.types import MatchKey

    km = ion.app.keymaps['global']
    km.items.new(MatchKey(kbd.R, logo=True), ops.compositor_reload())
    km.items.new(MatchKey(kbd.Q, logo=True), ops.compositor_quit())


def setup_session(*, dbus: bool = False, systemd: bool = False) -> None:
    """
    Export compositor environment to the session.

    :param dbus: Run ``dbus-update-activation-environment`` to update
       the D-Bus activation environment.
    :param systemd: Run ``systemctl --user import-environment`` to
       update the systemd user session.
    """
    import subprocess

    import ion

    env_vars = (
        'WAYLAND_DISPLAY',
        'XDG_CURRENT_DESKTOP',
        'XDG_SESSION_TYPE',
    )

    cmds: list[tuple[str, ...]] = []
    if systemd:
        cmds.append(('systemctl', '--user', 'import-environment', *env_vars))
    if dbus:
        cmds.append(('dbus-update-activation-environment', *env_vars))
    for cmd in cmds:
        try:
            subprocess.call(cmd)
        except Exception as ex:
            ion.utils.error_report("Session setup: {:s}".format(cmd[0]), ex)


def setup_defaults() -> None:
    """
    Set up default context menus and pointer bindings for built-in keymaps.

    This registers the standard context menus (tab, frame, root) and the
    pointer interactions that all configurations need: tab activation,
    context menu triggers, divider resize, and decoration grab.
    """
    import ion
    import ion.constants.event_actions as act
    import ion.constants.pointer_buttons as btn
    from ion import ops
    from ion.types import MatchPointer

    # Context menus.
    def _tab_menu(menu: ion.types.MenuBuilder) -> None:
        layout = menu.layout
        layout.operator(ops.window_close())
        layout.operator(ops.window_kill())
        layout.operator(ops.frame_delete())
        layout.operator(ops.tag_set())
        layout.operator(ops.tag_attach())
        layout.operator(ops.window_floating_set())
        layout.operator(ops.floating_depth_to_front())
        layout.operator(ops.floating_depth_to_back())
        layout.separator()
        layout.menu(idname='frame')

    ion.app.menus.new('tab', 'Tab', _tab_menu)

    def _frame_menu(menu: ion.types.MenuBuilder) -> None:
        layout = menu.layout
        layout.operator(ops.frame_join())
        layout.operator(ops.tiling_split(direction='RIGHT'))
        layout.operator(ops.tiling_split(direction='DOWN'))
        layout.operator(ops.tiling_split_axis_set())
        layout.operator(ops.tiling_split_axis_set(parent_depth=-1))
        layout.operator(ops.frame_untile())
        layout.operator(ops.workspace_untile())
        layout.operator(ops.frame_tile())
        layout.operator(ops.window_floating_set())
        layout.separator()
        layout.menu(idname='dividers')
        layout.menu(idname='root')

    ion.app.menus.new('frame', 'Frame', _frame_menu)

    def _divider_menu(menu: ion.types.MenuBuilder) -> None:
        layout = menu.layout
        layout.operator(ops.tiling_split_axis_rotate(angle=90, pointer_warp=False))
        layout.operator(ops.tiling_split_axis_rotate(angle=270, pointer_warp=False))
        layout.operator(ops.tiling_swap(pointer_warp=False))
        layout.operator(ops.tiling_divider_gapless_set())
        layout.operator(ops.tiling_divider_gapless_set(mode=2))
        layout.operator(ops.frame_join())
        layout.operator(ops.tiling_split(direction='RIGHT'))
        layout.operator(ops.tiling_split(direction='DOWN'))

    ion.app.menus.new('divider', 'Divider', _divider_menu)

    # Directional divider submenus. Each resolves the divider bordering the
    # active frame on its edge and draws the ordinary divider menu inside a
    # `layout.context_store(split=...)`, so its items run as if invoked over
    # that divider -- this is how a gapless divider (which has no pointer
    # target) stays reachable from the frame menu. Each edge greys out when no
    # divider lies that way, and the parent `dividers` menu greys out when none
    # do.
    #
    # Each edge: menu id, label, the bordering split's axis (0 horizontal, 1
    # vertical), and whether the focused frame is that split's min child (true
    # when the neighbor lies towards max, so Right and Below; Left and Above
    # face min).
    divider_edges = (
        ('divider_left', 'Left', 0, False),
        ('divider_right', 'Right', 0, True),
        ('divider_up', 'Above', 1, False),
        ('divider_down', 'Below', 1, True),
    )

    def _divider_edge_register(idname: str, label: str, axis: int, frame_is_min_child: bool) -> None:
        # `build`/`poll` close over the edge via this function's parameters, so
        # each registration binds its own edge (a plain loop body would share
        # the last value).
        def build(menu: ion.types.MenuBuilder) -> None:
            divider = _divider_at_edge(axis, frame_is_min_child)
            if divider is not None:
                with menu.layout.context_store(split=divider):
                    _divider_menu(menu)

        def poll() -> str | None:
            if _divider_at_edge(axis, frame_is_min_child) is None:
                return 'No divider on this edge'
            return None

        ion.app.menus.new(idname, label, build, poll=poll)

    for _edge in divider_edges:
        _divider_edge_register(*_edge)

    def _dividers_menu(menu: ion.types.MenuBuilder) -> None:
        layout = menu.layout
        for idname, _, _, _ in divider_edges:
            layout.menu(idname=idname)

    def _dividers_poll() -> str | None:
        for _, _, axis, frame_is_min_child in divider_edges:
            if _divider_at_edge(axis, frame_is_min_child) is not None:
                return None
        return 'No adjacent dividers'

    ion.app.menus.new('dividers', 'Dividers', _dividers_menu, poll=_dividers_poll)

    def _looks_menu(menu: ion.types.MenuBuilder) -> None:
        import os
        import urllib.parse
        layout = menu.layout
        looks_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', '..', 'resources', 'looks')
        looks_dir = os.path.realpath(looks_dir)
        try:
            entries = sorted(os.scandir(looks_dir), key=lambda e: e.name)
        except OSError as ex:
            ion.utils.notify(
                "Looks menu: cannot list {:s}: {:s}".format(looks_dir, ex.strerror or str(ex)),
                urgency='critical',
            )
            return
        for entry in entries:
            filename = entry.name
            if filename.startswith(('.', '_')):
                continue
            if not entry.is_file():
                continue
            if not filename.endswith('.py'):
                continue

            name = urllib.parse.unquote(os.path.splitext(filename)[0])
            layout.operator(ops.python_exec(filepath=entry.path), text=name)

    ion.app.menus.new('looks', 'Looks', _looks_menu)

    def _root_menu(menu: ion.types.MenuBuilder) -> None:
        layout = menu.layout
        layout.operator(ops.workspace_new_tiling_on_desktop())
        layout.operator(ops.workspace_new_tiling_on_output())
        layout.operator(ops.workspace_new_floating())
        layout.separator()
        layout.operator(ops.workspace_tile_on_desktop())
        layout.operator(ops.workspace_tile_on_output())
        layout.separator()
        layout.operator(ops.desktop_new())
        layout.operator(ops.desktop_delete())
        layout.separator()
        layout.menu(idname='looks')
        layout.separator()
        layout.operator(ops.compositor_reload(), text='Reload Config')

    ion.app.menus.new('root', 'Root', _root_menu)

    # Pointer bindings for built-in keymaps.
    # Don't consume the press, to allow dragging, we could activate on "release",
    # but this results in a noticeable lag/delay.
    ion.app.keymaps['tab'].items.new(
        MatchPointer(btn.LEFT, action=act.PRESS),
        ops.frame_tab_activate(),
        consume=False,
    )
    ion.app.keymaps['tab'].items.new(MatchPointer(btn.MIDDLE, action=act.DRAG), ops.frame_tab_drag())
    ion.app.keymaps['tab'].items.new(MatchPointer(btn.RIGHT, action=act.PRESS), ops.menu_show(idname='tab'))
    ion.app.keymaps['title'].items.new(MatchPointer(btn.RIGHT, action=act.PRESS), ops.menu_show(idname='frame'))
    ion.app.keymaps['root'].items.new(MatchPointer(btn.RIGHT, action=act.PRESS), ops.menu_show(idname='root'))
    ion.app.keymaps['divider'].items.new(MatchPointer(btn.LEFT, action=act.PRESS), ops.tiling_divider_resize())
    ion.app.keymaps['divider'].items.new(MatchPointer(btn.RIGHT, action=act.PRESS), ops.menu_show(idname='divider'))
    ion.app.keymaps['decoration'].items.new(MatchPointer(btn.LEFT, action=act.DRAG), ops.floating_move())
    ion.app.keymaps['border'].items.new(MatchPointer(btn.LEFT, action=act.DRAG), ops.floating_resize(border=True))

    # Floating window move/resize (Super+pointer).
    # No-op Press suppresses the event reaching the client without
    # consuming Click/Drag evaluation for the same button.
    ion.app.keymaps['global'].items.new(
        MatchPointer(btn.RIGHT, logo=True, action=act.PRESS),
        ops.system_noop(),
        consume=False,
    )
    ion.app.keymaps['global'].items.new(
        MatchPointer(btn.RIGHT, logo=True, action=act.DRAG), ops.floating_move(),
    )
    ion.app.keymaps['global'].items.new(
        MatchPointer(btn.LEFT, logo=True, action=act.PRESS),
        ops.system_noop(),
        consume=False,
    )
    ion.app.keymaps['global'].items.new(
        MatchPointer(btn.LEFT, logo=True, action=act.DRAG), ops.floating_resize(),
    )

    # Floating window raise/lower (Super+pointer click).
    ion.app.keymaps['global'].items.new(
        MatchPointer(btn.RIGHT, logo=True, action=act.CLICK), ops.floating_raise(),
    )
    ion.app.keymaps['global'].items.new(
        MatchPointer(btn.MIDDLE, logo=True, action=act.CLICK), ops.floating_lower(),
    )
