This module provides helper functions for
configuration scripts. The non-obvious member is
:func:`exec_generator`, which drives Python generators as coroutines
on the compositor's event loop - useful for animations and multi-step
UI sequences that need to yield between steps.

.. WARNING: Do not add listings of sub-modules, documentation generation can do this,
   such lists must never be hand-maintained.
