"""
**Querying Runtime State**

The :mod:`ion.wm` module exposes live collections for windows,
workspaces, outputs, frames, and desktops. Each collection supports
iteration, indexing, ``len()``, and an ``active`` property.

These queries are typically used inside hook callbacks or operator
``exec`` functions.
"""

import ion


@ion.app.hooks.window_new_post.append
def on_window_new(window: ion.types.Window) -> None:
    print("New window:", window.title, window.app_id)
    print("Total windows:", len(ion.wm.windows))

    # Show which output received the window.
    for output in ion.wm.outputs:
        r = output.rect
        print(" ", output.name, r.min, r.size)

    # List workspaces on the active desktop.
    desktop = ion.wm.desktops.active
    for item in desktop.items_tiling:
        if isinstance(item, ion.types.DesktopItemTilingWorkspace):
            ws = item.workspace
            print("  Workspace:", ws.name, "frames:", len(ws.frames))
