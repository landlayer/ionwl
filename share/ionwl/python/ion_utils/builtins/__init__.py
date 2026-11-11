# SPDX-License-Identifier: GPL-3.0-or-later

# Built-in operator registration.

__all__ = (
    "keymaps_ensure",
    "register",
)


def register() -> None:
    """Register all built-in operators, and create the keymaps they use."""
    from .operators import register as _register
    _register()
    keymaps_ensure()


def keymaps_ensure() -> None:
    """Create the keymaps the built-in operators use, where missing."""
    import ion

    from .operators import keymap_names
    keymaps = ion.app.keymaps
    for name in keymap_names:
        keymaps.ensure(name)
