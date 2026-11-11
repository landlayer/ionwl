"""
**Context Menus**

Register context menus with :meth:`ion.types.MenuRegistry.new`. The
callback receives a :class:`ion.types.MenuBuilder` and populates its
:class:`ion.types.UILayout` (``menu.layout``) with operators, separators,
and sub-menus. Bind the menu to a pointer event with the built-in
``menu_show`` operator.
"""

import ion
from ion.types import MatchPointer, MenuBuilder
import ion.constants.pointer_buttons as btn
import ion.ops as ops


# Tab context menu - shown on right-click over a tab.
def _tab_menu(menu: MenuBuilder) -> None:
    layout = menu.layout
    layout.operator(ops.window_close())
    layout.operator(ops.frame_delete())
    layout.separator()
    layout.operator(ops.tag_set())
    layout.operator(ops.window_floating_set())


ion.app.menus.new('tab', "Tab", _tab_menu)


# Frame context menu with a nested sub-menu.
def _frame_menu(menu: MenuBuilder) -> None:
    layout = menu.layout
    layout.operator(ops.tiling_split(direction='RIGHT'))
    layout.operator(ops.tiling_split(direction='DOWN'))
    layout.operator(ops.tiling_split_axis_set())
    layout.separator()
    layout.menu(idname="root")


ion.app.menus.new('frame', "Frame", _frame_menu)


# Root sub-menu referenced by the frame menu above.
def _root_menu(menu: MenuBuilder) -> None:
    layout = menu.layout
    layout.operator(ops.workspace_new_tiling_on_desktop())
    layout.separator()
    layout.operator(ops.desktop_new())
    layout.operator(ops.desktop_delete())


ion.app.menus.new('root', "Root", _root_menu)


# Bind right-click on a tab to show the "tab" menu.
ion.app.keymaps['tab'].items.new(
    MatchPointer(btn.RIGHT),
    operator=ops.menu_show(idname="tab"),
)
