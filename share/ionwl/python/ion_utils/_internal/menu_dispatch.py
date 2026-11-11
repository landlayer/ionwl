# SPDX-License-Identifier: GPL-3.0-or-later

# Menu registry and dispatch functions used by the Rust menu system.
# Installed on `ion.app` as `menus` during module creation.

from __future__ import annotations

__all__ = (
    "Menu",
    "MenuBuilder",
    "MenuRegistry",
)

from collections.abc import Callable, Iterator

from ion_utils._internal.ui_layout import UILayout


class _MenuEntry:
    """Internal storage for a registered menu."""

    __slots__ = ("callback", "name", "poll")

    def __init__(
            self,
            name: str,
            callback: Callable[[MenuBuilder], None],
            poll: Callable[[], str | None] | None,
    ) -> None:
        self.name = name
        self.callback = callback
        self.poll = poll


class Menu:
    """A reference to a registered menu in the registry.

    .. method:: __init__(self, idname)

       :param idname: The menu identifier.
       :type idname: str
       :rtype: None
    """

    __slots__ = ("_idname",)

    def __init__(self, idname: str) -> None:
        self._idname = idname

    @property
    def idname(self) -> str:
        """The menu identifier.

        :type: str
        """
        return self._idname

    @property
    def name(self) -> str | None:
        """The display name.

        :type: str | None
        """
        import ion
        registry: MenuRegistry = ion.app.menus  # type: ignore[assignment]
        entry = registry._entries.get(self._idname)
        if entry is not None:
            return entry.name
        return None

    def __repr__(self) -> str:
        return "Menu('{:s}')".format(self._idname)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Menu):
            return NotImplemented
        return self._idname == other._idname

    def __hash__(self) -> int:
        return hash(self._idname)


class MenuBuilder:
    """Builder passed to menu callbacks.

    The callback receives a fresh builder each time the menu is shown. GUI
    elements are added through its :class:`ion.types.UILayout`, accessed as
    ``menu.layout`` (see :class:`ion.types.UILayout` for the element methods).
    """

    __slots__ = ("_layout",)

    def __init__(self) -> None:
        self._layout = UILayout()

    @property
    def layout(self) -> UILayout:
        """The layout that collects this menu's GUI elements.

        :type: UILayout
        """
        return self._layout


