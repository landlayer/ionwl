# SPDX-License-Identifier: GPL-3.0-or-later

# IonWL sample configuration.
#
# Copy this file to ~/.config/ionwl/ion_init.py and customize as needed.

# Only needed for Python < 3.14.
from __future__ import annotations

__all__ = (
    "main",
)

import ion
from ion.app import preferences as prefs
from ion.types import MatchKey
import ion.constants.keys as kbd
import ion.ops as ops
import ion_utils.config

# True when this module is being reloaded.
reload = "main" in locals()

# -----------------------------------------------------------------------------
# Settings

TERMINAL = ('foot',)
LAUNCHER = ('tofi-drun', '--drun-launch=true')


def main() -> None:
    '''Apply preferences and declare keymaps and menus.'''

    if reload:
        ion_utils.config.reset_defaults(desktops=False)

    # -------------------------------------------------------------------------
    # Preferences

    prefs.fonts.titlebar_font.face = 'DejaVu Sans:size=11:weight=bold'

    # -------------------------------------------------------------------------
    # Keymaps

    km_global = ion.app.keymaps['global']
    km_tiling = ion.app.keymaps['tiling']
    km_floating = ion.app.keymaps['floating']
    km_window = ion.app.keymaps['window']
    km_fullscreen = ion.app.keymaps['fullscreen']

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
    km_fullscreen.items.new(MatchKey(kbd.F, logo=True), ops.window_fullscreen_set())

    # Toggle floating (detach/reattach).
    km_window.items.new(MatchKey(kbd.X, logo=True), ops.window_floating_set())

    # Toggle tag on current window.
    km_window.items.new(MatchKey(kbd.T, logo=True), ops.tag_set())

    # Attach tagged windows to current frame.
    for km in (km_tiling, km_floating):
        km.items.new(MatchKey(kbd.A, logo=True), ops.tag_attach())

    # -------------------------------------------------------------------------
    # Launchers

    # Terminal.
    km_global.items.new(MatchKey(kbd.RETURN, logo=True), ops.system_exec(command=TERMINAL))

    # App launcher.
    km_global.items.new(MatchKey(kbd.P, logo=True), ops.system_exec(command=LAUNCHER))

    # -------------------------------------------------------------------------
    # Compositor control

    # Logout (graceful): close all windows, exit when none remain.
    km_global.items.new(MatchKey(kbd.Q, logo=True, shift=True), ops.compositor_logout())

    # Exit (force): quit immediately without closing windows.
    km_global.items.new(MatchKey(kbd.Q, logo=True, shift=True, ctrl=True), ops.compositor_quit())

    # Reload config.
    km_global.items.new(MatchKey(kbd.R, logo=True, shift=True), ops.compositor_reload())


main()
