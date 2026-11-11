IonWL is a tiling Wayland compositor configured entirely in Python. See
:doc:`configure` for an introduction to the config file and the data
and execution models.

.. WARNING: Do not add listings of sub-modules, documentation generation can do this,
   such lists must never be hand-maintained.

Threads
   Call the ``ion`` API only from the thread that runs the config and its
   callbacks. A call from any other thread, such as one started with
   ``threading``, is not supported.
