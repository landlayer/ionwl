#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Auto-generate the Source Layout section of doc/architecture/readme.rst.

Reads the first ``//! `` doc comment from each ``.rs`` source file and produces
an ASCII tree between SOURCE_LAYOUT_BEGIN / SOURCE_LAYOUT_END.

The tree is discovered rather than listed: every tracked module under ``src`` appears,
at whatever depth it sits, followed by each workspace crate under ``crates``.
``_TREE_ORDER`` only says which top-level entries of ``src`` come first, and
anything it does not name is appended in sorted order, so a new module or crate
shows up without editing this file.

With ``--check`` the README is compared rather than written, failing when the
tree is out of date; ``make check_readme`` runs it this way.
"""

__all__ = (
    "main",
)

import argparse
import os
import re
import subprocess

_BASE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SRC_DIR = os.path.join(_BASE_DIR, "src")
_CRATES_DIR = os.path.join(_BASE_DIR, "crates")
_README_PATH = os.path.join(os.path.dirname(__file__), "readme.rst")

# Preferred order for the top level only; the rest is sorted after these.
# Naming a directory that no longer exists is harmless, which is the point:
# the tree comes from the filesystem, this only arranges it.
_TREE_ORDER = (
    "main.rs",
    "lib.rs",
    "collections.rs",
    "color.rs",
    "enums.rs",
    "geom.rs",
    "system.rs",
    "state",
    "tiling",
    "wm",
    "handler",
    "input",
    "render",
    "backend",
    "protocols",
    "python",
    "ipc",
    "cursor",
    "constants",
    "fixed",
    "prefs",
    "xwayland",
    "bin",
)


class _Entry:
    """One tree row: a file or a directory, with its children."""

    __slots__ = ("children", "desc", "name")

    def __init__(self, name: str, desc: str | None, children: list[_Entry]) -> None:
        self.name = name
        self.desc = desc
        self.children = children


def _first_doc_comment(filepath: str) -> str | None:
    """The text of the first ``//! `` line in *filepath*, or ``None``."""
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^//! (.+)", line)
                if m:
                    return m.group(1).rstrip(".")
    except OSError:
        pass
    return None


