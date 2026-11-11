# SPDX-License-Identifier: GPL-3.0-or-later

# The library's internals.
#
# The compositor imports these modules by name, so renaming one is a Python
# rename and a Rust string literal. `make test` reaches every one; the compiler
# and `make check_all` do not.
#
# - `operator_dispatch`: `call`, `_poll` and `_exec`, fetched as `ion.ops` is
#   built (`python/operator.rs`), for every operator poll and exec.
# - `menu_dispatch`: `MenuRegistry`, `Menu` and `MenuBuilder`, published as
#   `ion.types` (`python/init.rs`), and a `MenuRegistry` as `ion.app.menus`
#   (`python/app.rs`). `_build` and `_poll` for every menu build and poll
#   (`python/popups.rs`, `python/hooks.rs`).
# - `ui_layout`: `UILayout`, published as `ion.types` (`python/init.rs`).
# - `ipc_execute`: `execute`, for every IPC request (`python/run.rs`).
# - `desktop_layout`: `desktop_layout_calc` and `layout_find_adjacent`, the
#   bodies of `ion.wm.desktops.layout_calc` and `find_adjacent`
#   (`python/desktop.rs`).
#
# The other direction is `ion._internal`, the functions the library calls on
# the compositor. Its page is generated but not published (`exclude_patterns`
# in `doc/python_api/conf.py`), and its stub type-checks the library.

__all__ = ()
