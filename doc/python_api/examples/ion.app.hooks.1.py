"""
**Startup Layout**

Use the ``compositor_startup_post`` hook to create desktops and
workspaces when the compositor starts. Desktop 0 always exists, so
only additional desktops need to be created explicitly.
"""

import ion
from ion.types import Rect


@ion.app.hooks.compositor_startup_post.append
def on_startup() -> None:
    # Desktop 0 already exists; create three more.
    desktops = [ion.wm.desktops[0]]
    for i in range(3):
        desktops.append(ion.wm.desktops.new(str(i + 2)))

    # Give each desktop a named workspace with a horizontal split.
    for i, desktop in enumerate(desktops):
        desktop.name = str(i + 1)
        ws = ion.wm.workspaces.new(Rect((0, 0), (800, 600)))
        desktop.items_tiling.add(ws)
        node = ws.frames[0].split_node
        assert node is not None
        node.split(0, 1)
