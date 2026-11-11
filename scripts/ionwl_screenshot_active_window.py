#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Screenshot the active window using grim and ionwl IPC.

Asks ionwl for the focused window's geometry, then hands that region to
``grim``. By default the compositor's decorations (tab bar and border) are
excluded; pass ``--decorations`` to include them (a floating window draws its
decorations outside its frame rect, so the flag makes no difference there).
Any other arguments are forwarded to ``grim`` unchanged, so the usual output
options keep working::

   ionwl_screenshot_active_window.py shot.png
   ionwl_screenshot_active_window.py --decorations shot.png
   ionwl_screenshot_active_window.py - | wl-copy
"""

from __future__ import annotations

__all__ = (
    "main",
)

# Deliberately self-contained so copied scripts keep working.
# pylint: disable=duplicate-code

import argparse
import ast
import subprocess
import sys


def _ionwl_cmd(*args: str) -> subprocess.CompletedProcess[str]:
    """Run ``ionwl-cmd`` and return the completed process."""
    try:
        return subprocess.run(
            ["ionwl-cmd", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        sys.exit("Error: ionwl-cmd is not installed")


def main() -> None:
    """Capture the active window's region into grim."""
    parser = argparse.ArgumentParser(
        description="Screenshot the active ionwl window using grim.",
    )
    parser.add_argument(
        "--decorations",
        action="store_true",
        help="Include the window decorations (tab bar and border).",
    )
    # Unrecognized arguments are forwarded to grim (e.g. an output path or "-").
    args, grim_args = parser.parse_known_args()

    # The frame rect includes decorations; the content rect excludes them.
    attr = "frame_rect" if args.decorations else "content_rect"

    # Return the focused window's rectangle as ((x0, y0), (x1, y1)) in global
    # layout coordinates, or None when no window is focused or placed yet.
    expr = (
        "(r.to_tuple() if (w := ion.wm.windows.active) is not None "
        "and (r := w.{:s}) is not None else None)".format(attr)
    )
    result = _ionwl_cmd("python-eval", expr)
    if result.returncode != 0:
        sys.exit(result.stderr.strip() or "ionwl-cmd failed")

    reply = result.stdout.strip()
    try:
        rect = ast.literal_eval(reply)
    except (ValueError, SyntaxError):
        sys.exit("Error: unexpected reply from ionwl-cmd: {:s}".format(reply))
    if rect is None:
        sys.exit("No active window, or it is not placed yet")

    (x0, y0), (x1, y1) = rect
    geometry = "{:d},{:d} {:d}x{:d}".format(x0, y0, x1 - x0, y1 - y0)

    try:
        proc = subprocess.run(
            ["grim", "-g", geometry, *grim_args],
            check=False,
        )
    except FileNotFoundError:
        sys.exit("Error: grim is not installed")

    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