def _tracked_rs_paths() -> frozenset[str]:
    """Every ``.rs`` file git tracks, as an absolute path.

    Read from git rather than the disk, as the pre-commit hook leaves untracked
    files in place, and a scratch module must not fail an unrelated commit.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.rs"],
        cwd=_BASE_DIR,
        capture_output=True,
        check=True,
    )
    return frozenset(
        os.path.join(_BASE_DIR, path)
        for path in result.stdout.decode("utf-8").split("\0") if path
    )


def _is_test_name(name: str) -> bool:
    """Whether *name* is test scaffolding rather than a module."""
    return name == "tests" or name.startswith("test_") or name.endswith("_tests.rs")


def _dir_doc_path(parent: str, name: str) -> str:
    """The file carrying a directory's module doc.

    Rust accepts either ``name/mod.rs`` or a sibling ``name.rs``; both are in
    use here (``handler/protocol/`` is described by ``handler/protocol.rs``).
    """
    mod_path = os.path.join(parent, name, "mod.rs")
    if os.path.isfile(mod_path):
        return mod_path
    return os.path.join(parent, "{:s}.rs".format(name))


def _order_key(names: list[str]) -> list[str]:
    """*names* with the `_TREE_ORDER` ones first, the rest sorted after."""
    preferred = [n for n in _TREE_ORDER if n in names]
    rest = sorted(n for n in names if n not in _TREE_ORDER)
    return preferred + rest


def _entries_collect(abs_dir: str, tracked: frozenset[str], top: bool) -> list[_Entry]:
    """Every tracked module in *abs_dir*, recursively, as tree entries."""
    dir_names = []
    file_names = []
    for name in os.listdir(abs_dir):
        if _is_test_name(name):
            continue
        full = os.path.join(abs_dir, name)
        if os.path.isdir(full):
            if any(path.startswith(full + os.sep) for path in tracked):
                dir_names.append(name)
        elif full in tracked and name != "mod.rs":
            file_names.append(name)

    # A directory's own module file describes it, so it is not a row of its own.
    described = {"{:s}.rs".format(d) for d in dir_names}
    file_names = [f for f in file_names if f not in described]

    names = _order_key(dir_names + file_names) if top else (
        sorted(dir_names) + sorted(file_names)
    )

    entries = []
    for name in names:
        if name in dir_names:
            desc = _first_doc_comment(_dir_doc_path(abs_dir, name))
            children = _entries_collect(os.path.join(abs_dir, name), tracked, top=False)
            entries.append(_Entry("{:s}/".format(name), desc, children))
        else:
            desc = _first_doc_comment(os.path.join(abs_dir, name))
            entries.append(_Entry(name, desc, []))
    return entries


def _render(entries: list[_Entry], prefix: str, lines: list[str]) -> None:
    """Append *entries* to *lines*, aligning descriptions within this level."""
    if not entries:
        return
    width = max(len(e.name) for e in entries)
    last = len(entries) - 1
    for i, entry in enumerate(entries):
        desc = "  {:s}".format(entry.desc) if entry.desc else ""
        lines.append("{:s}+- {:<{w}s}{:s}".format(prefix, entry.name, desc, w=width).rstrip())
        if entry.children:
            child_prefix = prefix + ("|   " if i != last else "    ")
            _render(entry.children, child_prefix, lines)
            # Separate a directory block from the next sibling, as before.
            if i != last:
                lines.append("{:s}|".format(prefix))


def _crate_entries_collect(tracked: frozenset[str]) -> list[_Entry]:
    """Every crate in `_CRATES_DIR`, described by its ``lib.rs``."""
    entries = []
    for name in sorted(os.listdir(_CRATES_DIR)):
        crate_src = os.path.join(_CRATES_DIR, name, "src")
        lib_path = os.path.join(crate_src, "lib.rs")
        if lib_path not in tracked:
            continue
        desc = _first_doc_comment(lib_path)
        # The crate's row carries the `lib.rs` doc, as a directory's does for `mod.rs`.
        children = [
            e for e in _entries_collect(crate_src, tracked, top=False)
            if e.name != "lib.rs"
        ]
        entries.append(_Entry("{:s}/".format(name), desc, children))
    return entries


def _tree_build() -> list[str]:
    """The indented ASCII trees, without the surrounding literal block."""
    lines: list[str] = ["  src/"]
    tracked = _tracked_rs_paths()
    _render(_entries_collect(_SRC_DIR, tracked, top=True), "  ", lines)
    lines += ["", "  crates/"]
    _render(_crate_entries_collect(tracked), "  ", lines)
    return lines


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Regenerate the source layout in the architecture README.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report an out-of-date README instead of writing it, exiting non-zero.",
    )
    return parser


def main() -> None:
    """Regenerate the source tree block in the architecture README, or with
    ``--check`` report whether it is current."""
    args = _create_parser().parse_args()

    # Trailing blank line: without it the literal block runs straight into the
    # END marker, which docutils reports as an unexpected unindent.
    tree_text = "\n".join(["", "::", ""] + _tree_build()) + "\n\n"

    with open(_README_PATH, "r", encoding="utf-8") as fh:
        data = fh.read()

    begin_tag = ".. SOURCE_LAYOUT_BEGIN"
    end_tag = ".. SOURCE_LAYOUT_END"
    begin_idx = data.find(begin_tag)
    end_idx = data.find(end_tag, begin_idx)

    if begin_idx == -1:
        raise SystemExit("Error: {!r} not found".format(begin_tag))
    if end_idx == -1:
        raise SystemExit("Error: {!r} not found".format(end_tag))

    begin_idx += len(begin_tag) + 1
    data_update = data[:begin_idx] + tree_text + data[end_idx:]

    if args.check:
        if data_update != data:
            raise SystemExit("Error: {:s} is out of date, run: make doc-readme".format(_README_PATH))
        return

    with open(_README_PATH, "w", encoding="utf-8") as fh:
        fh.write(data_update)

    print("Updated {:s}".format(_README_PATH))


if __name__ == "__main__":
    main()
