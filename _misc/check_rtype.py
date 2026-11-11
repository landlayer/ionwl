# SPDX-License-Identifier: GPL-3.0-or-later

"""
Check each documented Python ``:rtype:`` against the Rust function behind it.

Stubtest checks names and parameters against the live module, but a PyO3
method carries no return annotation, so a wrong ``:rtype:`` reaches the stubs
unchecked. This reads the generated RST (so docstrings a macro builds are
covered too), pairs each method or function with its Rust ``fn`` by name, maps
the Rust return type to Python's and reports where the two disagree.

A protocol method with no literal Rust ``fn`` (one a macro generates) is
checked against the type Python's data model fixes for it instead. Returns
typed as ``PyAny`` (or another untyped object), overloads, ``Iterator``
returns and other macro-generated methods are skipped: their type is in no
signature this can read.
"""

__all__ = (
    "main",
)

import collections
import os
import re
import sys

_RST_DIR = "doc/python_api/build"
_RUST_DIR = "src/python"

# A string or char literal, or a comment: blanked so braces inside them do not
# count, keeping every offset.
_RUST_BLANK_RE = re.compile(
    r'r(?P<hashes>#*)".*?"(?P=hashes)|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\\\'])\'|//[^\n]*|/\*.*?\*/',
    re.S,
)

_PYCLASS_RE = re.compile(r'#\[pyclass(?:\((?P<args>[^\]]*)\))?\]')
_TYPE_DEF_RE = re.compile(r'\b(?:struct|enum)\s+(?P<name>\w+)')
_PYMETHODS_RE = re.compile(r'#\[pymethods\]\s*impl\s+(?P<name>\w+)\s*(?:<[^>]*>)?\s*\{')
_PYFUNCTION_RE = re.compile(r'#\[pyfunction(?:\((?P<args>[^\]]*)\))?\]')
_FN_RE = re.compile(r'\bfn\s+(?P<name>\w+)\s*(?:<[^>]*>)?\s*\(')
_NAME_ARG_RE = re.compile(r'\bname\s*=\s*"(?P<name>\w+)"')

_INT = frozenset(("i8", "i16", "i32", "i64", "isize", "u8", "u16", "u32", "u64", "usize"))
_FLOAT = frozenset(("f32", "f64"))
_STR = frozenset(("String", "str", "PyBackedStr", "Cow", "PyString", "OsString"))
# Rust types whose Python type the signature does not say.
_UNTYPED = frozenset(("PyAny", "PyObject", "PyList", "PyTuple", "PyDict", "PySet", "PyIterator"))
# What Python's data model fixes a protocol method to return, `None` for the
# enclosing class.
_DATA_MODEL = {
    "__repr__": "str",
    "__str__": "str",
    "__format__": "str",
    "__hash__": "int",
    "__len__": "int",
    "__bool__": "bool",
    "__contains__": "bool",
    "__eq__": "bool",
    "__ne__": "bool",
    "__init__": "None",
    "__setitem__": "None",
    "__delitem__": "None",
    "__copy__": None,
    "__deepcopy__": None,
}
# Wrappers whose Python type is their argument's.
_TRANSPARENT = frozenset(("PyResult", "Py", "Bound", "PyRef", "PyRefMut", "Box", "Arc"))


def _blank(text: str) -> str:
    """Blank strings and comments, keeping offsets."""
    return _RUST_BLANK_RE.sub(lambda m: " " * len(m.group(0)), text)


