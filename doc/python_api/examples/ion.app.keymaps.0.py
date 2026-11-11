"""
**Basic Keybindings**

Set up keyboard and pointer bindings using :class:`ion.types.MatchKey` and
:class:`ion.types.MatchPointer`. Modifiers such as ``logo``, ``shift``, ``ctrl``
and ``alt`` can be combined freely.
"""

import ion
from ion.types import MatchKey, MatchPointer
import ion.constants.keys as kbd
import ion.constants.pointer_buttons as btn
import ion.constants.event_actions as act
import ion.ops as ops

km = ion.app.keymaps['global']

# Launch a terminal.
km.items.new(MatchKey(kbd.RETURN, logo=True),
             operator=ops.system_exec(command=("foot",)))

# Close the focused window (or remove frame if empty).
km.items.new(MatchKey(kbd.Q, logo=True), operator=ops.window_close())

# Toggle fullscreen.
km.items.new(MatchKey(kbd.F, logo=True), operator=ops.window_fullscreen_set())

# Vim-style focus navigation.
km.items.new(MatchKey(kbd.H, logo=True), operator=ops.tiling_focus_directional(direction="LEFT"))
km.items.new(MatchKey(kbd.J, logo=True), operator=ops.tiling_focus_directional(direction="DOWN"))
km.items.new(MatchKey(kbd.K, logo=True), operator=ops.tiling_focus_directional(direction="UP"))
km.items.new(MatchKey(kbd.L, logo=True), operator=ops.tiling_focus_directional(direction="RIGHT"))

# Move windows with Logo+Shift.
km.items.new(MatchKey(kbd.H, logo=True, shift=True), operator=ops.window_tiling_move_directional(direction="LEFT"))
km.items.new(MatchKey(kbd.L, logo=True, shift=True), operator=ops.window_tiling_move_directional(direction="RIGHT"))

# Tab cycling with Alt+Tab / Alt+Shift+Tab.
km.items.new(MatchKey(kbd.TAB, alt=True),
             operator=ops.frame_tab_cycle(direction=1))
km.items.new(MatchKey(kbd.TAB, alt=True, shift=True),
             operator=ops.frame_tab_cycle(direction=-1))

# Pointer: Logo+Right-click drag to move a floating window.
km.items.new(MatchPointer(btn.RIGHT, logo=True, action=act.PRESS),
             operator=ops.floating_move())

# Pointer: Logo+Left-click drag to resize a floating window.
km.items.new(MatchPointer(btn.LEFT, logo=True, action=act.PRESS),
             operator=ops.floating_resize())
