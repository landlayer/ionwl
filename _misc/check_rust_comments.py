# SPDX-License-Identifier: GPL-3.0-or-later

"""
Check that standalone Rust ``//`` comments end with terminating punctuation.

Prose comments are full sentences and must end with ``.``, ``!``, ``?`` or
``:``, optionally followed by a closing bracket or quote. Four forms are
exempt because a terminator reads as noise on them: decorative banners (a run
of ``=`` or ``-`` opening or closing the line), lines with no letters (rules
and ASCII art), short labels of at most ``LABEL_WORDS_MAX`` words, and
commented-out code. Doc comments (``///`` and ``//!``) are left to rustdoc
conventions, and trailing comments on a code line are not checked.

Only a block's last line is checked, since prose that wraps leaves every
earlier line mid-sentence and no rule can tell that from a missing
terminator.
"""

__all__ = (
    "BANNER_RE",
    "CLOSERS",
    "CODE_TAILS",
    "LABEL_WORDS_MAX",
    "LETTER_RE",
    "TERMINATORS",
    "block_is_exempt",
    "blocks_extract",
    "check_file",
    "main",
    "unterminated_find",
)

import re
import sys

from git_files import tracked_paths_get

# A comment block of at most this many words is a label, not prose.
LABEL_WORDS_MAX = 4

TERMINATORS = ".!?:"

# A banner opens or closes with a run of rule characters. Matching a run
# anywhere would exempt prose that merely contains one.
BANNER_RE = re.compile(r"^[-=]{2,}|[-=]{2,}$")

LETTER_RE = re.compile(r"[A-Za-z]")

# A body ending in one of these is commented-out code rather than prose.
CODE_TAILS = "{};"

# Closing punctuation that may follow the terminator, as in "(like this.)".
CLOSERS = ")]\"'`*"


def blocks_extract(text: str) -> list[list[tuple[int, str]]]:
    """Return each run of standalone ``//`` comments as ``(line, body)`` pairs."""
    blocks: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        is_comment = (
            stripped.startswith("//") and
            not stripped.startswith("///") and
            not stripped.startswith("//!")
        )
        if is_comment:
            current.append((lineno, stripped[2:].strip()))
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def block_is_exempt(bodies: list[str]) -> bool:
    """Return true for headers, banners, art, short labels and code."""
    if bodies[0].startswith("SPDX"):
        return True
    if any(BANNER_RE.search(body) for body in bodies):
        return True
    # A closing line with no letters is a rule or ASCII art, not a sentence.
    if LETTER_RE.search(bodies[-1]) is None:
        return True
    if bodies[-1][-1] in CODE_TAILS:
        return True
    return sum(len(body.split()) for body in bodies) <= LABEL_WORDS_MAX


def unterminated_find(text: str) -> list[tuple[int, str]]:
    """Return ``(line, body)`` for each comment block missing a terminator.

    The line is that of the block's last non-empty comment, which is where a
    terminator belongs.
    """
    matches: list[tuple[int, str]] = []
    for block in blocks_extract(text):
        filled = [(lineno, body) for lineno, body in block if body]
        if not filled:
            continue
        bodies = [body for _lineno, body in filled]
        if block_is_exempt(bodies):
            continue
        lineno, body = filled[-1]
        tail = body.rstrip(CLOSERS)
        if tail and tail[-1] in TERMINATORS:
            continue
        matches.append((lineno, body))
    return matches


def check_file(filepath: str) -> list[tuple[int, str]]:
    """Return ``(line, body)`` for each offending comment block in a file."""
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []
    return unterminated_find(text)


def main() -> int:
    """Scan tracked Rust files for unterminated standalone comments."""
    paths = tracked_paths_get("*.rs")
    if paths is None:
        return 1

    errors = 0
    for filepath in paths:
        for lineno, text in check_file(filepath):
            print("{:s}:{:d}: // {:s}".format(filepath, lineno, text))
            errors += 1

    if errors:
        sys.stderr.write("ERROR: {:d} comment(s) do not end with '{:s}'.\n".format(errors, TERMINATORS))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