def _brace_end(blanked: str, start: int) -> int:
    """The offset just past the brace block opening at ``start``."""
    depth = 0
    for i in range(start, len(blanked)):
        ch = blanked[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(blanked)


def _return_type(blanked: str, paren: int) -> str:
    """The return type of a ``fn`` whose parameter list opens at ``paren``."""
    depth = 0
    i = paren
    while i < len(blanked):
        ch = blanked[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    tail = blanked[i + 1:]
    end = min(pos for pos in (tail.find("{"), tail.find(";"), len(tail)) if pos >= 0)
    sig = tail[:end]
    # A where clause may be wrapped onto its own line.
    sig = re.split(r"\bwhere\b", sig, maxsplit=1)[0]
    if "->" not in sig:
        return "()"
    return " ".join(sig.split("->", 1)[1].split())


class _Rust:
    """The Python names the Rust declares, and the return type of each."""

    def __init__(self) -> None:
        # Rust type name to Python class name.
        self.pyclass: dict[str, str] = {}
        # (Python class, method) to Rust return types.
        self.methods: dict[tuple[str, str], list[str]] = {}
        # Python function name to Rust return types.
        self.functions: dict[str, list[str]] = {}
        # (Rust type, method, return type), resolved once every class is known.
        self._impl_fns: list[tuple[str, str, str]] = []

    def scan(self, text: str) -> None:
        """Add the classes, methods and functions one Rust file declares."""
        blanked = _blank(text)
        for m in _PYCLASS_RE.finditer(blanked):
            type_def = _TYPE_DEF_RE.search(blanked, m.end())
            if type_def is None:
                continue
            args = text[m.start("args"):m.end("args")] if m.group("args") is not None else ""
            name = _NAME_ARG_RE.search(args)
            self.pyclass[type_def.group("name")] = name.group("name") if name else type_def.group("name")
        for m in _PYMETHODS_RE.finditer(blanked):
            end = _brace_end(blanked, m.end() - 1)
            self._impl_scan(text, blanked, m.group("name"), m.end(), end)
        for m in _PYFUNCTION_RE.finditer(blanked):
            fn = _FN_RE.search(blanked, m.end())
            if fn is None:
                continue
            args = text[m.start("args"):m.end("args")] if m.group("args") is not None else ""
            name = _NAME_ARG_RE.search(args)
            py_name = name.group("name") if name else fn.group("name")
            self.functions.setdefault(py_name, []).append(_return_type(blanked, fn.end() - 1))

    def _impl_scan(self, text: str, blanked: str, rust_type: str, start: int, end: int) -> None:
        """Record each method of the ``#[pymethods]`` block between ``start`` and ``end``."""
        depth = 0
        attrs_start = start
        i = start
        while i < end:
            ch = blanked[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    attrs_start = i + 1
            elif depth == 0 and ch == ";":
                attrs_start = i + 1
            elif depth == 0 and blanked.startswith("fn", i):
                fn = _FN_RE.match(blanked, i)
                if fn is not None:
                    attrs = text[attrs_start:i]
                    if not re.search(r'#\[(getter|setter|classattr)\b', attrs):
                        name = re.search(r'#\[pyo3\([^\]]*\bname\s*=\s*"(\w+)"', attrs)
                        py_name = name.group(1) if name else fn.group("name")
                        self._impl_fns.append((rust_type, py_name, _return_type(blanked, fn.end() - 1)))
                    i = fn.end()
                    continue
            i += 1

    def resolve(self) -> None:
        """Key each method by its class's Python name, once every file is scanned."""
        for rust_type, py_name, ret in self._impl_fns:
            cls = self.pyclass.get(rust_type)
            if cls is not None:
                self.methods.setdefault((cls, py_name), []).append(ret)


def _generic_split(text: str) -> tuple[str, list[str]]:
    """``Name<A, B>`` as ``("Name", ["A", "B"])``, splitting at the top level."""
    text = text.strip()
    open_at = text.find("<")
    if open_at < 0 or not text.endswith(">"):
        return text, []
    return text[:open_at].strip(), [arg for arg in _top_split(text[open_at + 1:-1], ",") if arg]


def _top_split(text: str, sep: str) -> list[str]:
    """Split at ``sep`` outside brackets."""
    parts = []
    depth = 0
    current = ""
    for ch in text:
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return [p.strip() for p in parts]


def _rust_to_py(  # pylint: disable=too-many-return-statements
    rust: str,
    cls: str,
    pyclass: dict[str, str],
) -> str | None:
    """The Python type a Rust return type maps to, ``None`` when it can't be known."""
    rust = rust.strip()
    rust = re.sub(r"&(?:'\w+\s+)?(?:mut\s+)?", "", rust)
    rust = re.sub(r"'\w+\s*,\s*", "", rust)
    if rust in ("()", ""):
        return "None"
    if rust.startswith("(") and rust.endswith(")"):
        items = [_rust_to_py(item, cls, pyclass) for item in _top_split(rust[1:-1], ",") if item]
        if any(item is None for item in items):
            return None
        return "tuple[{:s}]".format(", ".join(item for item in items if item is not None))
    name, args = _generic_split(rust)
    name = name.rsplit("::", 1)[-1]
    if name in _UNTYPED:
        return None
    if name in _TRANSPARENT:
        return _rust_to_py(args[-1], cls, pyclass) if args else None
    if name == "Option" and args:
        inner = _rust_to_py(args[0], cls, pyclass)
        return None if inner is None else "{:s} | None".format(inner)
    if name == "Vec" and args:
        inner = _rust_to_py(args[0], cls, pyclass)
        return None if inner is None else "list[{:s}]".format(inner)
    if name == "bool":
        return "bool"
    if name in _INT:
        return "int"
    if name in _FLOAT:
        return "float"
    if name in _STR:
        return "str"
    if name == "Self":
        return cls
    return pyclass.get(name)


def _rst_normalize(rst: str, cls: str) -> str:
    """An RST ``:rtype:`` with roles, module paths and literal values removed."""
    text = re.sub(r":\w+:`~?([^`]+)`", r"\1", rst)
    text = re.sub(r"\b(?:\w+\.)+(\w+)", r"\1", text)
    text = re.sub(r'Literal\[\s*["\'].*?\]', "str", text)
    text = re.sub(r"Literal\[[^\]]*\]", "int", text)
    text = re.sub(r"\bSelf\b", cls, text)
    return _type_canon(text)


def _type_canon(text: str) -> str:
    """A type with its unions sorted and duplicates dropped, so order is ignored."""
    members = []
    for member in _top_split(text, "|"):
        if "[" in member and member.endswith("]"):
            head = member[:member.index("[")].strip()
            inner = member[member.index("[") + 1:-1]
            member = "{:s}[{:s}]".format(head, ", ".join(_type_canon(arg) for arg in _top_split(inner, ",")))
        members.append(" ".join(member.split()))
    return " | ".join(sorted(set(members)))


def _rst_scan(path: str) -> list[tuple[str | None, str, str, int]]:
    """Each documented ``(class, name, rtype, line)`` in a generated RST file."""
    entries = []
    cls: str | None = None
    # The method or function whose `:rtype:` comes next, with its class and line.
    current_cls: str | None = None
    current_name: str | None = None
    current_line = 0
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if m := re.match(r"\.\. class:: (\w+)", line):
                cls = m.group(1)
                current_name = None
            elif m := re.match(r"\.\. function:: (\w+)\(", line):
                cls = None
                current_cls, current_name, current_line = None, m.group(1), lineno
            elif m := re.match(r"\s+\.\. (?:method|staticmethod|classmethod):: (\w+)\(", line):
                current_cls, current_name, current_line = cls, m.group(1), lineno
            elif re.match(r"\s*\.\. \w+::", line):
                current_name = None
            elif (m := re.match(r"\s+:rtype: (.+)", line)) and current_name is not None:
                entries.append((current_cls, current_name, m.group(1).strip(), current_line))
                current_name = None
    return entries


def main() -> int:
    """Report each documented return type the Rust disagrees with."""
    rust = _Rust()
    for filename in sorted(os.listdir(_RUST_DIR)):
        if filename.endswith(".rs"):
            with open(os.path.join(_RUST_DIR, filename), encoding="utf-8") as fh:
                rust.scan(fh.read())
    rust.resolve()

    if not os.path.isdir(_RST_DIR):
        print("check_rtype: no generated RST in {:s}, build the docs first".format(_RST_DIR), file=sys.stderr)
        return 1

    entries: list[tuple[str, str | None, str, str, int]] = []
    for filename in sorted(os.listdir(_RST_DIR)):
        if filename.startswith("ion") and filename.endswith(".rst"):
            path = os.path.join(_RST_DIR, filename)
            entries.extend((path, *entry) for entry in _rst_scan(path))

    # An overload documents one name twice in one module; its Rust `fn`
    # returns `PyAny`. Keyed by file too, so a function another module also
    # defines is not mistaken for one.
    seen = collections.Counter((path, cls, name) for path, cls, name, _rtype, _lineno in entries)

    checked = 0
    skipped = 0
    errors = []
    for path, cls, name, rtype, lineno in entries:
        if seen[(path, cls, name)] > 1 or rtype.startswith("Iterator["):
            skipped += 1
            continue
        rets = rust.methods.get((cls, name)) if cls is not None else rust.functions.get(name)
        expected = None
        source = ""
        if rets and len(set(rets)) == 1:
            expected = _rust_to_py(rets[0], cls or "", rust.pyclass)
            source = "Rust returns " + rets[0]
        if expected is None and cls is not None and name in _DATA_MODEL:
            expected = _DATA_MODEL[name] or cls
            source = "the data model fixes it"
        if expected is None:
            skipped += 1
            continue
        checked += 1
        documented = _rst_normalize(rtype, cls or "")
        if documented != _type_canon(expected):
            errors.append("{:s}:{:d}: {:s}: documented {!r}, expected {!r} ({:s})".format(
                path, lineno, "{:s}.{:s}".format(cls, name) if cls else name, rtype, expected, source,
            ))

    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print("check_rtype: {:d} of {:d} checked return types disagree".format(len(errors), checked), file=sys.stderr)
        return 1
    print("check_rtype: {:d} return types match, {:d} not checkable".format(checked, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
