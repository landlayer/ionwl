########
Features
########

Feature Overview
================

Window Management
   - Tiling: Split-tree layout with interactive splitting and adjustable split axes.
   - Tabbed Frames: Frames hold windows as tabs, reordered by drag-and-drop.
   - Floating Windows: Windows detached from tiling, freely positioned and stacked.
   - Full Screen Windows: Per-output fullscreen with direct scanout.
   - Window Tagging: Tag windows, then gather them into one frame.
   - X11 Applications: Run through XWayland, enabled by default (see ``startup.use_xwayland``).
Workspaces and Desktops
   - Workspaces: Independent tiling trees, assigned per output.
   - Virtual Desktops: Multiple desktops, cycling occupied and empty.
   - Multiple Monitors: Per-output workspaces, moving items between outputs.
   - Scratchpad: Floating workspaces to be toggled on demand.
Navigation
   - Directional Focus: Vim-style focus and window movement between frames.
   - Overviews: Zoomed desktop and window overviews.
   - Window Switcher: A carousel for cycling windows.
Input
   - Configurable Keymaps: Layered keymaps bound from Python.
   - Focus Follows Pointer: Optional sloppy focus, and the pointer warped to a frame an operator focuses.
     The warp is the compositor's own; clients can't warp the pointer (pointer-warp-v1 is not supported).
   - Context Menus: Pointer-region menus and button bindings.
   - Dragging: Tabs, Floating Windows, Workspaces and Client Drag-and-Drop, across frames and desktops.
     A tablet pen can't start a drag, as its tip doesn't run pointer button bindings.
   - Modal Escape: ``Ctrl-Alt-Escape`` ends any interactive mode (overview, switcher, drag), whatever the keymaps bind.
Extensibility
   - Python API: Configured and scripted entirely in Python.
   - Operators and Hooks: Actions bound to keys or fired on events.
   - Config Reload: Live reload without restarting.
   - IPC: Run Python in the compositor with ``ionwl-cmd``.
Rendering
   - Multi-GPU: Automatic GPU detection.
   - VRR: Variable refresh rate for supported displays.
   - Direct scanout: Zero-copy rendering for full-screen applications.
   - Render threads: Per output threaded rendering to eliminate drawing contention across outputs.
Dragging
   - A MMB tab drag, from one frame's tab bar into another, or out of the tiling into a floating frame.
   - A floating frame or workspace can be dragged between desktops.
   - A client's own drag-and-drop, can be dragged between desktops too.
   - Drag delay can be tuned or disabled through :data:`ion.app.preferences.dnd`.

Wayland Protocols
=================

Core
   ``wl_compositor``, ``wl_subcompositor``, ``wl_shm``, ``wl_seat`` (keyboard,
   pointer, touch), ``wl_output`` with ``xdg-output``, and ``wl_data_device``
   for clipboard and drag-and-drop.
   ``wl_fixes`` lets a client destroy a ``wl_registry`` it no longer needs.

Shell and Window Management
---------------------------

xdg-shell
   The primary protocol for application windows.
xdg-decoration / kde-server-decoration
   Negotiate server-side vs client-side window borders.
xdg-activation
   Lets a client request focus for another window (used for launch feedback
   and click-to-activate).
xdg-foreign
   Export a surface so another client can position a window relative to it
   (dialogs across process boundaries).
xdg-toplevel-icon
   Per-window icons supplied by the client.
wlr-layer-shell
   Anchored surfaces for bars, panels, launchers, and wallpapers (waybar,
   tofi).
xwayland-shell
   Surface association for XWayland clients.

Output and Display
------------------

fractional-scale / viewporter
   Non-integer HiDPI scaling and buffer scaling/cropping.
linux-dmabuf
   Zero-copy GPU buffer sharing.
presentation-time
   Accurate frame-presentation feedback for clients.
single-pixel-buffer
   Solid-color buffers without a full allocation.
wlr-gamma-control
   Color-temperature adjustment (gammastep, wlsunset).
wlr-output-management
   External display configuration (kanshi, wlr-randr, nwg-displays).
wlr-output-power-management
   Display power control (wlopm).

Input
-----

relative-pointer / pointer-constraints
   Pointer locking and warp-free relative motion (games, 3D viewports).
cursor-shape
   Clients name a cursor from the theme instead of supplying a bitmap.
tablet
   Graphics-tablet input.
   Only clients that support the protocol receive pen input; the pen isn't emulated as a pointer for others.
virtual-keyboard
   Injected keyboard input (on-screen keyboards, IME, ``wtype``).
   Injected keys run key bindings like a physical keyboard's, except VT
   switching, which only a physical keyboard can do.
keyboard-shortcuts-inhibit
   Let a client (e.g. a nested compositor or remote-desktop viewer)
   capture compositor shortcuts.
idle-inhibit
   Clients suppress idle/screen-blanking (video players).

Clipboard and Selection
-----------------------

primary-selection
   Middle-click paste.
wlr-data-control / ext-data-control
   Clipboard managers read and set selections (``wl-clipboard``, ``clipman``).

Screen Capture and Session
--------------------------

wlr-screencopy
   Screenshots and screen recording (grim, wf-recorder).
wlr-foreign-toplevel-management
   Window lists for taskbars and docks.
   Maximize and minimize requests are ignored, and a window's parent is not
   reported.
ext-session-lock
   Secure screen lockers (swaylock, gtklock).

Not Yet Supported
-----------------

text-input / input-method
   Input-method editors for non-Latin scripts (fcitx5, ibus).
ext-idle-notify
   Idle detection for automatic screen locking (swayidle).
   The built-in idle timeout fires :attr:`ion.types.HooksRegistry.idle_lock` instead,
   which can run a locker.
ext-foreign-toplevel-list
   Read-only window lists, the newer counterpart of wlr-foreign-toplevel-management.
ext-image-copy-capture
   Screen and per-window capture, the newer counterpart of wlr-screencopy.
xdg-dialog-v1
   Marking a dialog modal to its parent window.
alpha-modifier
   Client-controlled surface opacity.
pointer-warp-v1
   Clients warping the pointer within their own surface.
xwayland-keyboard-grab
   Keyboard grabs for X11 clients (virtual machine and remote-desktop viewers).
pointer-gestures
   Touchpad swipe and pinch gestures reported to clients.
tearing-control
   Opt-in screen tearing for latency-sensitive fullscreen games.
security-context
   Sandbox identification, letting the compositor restrict privileged
   protocols per client (Flatpak).


Limitations
===========

- Output scale is global (no support for mixed output scaling).
