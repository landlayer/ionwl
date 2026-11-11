# SPDX-License-Identifier: GPL-3.0-or-later

# Generic UI layout that collects GUI elements (operators, separators,
# submenus). Used by the menu system to gather a menu's items; kept independent
# of menus so it can back other layouts in the future.

from __future__ import annotations

__all__ = (
    "UILayout",
)

from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ion.types import (
        ContextSnapshot,
        Desktop,
        Frame,
        Output,
        SplitNodeContainer,
        Window,
        Workspace,
    )


class UILayout:
    """Collects the GUI elements of a container such as a menu.

    Elements are added through the layout, for example ``menu.layout.operator(...)``.
    Wrap additions in :meth:`context_store` to store the context an operator
    should act on when it runs, e.g. a divider a menu item targets.

    .. code-block:: python

       def my_menu(menu):
           layout = menu.layout
           layout.operator(ion.ops.window_close())
           # Pin a divider resolved elsewhere (e.g. the one bordering the
           # focused frame) so the operator acts on it even though it is not
           # under the pointer -- the reason `context_store` exists.
           with layout.context_store(split=target_divider):
               layout.operator(ion.ops.tiling_swap())
           layout.separator()
           layout.menu("submenu_id")
    """

    __slots__ = ("_context_overrides", "_items")

    def __init__(self) -> None:
        self._items: list[tuple[object, ...]] = []
        # Stack of context-override dicts pushed by `context_store`, each mapping
        # context attribute names to proxy objects. Merged (inner wins) and
        # stored on each operator so it targets those elements when it executes.
        self._context_overrides: list[dict[str, Any]] = []

    def operator(self, operator: tuple[object, ...], /, *, text: str | None = None) -> None:
        """Add an operator action item.

        The label defaults to the operator's name. Use ``text`` to override.

        .. code-block:: python

           menu.layout.operator(ion.ops.window_close())
           menu.layout.operator(ion.ops.tiling_split(direction='RIGHT'), text="Split Right")

        :param operator: NamedTuple instance (from ``ion.ops.*(...)``).
        :type operator: NamedTuple
        :param text: Optional override for the item label.
        :type text: str | None
        :rtype: None
        """
        cls = type(operator)
        idname: str = cls._ion_operator_id  # type: ignore[attr-defined]
        if text is not None:
            label = text
        else:
            label = cls._ion_name(operator)  # type: ignore[attr-defined]
        props = operator._asdict()  # type: ignore[attr-defined]
        self._items.append(("operator", label, idname, props, self._context_snapshot()))

    def menu(self, idname: str) -> None:
        """Add a submenu reference item.

        The display label is taken from the referenced menu's name.

        .. code-block:: python

           menu.layout.menu("my_submenu")

        :param idname: Menu identifier to reference.
        :type idname: str
        :rtype: None
        """
        self._items.append(("submenu", "", idname))

    def separator(self) -> None:
        """Add a visual separator line.

        :rtype: None
        """
        self._items.append(("separator",))

    def context_store(
            self,
            *,
            window: Window | None = None,
            frame: Frame | None = None,
            split: SplitNodeContainer | None = None,
            output: Output | None = None,
            workspace: Workspace | None = None,
            desktop: Desktop | None = None,
    ) -> AbstractContextManager[UILayout]:
        """Store context values for operators added within the block.

        Unlike overriding the live context, this records the values and pins
        them to each operator added inside the ``with`` block; the operator
        targets them when it runs, after the menu has closed. Each attribute
        left ``None`` keeps the value from any enclosing block or the region's
        context. Stores nest.

        .. code-block:: python

           with menu.layout.context_store(split=divider):
               menu.layout.operator(ion.ops.tiling_swap())

        :param window: The window operators in the block should act on.
        :type window: :class:`ion.types.Window` | None
        :param frame: The frame operators in the block should act on.
        :type frame: :class:`ion.types.Frame` | None
        :param split: The split whose divider operators in the block should act on.
        :type split: :class:`ion.types.SplitNodeContainer` | None
        :param output: The output operators in the block should act on.
        :type output: :class:`ion.types.Output` | None
        :param workspace: The workspace operators in the block should act on.
        :type workspace: :class:`ion.types.Workspace` | None
        :param desktop: The desktop operators in the block should act on.
        :type desktop: :class:`ion.types.Desktop` | None
        :rtype: AbstractContextManager[UILayout]
        """
        overrides: dict[str, Any] = {
            "window": window,
            "frame": frame,
            "split": split,
            "output": output,
            "workspace": workspace,
            "desktop": desktop,
        }
        return _ContextStore(self, {k: v for k, v in overrides.items() if v is not None})

    def _context_snapshot(self) -> ContextSnapshot | None:
        """Merge the stored overrides over the region context for an operator."""
        from ion.wm import context
        base = context.capture()
        merged: dict[str, Any] = {}
        for overrides in self._context_overrides:
            merged.update(overrides)
        if not merged:
            return base
        from ion.types import ContextSnapshot
        return ContextSnapshot.build(base, **merged)


class _ContextStore(AbstractContextManager["UILayout"]):
    """Context manager pushing one `context_store` override onto a layout."""

    __slots__ = ("_layout", "_overrides")

    def __init__(self, layout: UILayout, overrides: dict[str, Any]) -> None:
        self._layout = layout
        self._overrides = overrides

    def __enter__(self) -> UILayout:
        self._layout._context_overrides.append(self._overrides)
        return self._layout

    def __exit__(self, *_args: object) -> None:
        self._layout._context_overrides.pop()
