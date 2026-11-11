############
Installation
############

Requirements
============

- Linux or FreeBSD.
- Rust 1.96 or later.
- Python 3.
- ``libseat``, ``libinput`` and ``udev`` (development headers to build from source).
- A GPU with DRM/KMS support.

Install
=======

Arch Linux
   Install `ionwl-git <https://aur.archlinux.org/packages/ionwl-git>`__ from the AUR.

From Source
   Build and install with ``make``:

   .. code:: sh

      make
      make install PREFIX=/opt/ionwl

      mkdir -p ~/.config/ionwl
      cp config/default/ion_init.py ~/.config/ionwl/

   ``PREFIX`` defaults to ``/usr/local``. Rather than repeating it on each
   command, set it once in a gitignored ``.env`` file at the repository root
   (a command-line ``PREFIX=...`` still overrides it):

   .. code:: make

      PREFIX = /opt/ionwl

Runtime Programs
================

The bundled configuration binds external programs for its default actions:
a terminal (``foot``), an application launcher (``tofi``), a notification
daemon (``mako``) and volume/media controls (``wpctl``, ``cmus``). Install the
ones you use, or edit the bindings in your config.

Launching
=========

Run from a TTY, not from inside another compositor. Launching from a TTY needs
an active seat, provided either by a ``logind`` session (the usual case on
systemd systems - simply log in on a virtual terminal) or a running ``seatd``
daemon.

Launch either the local build produced by ``cargo`` or the installed binary.

Local Build
   .. code:: sh

      ./target/release/ionwl

Installed
   .. code:: sh

      /opt/ionwl/bin/ionwl

From a Display Manager
   ``make install`` also installs a ``wayland-sessions`` entry, so IonWL appears
   as a session at the login screen. Display managers only scan
   ``wayland-sessions`` directories on ``XDG_DATA_DIRS``, so install into a
   prefix they search (typically ``/usr``):

   .. code:: sh

      make install PREFIX=/usr

Uninstalling
============

Remove an installation with ``make uninstall``, passing the same ``PREFIX``.

Next Steps
==========

See :doc:`configure` to set up preferences and key bindings.