class MenuRegistry:
    """Registry of named menus with builder callbacks: ``ion.app.menus.new('tab', 'Tab', callback)``.

    Callbacks receive a :class:`ion.types.MenuBuilder` and are called each time the menu
    is shown, enabling dynamic items.

    .. code-block:: python

       import ion
       import ion.ops as ops

       def my_menu(menu):
           menu.layout.operator(ops.window_close())
           menu.layout.separator()
           menu.layout.operator(ops.frame_delete())

       ion.app.menus.new("context", "Context Menu", my_menu)

    The registry follows the dict protocol: iteration yields menu idnames,
    ``"name" in menus`` tests membership, ``menus["name"]`` returns the
    :class:`ion.types.Menu`, and ``keys()`` / ``values()`` / ``items()``
    expose the three views.

    .. method:: __len__(self)

       Number of menus.

       :rtype: int

    .. method:: __bool__(self)

       True if any menu is registered.

       :rtype: bool

    .. method:: __iter__(self)

       Iterate over menu idnames (dict-like).

       :rtype: Iterator[str]

    .. method:: __reversed__(self)

       Iterate over menu idnames in reverse order.

       :rtype: Iterator[str]

    .. method:: __contains__(self, idname)

       Test whether a menu with this idname is registered.

       :param idname: The menu identifier.
       :type idname: str
       :rtype: bool

    .. method:: __getitem__(self, idname)

       Get a menu by idname.

       :param idname: The menu identifier.
       :type idname: str
       :rtype: :class:`ion.types.Menu`
       :raises KeyError: If no menu with this idname is registered.
    """

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: dict[str, _MenuEntry] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __reversed__(self) -> Iterator[str]:
        return reversed(self._entries)

    def __contains__(self, idname: object) -> bool:
        return idname in self._entries

    def __getitem__(self, idname: str) -> Menu:
        if idname not in self._entries:
            raise KeyError(idname)
        return Menu(idname)

    def new(
        self,
        idname: str,
        name: str,
        callback: Callable[[MenuBuilder], None],
        poll: Callable[..., str | None] | None = None,
    ) -> None:
        """Register a named menu with a builder callback.

        .. code-block:: python

           ion.app.menus.new("tab", "Tab", lambda menu: (
               menu.layout.operator(ion.ops.window_close()),
               menu.layout.operator(ion.ops.frame_delete()),
           ))

        :param idname: Unique identifier used to reference this menu.
        :type idname: str
        :param name: Human-readable display name (used as submenu label).
        :type name: str
        :param callback: Receives a :class:`ion.types.MenuBuilder`, called each time the menu is shown.
        :type callback: ``Callable[[MenuBuilder], None]``
        :param poll: Optional callable returning ``None`` if the menu is available,
            or a string reason if it should be hidden.
        :type poll: ``Callable[..., str | None]`` | None
        :rtype: None
        """
        if not callable(callback):
            raise TypeError("callback must be callable")
        if poll is not None and not callable(poll):
            raise TypeError("poll must be callable")
        self._entries[idname] = _MenuEntry(name, callback, poll)

    def get(self, idname: str, default: object = None) -> Menu | object:
        """Get a menu by identifier, returning ``default`` if not found.

        :param idname: The menu identifier.
        :type idname: str
        :param default: Value returned when the menu is missing.
        :type default: object

        :return: The menu, or ``default`` if not found.
        :rtype: :class:`ion.types.Menu` | object
        """
        if idname in self._entries:
            return Menu(idname)
        return default

    def keys(self) -> list[str]:
        """All menu identifiers.

        :return: List of menu identifier strings.
        :rtype: list[str]
        """
        return list(self._entries.keys())

    def remove(self, menu: Menu) -> None:
        """Remove a menu.

        :param menu: The menu to remove.
        :type menu: :class:`ion.types.Menu`
        :rtype: None
        """
        if menu.idname not in self._entries:
            raise KeyError("Unknown menu: '{:s}'".format(menu.idname))
        del self._entries[menu.idname]

    def items(self) -> list[tuple[str, Menu]]:
        """All (idname, menu) pairs.

        :return: List of (idname, menu) tuples.
        :rtype: list[tuple[str, :class:`ion.types.Menu`]]
        """
        return [(k, Menu(k)) for k in self._entries]

    def values(self) -> list[Menu]:
        """All menus.

        :return: List of menus.
        :rtype: list[:class:`ion.types.Menu`]
        """
        return [Menu(k) for k in self._entries]

    def clear(self) -> None:
        """Remove all menus.

        :rtype: None
        """
        self._entries.clear()

    def show(self, idname: str) -> None:
        """Show a named context menu.

        Must be called during a keybinding callback.

        .. code-block:: python

           ion.app.menus.show("context")

        :param idname: The menu identifier to show.
        :type idname: str
        :rtype: None
        """
        import ion
        items = _build(idname)
        if items:
            ion.ui._popup_menu_defs(items)  # type: ignore[attr-defined]

    def __repr__(self) -> str:
        return "MenuRegistry(menus={:d})".format(len(self._entries))


def _build(idname: str) -> list[tuple[object, ...]]:
    """Build a named menu by looking up the registry and calling the callback.

    Returns a list of tuples suitable for passing to Rust, or an empty list
    on error or if the menu is not registered.

    :param idname: The menu identifier.
    :type idname: str
    :rtype: list[tuple[object, ...]]
    """
    import ion
    registry: MenuRegistry = ion.app.menus  # type: ignore[assignment]
    entry = registry._entries.get(idname)
    if entry is None:
        return []
    builder = MenuBuilder()
    entry.callback(builder)
    items = builder.layout._items

    # Resolve submenu labels from the registry's display names.
    for i, item in enumerate(items):
        if item[0] == "submenu":
            sub_id = item[2]
            assert isinstance(sub_id, str)
            sub_entry = registry._entries.get(sub_id)
            if sub_entry is not None:
                items[i] = ("submenu", sub_entry.name, sub_id)
            else:
                items[i] = ("submenu", sub_id, sub_id)

    return items


def _poll(idname: str) -> bool:
    """Check whether a named menu's poll allows it to be shown.

    Returns True if the menu is available (no poll or poll returns None).

    :param idname: The menu identifier.
    :type idname: str
    :rtype: bool
    """
    import ion
    registry: MenuRegistry = ion.app.menus  # type: ignore[assignment]
    entry = registry._entries.get(idname)
    if entry is None:
        return True
    if entry.poll is None:
        return True
    try:
        result = entry.poll()
        return result is None
    except Exception as ex:
        ion.utils.error_report("Menu '{:s}' poll".format(idname), ex)
        return False
