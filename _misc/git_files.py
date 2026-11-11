# SPDX-License-Identifier: GPL-3.0-or-later

"""
List the files tracked by git, for the source checks that scan the tree.

Shared so a check cannot drift onto its own notion of which files count.
"""

__all__ = (
    "tracked_paths_get",
)

import subprocess
import sys


def tracked_paths_get(*patterns: str) -> list[str] | None:
    """Return sorted tracked paths matching ``patterns``, or ``None`` on failure."""
    result = subprocess.run(
        ["git", "ls-files", "-z", *patterns],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write("git ls-files failed: {:s}\n".format(result.stderr.decode("utf-8", "replace")))
        return None
    return sorted(path for path in result.stdout.decode("utf-8").split("\0") if path)
