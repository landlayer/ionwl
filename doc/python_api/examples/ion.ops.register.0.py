"""
**Custom Operator**

Register a custom operator with :func:`ion.ops.register` and bind it
to a key. The ``exec`` callback receives a NamedTuple whose fields are
declared at registration time via ``properties_type``, and an
:class:`~ion.types.Event` describing the input that triggered it.
A field's ``Annotated`` string is its description.
"""

import ion
from typing import Annotated, NamedTuple
from ion.types import Event, MatchKey, Rect
import ion.constants.keys as kbd
import ion.ops as ops


class ScratchToggleProperties(NamedTuple):
    name: Annotated[str, "Workspace to toggle."]


def _scratch_toggle_name(properties: ScratchToggleProperties) -> str:
    return 'Toggle Scratchpad'


def _scratch_toggle_exec(properties: ScratchToggleProperties, event: Event) -> None:
    ws_name = properties.name
    # Find or create the workspace, then toggle whether it floats.
    ws = ion.wm.workspaces.get(ws_name)
    if ws is None:
        # Center the floating workspace at 80 % of the active output.
        output = ion.wm.outputs.active_pointer
        assert output is not None
        r = output.rect
        w, h = int(r.size_x * 0.8), int(r.size_y * 0.8)
        cx, cy = r.center_floor()
        x, y = cx - w // 2, cy - h // 2
        ws = ion.wm.workspaces.new(Rect((x, y), (x + w, y + h)), ws_name)
    desktop = ion.wm.desktops.active
    if ws.is_floating:
        item = desktop.items_floating.find_by_workspace(ws)
        if item is not None:
            desktop.items_floating.remove(item)
    else:
        desktop.items_floating.add(ws)


ion.ops.register(
    "scratch_toggle",
    name=_scratch_toggle_name,
    exec=_scratch_toggle_exec,
    description="Toggle whether a named workspace floats.",
    properties_type=ScratchToggleProperties,
)

# Bind Logo+Space to toggle a scratchpad workspace.
ion.app.keymaps['global'].items.new(
    MatchKey(kbd.SPACE, logo=True),
    operator=ops.scratch_toggle(name="scratch"),  # type: ignore[attr-defined]
)
