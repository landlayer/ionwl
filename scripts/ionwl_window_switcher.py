#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Window switcher using tofi (dmenu-like) and ionwl IPC."""

__all__ = (
    "main",
)

# Deliberately self-contained so copied scripts keep working.
# pylint: disable=duplicate-code

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
    """Show a tofi menu of windows and focus the selected one."""
    # Query all windows as a list of (id, title, app_id, workspace_name, is_focused).
    expr = (
        "["
        "(w.id, w.title or w.app_id or '<no title>', w.app_id or '', "
        "w.workspace.name if w.workspace else 'floating', "
        "w.is_focused)"
        " for w in ion.wm.windows"
        "]"
    )
    result = _ionwl_cmd("python-eval", expr)
    if result.returncode != 0:
        sys.exit(result.stderr.strip() or "ionwl-cmd failed")

    reply = result.stdout.strip()
    try:
        windows: list[tuple[int, str, str, str, bool]] = ast.literal_eval(reply)
    except (ValueError, SyntaxError):
        sys.exit("Error: unexpected reply from ionwl-cmd: {:s}".format(reply))

    if not windows:
        sys.exit("No windows open")

    # Build menu lines, disambiguating duplicates with a numeric suffix.
    seen: dict[str, int] = {}
    lines: list[str] = []
    ids: list[int] = []
    for wid, title, app_id, ws_name, focused in windows:
        suffix = " *" if focused else ""
        if app_id and app_id != title:
            base = "[{:s}] {:s} [{:s}]{:s}".format(app_id, title, ws_name, suffix)
        else:
            base = "{:s} [{:s}]{:s}".format(title, ws_name, suffix)
        count = seen.get(base, 0)
        seen[base] = count + 1
        line = "{:s} <{:d}>".format(base, count + 1) if count > 0 else base
        lines.append(line)
        ids.append(wid)

    # Short prompt to avoid widening the tofi popup.
    try:
        proc = subprocess.run(
            ["tofi", "--prompt-text", ": "],
            input="\n".join(lines),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        sys.exit("Error: tofi is not installed")

    choice = proc.stdout.strip()
    if not choice:
        sys.exit(0)

    try:
        i = lines.index(choice)
    except ValueError:
        sys.exit("Error: could not match selection: {:s}".format(choice))

    # Jump to the selected window using its stable ID.
    wid = ids[i]
    code = "ion.wm.windows.active_goto(ion.wm.windows.find_by_id({:d}))".format(wid)
    result = _ionwl_cmd("python-exec", code)
    if result.returncode != 0:
        sys.exit(result.stderr.strip() or "ionwl-cmd failed")


if __name__ == "__main__":
    main()
