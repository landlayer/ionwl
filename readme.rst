#####
IonWL
#####

A Wayland compositor inspired by Ion3_, built on Smithay_.

See the documentation_ for a full overview, including the Python API reference.

.. _Ion3: https://en.wikipedia.org/wiki/Ion_%28window_manager%29
.. _Smithay: https://github.com/Smithay/smithay
.. _documentation: https://ideasman42.codeberg.page/IonWL/


Why IonWL?
==========

Most tiling compositors on Wayland use automatic layouts that rearrange windows when you open or close them.
Ion3_ took a different approach: you manually split the screen into frames,
and windows open inside those frames as tabs.
This gives you full control over your layout - it stays exactly how you set it up.

At the time of writing, nothing on Wayland offers this model. IonWL brings it to Wayland
with a Python scripting API for configuration and key-bindings.

.. figure:: https://codeberg.org/attachments/b2b13046-d8c0-444e-ace6-f4467f49cd20
   :scale: 50 %
   :align: center

   Screenshot.


Features
========

- **Manual tiling**: Split the screen into frames and manage windows as tabs.
  Layouts stay fixed - opening or closing windows doesn't rearrange anything.
- **Floating windows**: Full floating layer with z-ordering.
- **Scratch workspaces**: Workspaces can float as overlays, acting as toggle-able scratch-pads.
- **Shared desktops**: All outputs belong to one desktop.
  Switching desktops switches all outputs at once.
- **Python API**: Key-bindings and configuration written in Python,
  with direct access to windows, frames, workspaces, and outputs.
  The Python API may also be invoked from external commands to run custom scripts.
- **Flexible key-bindings**:
  Separate bindings for press, release, and click for both mouse and keyboard.
  Modifier keys can be bound as tap actions.
  Key-bindings can optionally consume events and/or pass them through to the client.
- **IPC**: Unix socket interface with ``ionwl-cmd`` for scripting and external tools.


See the `supported features <https://ideasman42.codeberg.page/IonWL/features.html>`__ documentation
for a comprehensive list.


Requirements
============

- Linux or FreeBSD.
- Rust 1.96+.
- Python 3.
- libseat, libinput & udev.
- GPU with DRM/KMS support.
- `Sphinx <https://www.sphinx-doc.org/>`__ (for building Python API docs).


Building
========

.. code:: sh

   cargo build --release

To disable XWayland support:

.. code:: sh

   cargo build --release --no-default-features


Installation
============

Arch Linux
   Install `ionwl-git <https://aur.archlinux.org/packages/ionwl-git>`__ from the AUR.

From Source
   Build and install with ``make``:

   .. code:: sh

      make
      make install PREFIX=/opt/ionwl

      mkdir -p ~/.config/ionwl
      cp config/default/ion_init.py ~/.config/ionwl/

Usage
=====

See the `documentation <https://ideasman42.codeberg.page/IonWL/>`__ for more details as well as the Python API.


Running
-------

.. code:: sh

   # From a TTY (not inside another compositor).
   ./target/release/ionwl


Customizing
-----------

- See the `configuration <https://ideasman42.codeberg.page/IonWL/configuration.html>`__ documentation.


Attribution
===========

- Tuomo Valkonen
  Original author of the `Ion3 (window-manager) <https://en.wikipedia.org/wiki/Ion_%28window_manager%29>`__
- `Pinnacle <https://github.com/pinnacle-comp/pinnacle>`__
  (protocol implementations, backend initialization, cursor management, input handling, XWayland integration).
- `Niri <https://github.com/YaLTeR/niri>`__
  (window creation logic, DMABUF allocation, foreign toplevel protocol).
- `Cosmic <https://github.com/pop-os/cosmic-comp>`__
  (layer shell deferred mapping, window mapping gate, interactive resize, output management).

Note
   This was written with the assistance of an LLM, in some cases using existing open-source code as a reference,
   full credit goes to those projects on which this is based.


License
=======

GPL 3 or later, See LICENSE file for details.
