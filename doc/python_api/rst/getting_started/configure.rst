#############
Configuration
#############

IonWL is configured entirely through Python. The config file is ``~/.config/ionwl/ion_init.py``.
It runs at startup, and again on each reload (see :mod:`ion.app`).

A typical configuration sets up:

- Preferences (:data:`ion.app.preferences`).
- Key and pointer bindings (:data:`ion.app.keymaps`, :mod:`ion.ops`).
- Hooks (:data:`ion.app.hooks`) - may create desktops or launch services on startup.


Sample Configurations
=====================

Copy either to ``~/.config/ionwl/ion_init.py`` and customize.

Minimal
-------

A minimal starting point: window management, launchers, and compositor controls, without tiling-navigation keys.
Other actions remain reachable through the right-click context menus.

.. literalinclude:: config/minimal/ion_init.py
   :language: python

Full
----

The bundled sample configuration wires up Notion-style keybindings with
VIM-style (HJKL) navigation.

.. literalinclude:: config/default/ion_init.py
   :language: python

Type Checking
=============

Validate your configuration with ``mypy`` using the installed stubs:

.. code:: sh

   MYPYPATH=/opt/ionwl/share/ionwl/python mypy --strict ~/.config/ionwl/ion_init.py
