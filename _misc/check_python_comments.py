# SPDX-License-Identifier: GPL-3.0-or-later

"""
Check that Python ``#`` comments do not use RST double back-ticks.

Code references in ``#`` comments must use single back-ticks. Double
back-ticks are RST inline-literal syntax and belong in docstrings only.
"""

__all__ = (
    "main",
)

import re
import sys
import tokenize

from git_files import tracked_paths_get

_PATTERN = re.compile(r"#[^\n]+``")


def _check_file(filepath: str) -> list[tuple[int, int, str]]:
    """Return a list of ``(line, col, text)`` for offending comments."""
    matches: list[tuple[int, int, str]] = []
    try:
        with open(filepath, "rb") as fh:
            tokens = list(tokenize.tokenize(fh.readline))
    except (OSError, SyntaxError, tokenize.TokenError):
        return matches

    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        if _PATTERN.search(tok.string) is None:
            continue
        line, col = tok.start
        matches.append((line, col, tok.string))
    return matches


def main() -> int:
    """Scan tracked Python files for ``#`` comments with double back-ticks."""
    paths = tracked_paths_get("*.py")
    if paths is None:
        return 1

    errors = 0
    for filepath in paths:
        for line, col, text in _check_file(filepath):
            print("{:s}:{:d}:{:d}: {:s}".format(filepath, line, col, text))
            errors += 1

    if errors:
        sys.stderr.write("ERROR: {:d} comment(s) use RST double back-ticks (use single back-ticks).\n".format(errors))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
