#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Check the generated stubs against the live ``ion`` module with mypy's stubtest.

The stubs are generated from docstrings, so a misnamed method, a wrong
parameter list or a missing attribute would otherwise be typed against
unnoticed. ``ion`` exists only inside ionwl, so this runs there, launched by
``sphinx_gen_run.py --stubtest``.

Differences not yet resolved are listed in ``stubtest_allowlist.txt``.
Stubtest fails on an entry that no longer matches, so a fix removes its own.
"""

__all__ = (
    "main",
)

import os
import sys
from pathlib import Path

from mypy import stubtest

_SCRIPT_DIR = Path(__file__).parent


def main(argv: list[str]) -> int:
    """Run stubtest over ``ion`` with *argv* as extra options, returning its exit code."""
    os.environ["MYPYPATH"] = str(_SCRIPT_DIR / "stubs")
    # Reached as an attribute of `ion`, so registered for stubtest to import.
    sys.modules["ion._internal"] = vars(sys.modules["ion"])["_internal"]
    options = stubtest.parse_options([
        "ion",
        "--concise",
        # A typing marker newer than the stubs; it says nothing about the API.
        "--ignore-disjoint-bases",
        "--allowlist", str(_SCRIPT_DIR / "stubtest_allowlist.txt"),
        *argv,
    ])
    return stubtest.test_stubs(options)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
