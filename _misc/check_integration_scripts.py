# SPDX-License-Identifier: GPL-3.0-or-later

"""
Check the integration tests' Python scripts against the Rust that calls them.

The Rust tests reach ``tests/integration/python/scripts/<module>.py`` only by
name (``python_call("module", "func", ...)``, ``python_attr("module", "name")``),
which neither the compiler nor the Python linters see. So this check requires:

- Every name a Rust call passes is a string literal, defined by its module.
- Every public module-level name in a script is named by a Rust call.
- Every ``_``-prefixed module-level name is used within its module.
"""

__all__ = (
    "main",
)

import ast
import os
import re
import sys

from git_files import tracked_paths_get

_SCRIPTS_DIR = "tests/integration/python/scripts"

# A string, raw string or char literal (kept), or a comment (blanked).
_RUST_TOKEN_RE = re.compile(
    r'(?P<keep>r(?P<hashes>#*)".*?"(?P=hashes)|"(?:\\.|[^"\\])*"|\'(?:\\u\{[0-9a-fA-F]+\}|\\.|[^\\\'])\')'
    r'|//[^\n]*|/\*.*?\*/',
    re.S,
)

# A call to a fixture method taking `(module, name, ...)` (`python_attr` and
# the `python_call` family), with both names captured when they are string
# literals. A `fn` before the name marks a definition, a `self.` the harness
# forwarding its own parameters. The lazy turbofish stops at the first `>(`,
# which can only be its closing bracket.
_CALL_RE = re.compile(
    r'(?P<fn>\bfn\s+)?(?P<self>\bself\s*\.\s*)?'
    r'\b(?P<method>python_call\w*|python_attr)'
    r'\s*(?:::<.*?>)?\s*\(\s*(?:"(?P<module>\w+)"\s*,\s*"(?P<name>\w+)")?',
    re.S,
)


def _rust_comments_strip(source: str) -> str:
    """Return ``source`` with comments blanked, keeping strings and line numbers."""
    return _RUST_TOKEN_RE.sub(
        lambda m: m.group(0) if m.group("keep") else re.sub(r"[^\n]", " ", m.group(0)),
        source,
    )


def _rust_refs_collect(
        paths: list[str],
        errors: list[str],
) -> dict[tuple[str, str], list[str]]:
    """Return each ``(module, name)`` the Rust calls pass, mapped to its call sites."""
    refs: dict[tuple[str, str], list[str]] = {}
    for path in paths:
        with open(path, "r", encoding="utf-8") as fh:
            code = _rust_comments_strip(fh.read())
        for m in _CALL_RE.finditer(code):
            if m.group("fn"):
                continue
            location = "{:s}:{:d}".format(path, code.count("\n", 0, m.start("method")) + 1)
            if m.group("module") is None:
                if m.group("self"):
                    continue
                errors.append("{:s}: `{:s}` must name its module and name as string literals".format(
                    location, m.group("method"),
                ))
                continue
            refs.setdefault((m.group("module"), m.group("name")), []).append(location)
    return refs


def _module_defs(tree: ast.Module) -> list[tuple[str, int]]:
    """Return ``(name, line)`` for each module-level definition, dunders excluded."""
    defs: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs.append((node.name, node.lineno))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defs.append((target.id, node.lineno))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defs.append((node.target.id, node.lineno))
    return [(name, line) for name, line in defs if not (name.startswith("__") and name.endswith("__"))]


def _names_loaded(tree: ast.Module) -> set[str]:
    """Return every name read anywhere in ``tree``."""
    return {
        node.id for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def main() -> int:
    """Check the integration scripts and the Rust calls naming them."""
    rust_paths = tracked_paths_get("tests/*.rs")
    script_paths = tracked_paths_get("{:s}/*.py".format(_SCRIPTS_DIR))
    if rust_paths is None or script_paths is None:
        return 1

    errors: list[str] = []
    refs = _rust_refs_collect(rust_paths, errors)

    modules_defs: dict[str, set[str]] = {}
    for path in script_paths:
        module = os.path.splitext(os.path.basename(path))[0]
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        defs = _module_defs(tree)
        modules_defs[module] = {name for name, _line in defs}
        loaded = _names_loaded(tree)
        for name, line in defs:
            if name.startswith("_"):
                if name not in loaded:
                    errors.append("{:s}:{:d}: `{:s}` is never used".format(path, line, name))
            elif (module, name) not in refs:
                errors.append(
                    "{:s}:{:d}: `{:s}` is not named by any Rust test "
                    "(prefix it with `_` if it is module-private)".format(path, line, name)
                )

    for (module, name), locations in sorted(refs.items()):
        if module not in modules_defs:
            message = "unknown script module `{:s}` (is it tracked by git?)".format(module)
        elif name not in modules_defs[module]:
            message = "`{:s}` defines no `{:s}`".format(module, name)
        else:
            continue
        for location in locations:
            errors.append("{:s}: {:s}".format(location, message))

    for error in errors:
        print(error)
    if errors:
        sys.stderr.write("ERROR: {:d} integration script problem(s).\n".format(len(errors)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
