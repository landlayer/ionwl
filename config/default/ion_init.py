# SPDX-License-Identifier: GPL-3.0-or-later

# IonWL sample configuration.
#
# Copy this file to ~/.config/ionwl/ion_init.py and customize as needed.
#
# This config uses VIM-style navigation.

# Only needed for Python < 3.14.
from __future__ import annotations

__all__ = (
    "main",
)

import ion
from ion.app import preferences as prefs
from ion.types import MatchKey, MatchPointer
import ion.constants.keys as kbd
import ion.constants.pointer_buttons as btn
import ion.constants.event_actions as act
import ion.ops as ops
import ion_utils.config

# True when this module is being reloaded.
reload = "main" in locals()

# -----------------------------------------------------------------------------
# Settings

TERMINAL = ('foot',)
LAUNCHER = ('tofi-drun', '--drun-launch=true')
SCRATCHPAD = '*scratch*'  # Workspace used as a scratchpad.


def main() -> None:
    '''Apply preferences and declare keymaps, menus and hooks.'''

    if reload:
        ion_utils.config.reset_defaults(desktops=False)

    # -------------------------------------------------------------------------
    # Preferences

    # Enable numlock on startup.
    prefs.startup.use_numlock = True

    # Enable sloppy focus (focus follows mouse).
    prefs.focus.pointer_follow = True

    # Warp pointer to frame on directional focus.
    prefs.focus.pointer_warp = True
    prefs.focus.pointer_warp_factor = (0.5, 0.5)  # Centered.
    prefs.focus.pointer_warp_margin = 5

    # Key repeat: 40 Hz, 200ms delay.
    prefs.input.keyboard_defaults.repeat_rate = 40
    prefs.input.keyboard_defaults.repeat_delay = 200

    # Python errors show in a popup with their traceback; uncomment to only
    # log them.
    # prefs.system.notify_on_error = False

    # Cursor size.
    prefs.cursor.size = 48

    # Font settings.
    prefs.fonts.titlebar_font.face = 'DejaVu Sans:size=11:weight=bold'

    # -------------------------------------------------------------------------
    # Keymaps

    km_global = ion.app.keymaps['global']
    km_tiling = ion.app.keymaps['tiling']
    km_floating = ion.app.keymaps['floating']
    km_window = ion.app.keymaps['window']
    km_fullscreen = ion.app.keymaps['fullscreen']

    # -------------------------------------------------------------------------
    # Startup

    @ion.app.hooks.compositor_startup_post.append
    def on_startup() -> None:
        '''Create 4 desktops with a horizontal split, start background services.'''
        # Desktop 0 already exists, create 3 more.
        desktops = [ion.wm.desktops[0]]
        for i in range(3):
            desktops.append(ion.wm.desktops.new(str(i + 1)))

        # Give each desktop a workspace with a horizontal split.
        for i, desktop in enumerate(desktops):
            desktop.name = str(i + 1)
            ws = ion.wm.workspaces.new(ion.types.Rect((0, 0), (800, 600)))
            desktop.items_tiling.add(ws)
            node = ws.frames[0].split_node
            assert node is not None
            node.split(0, 1)

        ion_utils.config.setup_session(dbus=True, systemd=True)

        ion.utils.exec(('mako',))

    # -------------------------------------------------------------------------
    # Context menus and pointer bindings

    ion_utils.config.setup_defaults()

    # -------------------------------------------------------------------------
    # Window management

    # Close window, or join frame if no window focused.
    for km in (km_window, km_tiling):
        km.items.new(MatchKey(kbd.Q, logo=True), ops.window_close(delete_empty_frame=True, delete_empty_workspace=True))

    # Toggle fullscreen.
    km_window.items.new(MatchKey(kbd.F, logo=True), ops.window_fullscreen_set())

    # Toggle fullscreen spanning all outputs.
    km_window.items.new(MatchKey(kbd.F, logo=True, shift=True), ops.window_fullscreen_all_set(name='*fullscreen*'))

    # Toggle floating (detach/reattach).
    km_window.items.new(MatchKey(kbd.X, logo=True), ops.window_floating_set())

    # Toggle tag on current window.
    km_window.items.new(MatchKey(kbd.T, logo=True), ops.tag_set())

    # Attach tagged windows to current frame.
    for km in (km_tiling, km_floating):
        km.items.new(MatchKey(kbd.A, logo=True), ops.tag_attach())

    # -------------------------------------------------------------------------
    # Fullscreen overrides (block operations that don't apply in fullscreen)

    # Exit fullscreen.
    km_fullscreen.items.new(MatchKey(kbd.F, logo=True), ops.window_fullscreen_set())

    # Block tiling move (vim-style).
    km_fullscreen.items.new(MatchKey(kbd.H, logo=True, shift=True), ops.system_noop())
    km_fullscreen.items.new(MatchKey(kbd.J, logo=True, shift=True), ops.system_noop())
    km_fullscreen.items.new(MatchKey(kbd.K, logo=True, shift=True), ops.system_noop())
    km_fullscreen.items.new(MatchKey(kbd.L, logo=True, shift=True), ops.system_noop())

    # -------------------------------------------------------------------------
    # Tab cycling within frame

    # Alt+Tab - next tab.
    km_window.items.new(MatchKey(kbd.TAB, alt=True), ops.frame_tab_cycle(direction=1))

    # Alt+Shift+Tab - previous tab.
    km_window.items.new(MatchKey(kbd.TAB, alt=True, shift=True), ops.frame_tab_cycle(direction=-1))

    # -------------------------------------------------------------------------
    # Tiling navigation (vim-style)

    km_global.items.new(MatchKey(kbd.H, logo=True), ops.tiling_focus_directional(direction='LEFT'))
    km_global.items.new(MatchKey(kbd.J, logo=True), ops.tiling_focus_directional(direction='DOWN'))
    km_global.items.new(MatchKey(kbd.K, logo=True), ops.tiling_focus_directional(direction='UP'))
    km_global.items.new(MatchKey(kbd.L, logo=True), ops.tiling_focus_directional(direction='RIGHT'))

    # -------------------------------------------------------------------------
    # Moving windows between frames (vim-style)

    km_tiling.items.new(MatchKey(kbd.H, logo=True, shift=True), ops.window_tiling_move_directional(direction='LEFT'))
    km_tiling.items.new(MatchKey(kbd.J, logo=True, shift=True), ops.window_tiling_move_directional(direction='DOWN'))
    km_tiling.items.new(MatchKey(kbd.K, logo=True, shift=True), ops.window_tiling_move_directional(direction='UP'))
    km_tiling.items.new(MatchKey(kbd.L, logo=True, shift=True), ops.window_tiling_move_directional(direction='RIGHT'))

    # -------------------------------------------------------------------------
    # Splitting frames

    # Split horizontal (new frame to the right) - backslash key.
    km_tiling.items.new(MatchKey(kbd.BACK_SLASH, logo=True), ops.tiling_split(direction='RIGHT'))

    # Split vertical (new frame below).
    km_tiling.items.new(MatchKey(kbd.BACK_SLASH, logo=True, shift=True), ops.tiling_split(direction='DOWN'))

    # Join frame with sibling, moving windows.
    km_tiling.items.new(MatchKey(kbd.X, logo=True, shift=True), ops.frame_join())

    # -------------------------------------------------------------------------
    # Layout manipulation

    # Move focused item to the next output (wraps back to the left).
    km_global.items.new(MatchKey(kbd.Z, logo=True), ops.output_move_directional(direction='RIGHT'))

    # Toggle split axis at current frame.
    km_tiling.items.new(MatchKey(kbd.Z, logo=True, shift=True), ops.tiling_split_axis_set())

    # Toggle split axis at workspace root.
    km_tiling.items.new(MatchKey(kbd.Z, logo=True, ctrl=True), ops.tiling_split_axis_set(parent_depth=-1))

    # -------------------------------------------------------------------------
    # Launchers

    # Terminal.
    km_global.items.new(MatchKey(kbd.RETURN, logo=True), ops.system_exec(command=TERMINAL))

    # App launcher.
    km_global.items.new(MatchKey(kbd.P, logo=True), ops.system_exec(command=LAUNCHER))

    # -------------------------------------------------------------------------
    # Floating workspace (scratch)

    km_global.items.new(MatchKey(kbd.SPACE, logo=True), ops.workspace_floating_set(name=SCRATCHPAD))
    km_window.items.new(MatchKey(kbd.W, logo=True), ops.window_workspace_push(name=SCRATCHPAD))
    km_global.items.new(MatchKey(kbd.W, logo=True, shift=True), ops.window_workspace_pop(name=SCRATCHPAD))

    # -------------------------------------------------------------------------
    # Compositor control

    # Logout (graceful): close all windows, exit when none remain.
    km_global.items.new(MatchKey(kbd.Q, logo=True, shift=True), ops.compositor_logout())

    # Exit (force): quit immediately without closing windows.
    km_global.items.new(MatchKey(kbd.Q, logo=True, shift=True, ctrl=True), ops.compositor_quit())

    # Reload config.
    km_global.items.new(MatchKey(kbd.R, logo=True, shift=True), ops.compositor_reload())

    # -------------------------------------------------------------------------
    # Workspace cycling

    # Cycle to next/previous occupied desktop.
    km_global.items.new(MatchKey(kbd.M, logo=True), ops.desktop_focus_occupied_cycle(direction=1))
    km_global.items.new(MatchKey(kbd.COMMA, logo=True), ops.desktop_focus_occupied_cycle(direction=-1))

    # Cycle to next empty desktop.
    km_global.items.new(MatchKey(kbd.RETURN, logo=True, ctrl=True), ops.desktop_focus_empty_cycle(direction=1))

    # Window carousel.
    km = ion.app.keymaps['window_carousel']
    km.items.new(MatchKey(kbd.RETURN, action=act.CLICK), ops.window_carousel_confirm())
    km.items.new(MatchKey(kbd.ESCAPE, action=act.CLICK), ops.window_carousel_cancel())
    km.items.new(MatchPointer(btn.LEFT, action=act.CLICK), ops.window_carousel_cancel())

    km_global.items.new(MatchKey(kbd.TAB, logo=True, ctrl=True), ops.window_cycle_carousel(keymap=km.name))

    # Desktop item carousel.
    km = ion.app.keymaps['desktop_item_carousel']
    km.items.new(MatchKey(kbd.RETURN, action=act.CLICK), ops.desktop_item_carousel_confirm())
    km.items.new(MatchKey(kbd.ESCAPE, action=act.CLICK), ops.desktop_item_carousel_cancel())
    km.items.new(MatchPointer(btn.LEFT, action=act.CLICK), ops.desktop_item_carousel_cancel())

    km_global.items.new(
        MatchKey(kbd.TAB, logo=True, alt=True),
        ops.desktop_item_cycle_carousel(keymap=km.name),
    )

    # Window switcher, confirmed once Logo is released.
    km = ion.app.keymaps['window_switcher']
    km.items.new(MatchKey(kbd.TAB, logo=None), ops.window_switcher_next())
    km.items.new(MatchKey(kbd.TAB, logo=None, shift=True), ops.window_switcher_prev())
    km.items.new(MatchKey(kbd.ESCAPE, action=act.CLICK), ops.window_switcher_cancel())

    km_global.items.new(MatchKey(kbd.TAB, logo=True), ops.window_switcher(keymap=km.name, direction=1))
    km_global.items.new(
        MatchKey(kbd.TAB, logo=True, shift=True),
        ops.window_switcher(keymap=km.name, direction=-1),
    )

    # Desktop overview on logo key click.
    km = ion.app.keymaps['desktop_overview']
    km.items.new(MatchKey(kbd.H), ops.desktop_overview_navigate(direction='LEFT'))
    km.items.new(MatchKey(kbd.J), ops.desktop_overview_navigate(direction='DOWN'))
    km.items.new(MatchKey(kbd.K), ops.desktop_overview_navigate(direction='UP'))
    km.items.new(MatchKey(kbd.L), ops.desktop_overview_navigate(direction='RIGHT'))
    km.items.new(MatchKey(kbd.RETURN, action=act.CLICK), ops.desktop_overview_confirm())
    km.items.new(MatchKey(kbd.ESCAPE, action=act.CLICK), ops.desktop_overview_cancel())
    km.items.new(MatchPointer(btn.LEFT, action=act.CLICK), ops.desktop_overview_select())

    for key in (kbd.LOGO_L, kbd.LOGO_R):
        km_global.items.new(
            MatchKey(key, action=act.CLICK),
            ops.desktop_overview(keymap=km.name, trim_empty=True),
        )

    # Window overview.
    km = ion.app.keymaps['window_overview']
    km.items.new(MatchKey(kbd.H), ops.window_overview_navigate(direction='LEFT'))
    km.items.new(MatchKey(kbd.J), ops.window_overview_navigate(direction='DOWN'))
    km.items.new(MatchKey(kbd.K), ops.window_overview_navigate(direction='UP'))
    km.items.new(MatchKey(kbd.L), ops.window_overview_navigate(direction='RIGHT'))
    km.items.new(MatchKey(kbd.RETURN, action=act.CLICK), ops.window_overview_confirm())
    km.items.new(MatchKey(kbd.ESCAPE, action=act.CLICK), ops.window_overview_cancel())
    km.items.new(MatchPointer(btn.LEFT, action=act.CLICK), ops.window_overview_select())

    km_global.items.new(MatchKey(kbd.Y, logo=True), ops.window_overview(keymap=km.name))

    # -------------------------------------------------------------------------
    # Media keys

    km_global.items.new(
        MatchKey(kbd.XF86_AUDIO_RAISE_VOLUME),
        ops.system_exec(command=('wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', '5%+')),
    )
    km_global.items.new(
        MatchKey(kbd.XF86_AUDIO_LOWER_VOLUME),
        ops.system_exec(command=('wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', '5%-')),
    )
    km_global.items.new(MatchKey(kbd.XF86_AUDIO_PLAY), ops.system_exec(command=('cmus-remote', '--pause')))
    km_global.items.new(MatchKey(kbd.XF86_AUDIO_PREV), ops.system_exec(command=('cmus-remote', '--prev')))
    km_global.items.new(MatchKey(kbd.XF86_AUDIO_NEXT), ops.system_exec(command=('cmus-remote', '--next')))
    km_global.items.new(MatchKey(kbd.XF86_AUDIO_REWIND), ops.system_exec(command=('cmus-remote', '--seek', '-10')))
    km_global.items.new(MatchKey(kbd.XF86_AUDIO_FORWARD), ops.system_exec(command=('cmus-remote', '--seek', '+10')))

    ion.utils.log('Config loaded')


main()
