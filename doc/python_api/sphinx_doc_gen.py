#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Generate Sphinx RST documentation from ion module docstrings.

This script introspects the ion Python module and extracts all docstrings
to create RST files suitable for Sphinx documentation.

Based on patterns from Blender's sphinx_doc_gen.py.
"""

__all__ = (
    "main",
)

import sys
from collections.abc import Callable
from pathlib import Path
from types import (
    BuiltinFunctionType,
    BuiltinMethodType,
    FunctionType,
    MemberDescriptorType,
    ModuleType,
    UnionType,
)
from typing import NamedTuple

_SCRIPT_DIR = Path(__file__).parent
_EXAMPLES_DIR = _SCRIPT_DIR / "examples"
_RST_DIR = _SCRIPT_DIR / "rst"
# Hand-written narrative pages, grouped by the sidebar caption they appear
# under in the index toctree. Each group names its source subdirectory under
# `rst/` and its pages in order; every page maps to `rst/<subdir>/<name>.rst`,
# copied verbatim into the build directory so Sphinx treats it as a top-level
# document.
_GUIDE_SECTIONS = (
    ("Getting Started", "getting_started", (
        "configure",
        "install",
    )),
    ("Guide", "guide", (
        "features",
        "command_line",
    )),
)

# Trees copied verbatim into the build directory so guide pages can
# `.. literalinclude::` files inside them. Paths are relative to the repository
# root and preserved under the build directory, so guide pages reference files
# by that same path (e.g. `config/default/ion_init.py`). `_SCRIPT_DIR` is
# `doc/python_api`, so `parents[1]` is the repository root.
_REPO_ROOT = _SCRIPT_DIR.parents[1]
_GUIDE_ASSETS = (
    "config",
)

# Command-line `--help` pages captured from the built binaries at generation
# time, keyed by the build-directory filename a guide page `.. literalinclude::`s.
# Each names the command line to add `--help` to, a sub-command having help of
# its own.
_CMDLINE_HELP = (
    ("ionwl_help.txt", ("ionwl",)),
    ("ionwl_cmd_help.txt", ("ionwl-cmd",)),
    ("ionwl_cmd_ping_help.txt", ("ionwl-cmd", "ping")),
    ("ionwl_cmd_python_eval_help.txt", ("ionwl-cmd", "python-eval")),
    ("ionwl_cmd_python_exec_help.txt", ("ionwl-cmd", "python-exec")),
    ("ionwl_cmd_python_file_help.txt", ("ionwl-cmd", "python-file")),
)

# Hand-written static assets (CSS) copied into `build/static/`, which
# `conf.py` registers as `html_static_path`.
_STATIC_DIR = _SCRIPT_DIR / "static"

# Hand-written Sphinx config, copied into the build directory and templated
# with `${IONWL_VERSION}` substituted from `Cargo.toml`.
_CONF_PY = _SCRIPT_DIR / "conf.py"


# ----------------------------------------------------------------------------
# Mutable State

class _State:  # pylint: disable=too-few-public-methods
    """Mutable counters and flags shared across the documentation pass."""

    # Issues during generation (e.g. failed module imports), each reported as
    # it is found. `main()` returns non-zero when this is greater than zero.
    error_count: int = 0
    verbose: bool = False
    # When true, suppress progress output and print only errors/warnings.
    quiet: bool = False
    # When true, soft warnings (e.g. unused examples) are promoted to errors.
    strict: bool = False


# Descriptor types not directly exposed by Python, access indirectly.
_ClassMethodDescriptorType = type(dict.__dict__["fromkeys"])
_MethodDescriptorType = type(dict.get)
_GetSetDescriptorType = type(int.real)
_StaticMethodType = type(staticmethod(lambda: None))
_WrapperDescriptorType = type(object.__init__)

# `Py_TPFLAGS_BASETYPE`: set on a type that can be subclassed.
_TPFLAGS_BASETYPE = 1 << 10


_RST_TRANS = str.maketrans({
    "`": "\\`",
    "|": "\\|",
    "*": "\\*",
    "\\": "\\\\",
})


class _DunderParam(NamedTuple):
    """A documented parameter on a dunder method: RST type and description."""
    param_type: str
    description: str


class _DunderOverload(NamedTuple):
    """A single ``@overload`` entry: operand type and return type (RST)."""
    operand_type: str
    return_type: str


class _DunderInfo(NamedTuple):
    """Everything we know about a dunder (protocol) method.

    Used as a base entry (in :data:`_DUNDER_METHODS`, all fields populated)
    and as a per-class partial override (in :data:`_CLASS_OVERRIDES`, only the
    set fields applied via :func:`_merge_dunder_info`). All fields are optional
    so overrides can specify just what they change.

    - ``signature``: bracketed parameter list inserted into the directive
      (e.g. ``"(self, other)"``, ``"(self)"``).
    - ``params``: maps each non-``self`` parameter name to a :class:`_DunderParam`.
    - ``return_type``: RST rtype string. The literal ``"self"`` expands to
      the enclosing class as ``:class:`Name```; ``""`` omits ``:rtype:``
      entirely.
    - ``overloads``: when set, emit one ``.. method::`` directive per entry
      (subsequent entries use ``:noindex:``); the stub generator turns these
      into ``@overload`` declarations.
    """
    signature: str | None = None
    params: dict[str, _DunderParam] | None = None
    return_type: str | None = None
    overloads: list[_DunderOverload] | None = None


def _merge_dunder_info(base: _DunderInfo, override: _DunderInfo | None) -> _DunderInfo:
    """Apply *override* over *base*; ``None`` fields on the override inherit from base."""
    if override is None:
        return base
    return base._replace(**{
        field: value for field, value in override._asdict().items() if value is not None
    })


# Signatures for dunder (protocol) methods to include in documentation.
# Signatures use `(self, ...)` form to match the rest of ionwl's method
# emission. `__getitem__` / `__setitem__` rtype is empty by default since
# ionwl has no uniform element type; override per class via `_CLASS_OVERRIDES`.
_OTHER_OPERAND = {"other": _DunderParam("Self", "The other operand.")}
_DUNDER_METHODS: dict[str, _DunderInfo] = {
    # Binary arithmetic operators.
    "__add__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__radd__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__sub__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__rsub__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__mul__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__rmul__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__truediv__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__rtruediv__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__floordiv__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__rfloordiv__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__matmul__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__rmatmul__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    # Unary operators.
    "__neg__": _DunderInfo("(self)", {}, "self"),
    "__pos__": _DunderInfo("(self)", {}, "self"),
    "__abs__": _DunderInfo("(self)", {}, "self"),
    "__invert__": _DunderInfo("(self)", {}, "self"),
    # In-place arithmetic operators.
    "__iadd__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__isub__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__imul__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__itruediv__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__ifloordiv__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    "__imatmul__": _DunderInfo("(self, other)", _OTHER_OPERAND, "self"),
    # Comparison and hashing. `__eq__` / `__ne__` must accept `object`
    # to satisfy the Liskov substitution rule mypy enforces for these slots.
    "__eq__": _DunderInfo(
        "(self, other)",
        {"other": _DunderParam("object", "The object to compare against.")},
        "bool",
    ),
    "__ne__": _DunderInfo(
        "(self, other)",
        {"other": _DunderParam("object", "The object to compare against.")},
        "bool",
    ),
    # `__lt__`, `__le__`, `__gt__` and `__ge__` are deliberately absent.
    # CPython serves all six comparisons from one `tp_richcompare` slot, so a
    # PyO3 class defining `__eq__` lists the ordering four in `dir()` as well,
    # and documenting what `dir()` reports would promise an ordering that
    # raises `TypeError` when called - `keyboard_a <= keyboard_b` is not a
    # question with an answer. Add an entry here if a type ever implements
    # them for real.
    "__hash__": _DunderInfo("(self)", {}, "int"),
    # Container protocol.
    "__len__": _DunderInfo("(self)", {}, "int"),
    "__getitem__": _DunderInfo(
        "(self, key)", {"key": _DunderParam("int", "Index or key.")}, "",
    ),
    "__setitem__": _DunderInfo("(self, key, value)", {
        "key": _DunderParam("int", "Index or key."),
        "value": _DunderParam("object", "Value to assign."),
    }, ""),
    "__contains__": _DunderInfo(
        "(self, item)",
        {"item": _DunderParam("object", "Item to test for membership.")},
        "bool",
    ),
    # String representation.
    "__repr__": _DunderInfo("(self)", {}, "str"),
    "__str__": _DunderInfo("(self)", {}, "str"),
    "__format__": _DunderInfo(
        "(self, format_spec)",
        {"format_spec": _DunderParam(
            "str",
            "Format spec applied per component (empty spec returns ``repr(self)``).",
        )},
        "str",
    ),
    # Iteration.
    "__iter__": _DunderInfo("(self)", {}, "Iterator"),
    # Context manager protocol.
    "__enter__": _DunderInfo("(self)", {}, "self"),
    "__exit__": _DunderInfo("(self, exc_type, exc_value, traceback)", {
        "exc_type": _DunderParam("type | None", "Exception type, or ``None``."),
        "exc_value": _DunderParam("BaseException | None", "Exception instance, or ``None``."),
        "traceback": _DunderParam("BaseException | None", "Traceback object, or ``None``."),
    }, "bool"),
    # `copy` module protocol.
    "__copy__": _DunderInfo("(self)", {}, "self"),
    "__deepcopy__": _DunderInfo(
        "(self, memo)",
        {"memo": _DunderParam("dict", "Memoization dict for shared subobjects.")},
        "self",
    ),
    # `typing` / PEP 560 subscript protocol. The runtime returns a
    # `types.GenericAlias`; stub consumers treat it as `Any` because
    # mypy handles subscripts via `Generic[T]` rather than this method.
    "__class_getitem__": _DunderInfo(
        "(cls, item)",
        {"item": _DunderParam("Any", "Type parameter; ignored at runtime.")},
        "Any",
    ),
}
del _OTHER_OPERAND


class _ClassOverrides(NamedTuple):
    """Per-class customizations applied during RST generation. All fields optional."""
    # Per-dunder partial overrides merged onto `_DUNDER_METHODS` entries.
    # `None` fields on the override inherit from the base.
    dunders: dict[str, _DunderInfo] | None = None


# Add per-class dunder overrides as needed, e.g.:
#   ("ion.types", "Point"): _ClassOverrides(dunders={
#       "__add__": _DunderInfo(overloads=[
#           _DunderOverload(":class:`Point`", ":class:`Point`"),
#           _DunderOverload(":class:`Size` | tuple[int, int]", ":class:`Point`"),
#       ]),
#   }),
_CLASS_OVERRIDES: dict[tuple[str, str], _ClassOverrides] = {
    # Hook is parametric (`Hook(Generic[T])`); the default `__iter__` rtype
    # `Iterator` is untyped, so spell out `Iterator[T]` here.
    ("ion.types", "Hook"): _ClassOverrides(dunders={
        "__iter__": _DunderInfo(None, None, "Iterator[T]"),
    }),
}
_EMPTY_CLASS_OVERRIDES = _ClassOverrides()


def _escape_rst(text: str | None) -> str:
    """Escape plain text which may contain characters used by RST."""
    if text is None:
        return ""
    return text.translate(_RST_TRANS)


def _fully_qualified_name(cls: type) -> str:
    """Get fully qualified name for a class (e.g., 'ion.types.Preferences')."""
    module = getattr(cls, "__module__", None)
    name = cls.__name__
    if module and module.startswith("ion"):
        return "{:s}.{:s}".format(module, name)
    return name


def _title_string(text: str, heading_char: str, double: bool = False) -> str:
    """Generate an RST title with underline (and optional overline)."""
    filler = len(text) * heading_char
    if double:
        # pylint: disable-next=duplicate-string-formatting-argument
        return "{:s}\n{:s}\n{:s}\n\n".format(filler, text, filler)
    return "{:s}\n{:s}\n\n".format(text, filler)


def _write_indented_lines(ident: str, fw: Callable[[str], object], text: str | None, strip: bool = True) -> None:
    """
    Write text with consistent indentation.

    """
    if text is None:
        return

    lines = text.split("\n")

    # Strip empty lines from the start/end.
    while lines and not lines[0].strip():
        del lines[0]
    while lines and not lines[-1].strip():
        del lines[-1]

    if strip:
        # Normalize indentation to match ident.
        ident_strip = 1000
        for line in lines:
            if line.strip():
                ident_strip = min(ident_strip, len(line) - len(line.lstrip()))
        for line in lines:
            fw(ident + line[ident_strip:] + "\n")
    else:
        # Add ident to existing indentation.
        for line in lines:
            fw(ident + line + "\n")


# Populated by main() from filenames in EXAMPLES_DIR.
_EXAMPLE_SET: set[str] = set()

# Tracks which examples were actually referenced during generation.
_EXAMPLES_USED: set[str] = set()

# Qualified names of the documented classes that cannot be subclassed.
_FINAL_CLASSES: set[str] = set()

# Qualified names of the documented classes constructed by `__new__` alone, as
# PyO3 and `NamedTuple` classes are.
_NEW_CLASSES: set[str] = set()

# Each documented module's `__all__`, by module name.
_MODULE_ALL: dict[str, list[str]] = {}


def _example_extract_docstring(filepath: Path) -> tuple[str, int, bool]:
    """Extract the leading triple-quoted docstring from an example file.

    Returns ``(docstring_text, code_line_no, line_no_has_content)`` where
    *code_line_no* is the 1-based line number where the code starts (the
    first line after the closing ``\"\"\"``), and *line_no_has_content* is
    True when that line is non-blank.

    """
    lines = filepath.read_text(encoding="utf-8").splitlines()
    # Find opening triple-quote.
    line_no = 0
    if not lines or not lines[0].startswith('"""'):
        return ("", 1, bool(lines))
    # Collect docstring body (skip the opening """).
    doc_lines: list[str] = []
    for i in range(1, len(lines)):
        if lines[i].startswith('"""'):
            line_no = i + 2  # 1-based, line after closing """
            break
        doc_lines.append(lines[i])
    else:
        # Never closed - treat entire file as code.
        return ("", 1, bool(lines))

    text = "\n".join(doc_lines)
    has_content = line_no <= len(lines) and bool(lines[line_no - 1].strip())
    return (text, line_no, has_content)


def _write_example_ref_impl(ident: str, fw: Callable[[str], object], example_id: str) -> None:
    """Write RST for a single example file *example_id* (without ``.py``).

    Extracts the leading docstring and emits it as RST, followed by a
    ``.. literalinclude::`` directive pointing at the example source.
    """
    filepath = _EXAMPLES_DIR / "{:s}.py".format(example_id)
    if not filepath.exists():
        return

    _EXAMPLES_USED.add(example_id)

    text, line_no, _line_no_has_content = _example_extract_docstring(filepath)

    if text:
        _write_indented_lines(ident, fw, text)
        fw("\n")

    # Path relative from the build/ output directory.
    fw("{:s}.. literalinclude:: ../examples/{:s}.py\n".format(ident, example_id))
    if line_no > 1:
        fw("{:s}   :lines: {:d}-\n".format(ident, line_no))
    fw("\n")


def _write_example_ref(ident: str, fw: Callable[[str], object], example_id: str) -> None:
    """Write RST for all numbered example files matching *example_id*.

    Looks for ``example_id.0``, ``example_id.1``, ... in :data:`_EXAMPLE_SET`
    and emits each one via :func:`_write_example_ref_impl`.
    """
    index = 0
    while True:
        numbered = "{:s}.{:d}".format(example_id, index)
        if numbered not in _EXAMPLE_SET:
            break
        _write_example_ref_impl(ident, fw, numbered)
        index += 1


def _strip_text_fences(text: str) -> str:
    """Strip markdown ```text / ``` fences that wrap RST content.

    These fences are added to Rust ``///`` doc comments to suppress
    rustdoc doctests. Remove them so the RST parses cleanly.
    Only strips when both the opening and closing fence are present.
    """
    open_tag = "```text\n"
    close_tag = "\n```"
    i = text.find(open_tag)
    if i == -1:
        return text
    j = text.rfind(close_tag)
    if j <= i:
        return text
    if text[:i].lstrip():
        raise ValueError("unexpected content before ```text fence")
    if text[j + len(close_tag):].lstrip():
        raise ValueError("unexpected content after ``` fence")
    return text[i + len(open_tag):j]


def _undocumented_report(obj: object, module_name: str, identifier: str) -> None:
    """Report an attribute written as "Undocumented.", an error under ``--strict-docs``."""
    if _State.strict:
        print(
            "Error: {:s}.{:s} is undocumented".format(module_name, getattr(obj, "__qualname__", identifier)),
            file=sys.stderr,
        )
        _State.error_count += 1


def _strip_rst_method_blocks(text: str) -> str:
    """Strip ``.. method::`` directive blocks from a docstring.

    Used when writing data-item docs where the methods are already
    documented on the class page linked via the ``:type:`` field.
    """
    i = text.find("\n.. method:: ")
    if i == -1:
        return text
    return text[:i].rstrip()


def _strip_embedded_signature(doc: object, dunder_key: str = "") -> str | None:
    """Strip PyO3's embedded signature from the beginning of a docstring.

    PyO3 format: 'func_name(params) -> return_type\\n--\\n\\nActual docstring'

    When *dunder_key* is given (e.g. ``"__len__"``), also discard CPython's
    auto-generated default for protocol slots (e.g. ``"Return len(self)."``).
    PyO3 maps these to CPython C slots (e.g. ``sq_length``), and CPython
    creates a ``wrapper_descriptor`` with its own hardcoded docstring,
    ignoring any ``///`` doc-comment on the Rust method.
    """
    # Ensure doc is a string (some PyO3 classes have __doc__ as descriptor)
    if not isinstance(doc, str):
        return None
    if "\n--\n" in doc:
        # The actual docstring starts after the '--' separator
        doc = doc.split("\n--\n", 1)[1].lstrip("\n")
    if dunder_key and doc == "Return {:s}(self).".format(dunder_key.strip("_")):
        return None
    return doc


def _py_c_func2sphinx(
        ident: str,
        fw: Callable[[str], object],
        module_name: str,
        identifier: str,
        py_func: object,
) -> None:
    """
    Write RST for a C/Rust-defined function (PyO3).

    """
    doc = _strip_embedded_signature(py_func.__doc__)
    if doc:
        _write_indented_lines(ident, fw, doc, False)
        fw("\n")
    else:
        fw("{:s}.. function:: {:s}{:s}\n\n".format(ident, identifier, _get_func_signature(py_func)))
        fw("{:s}   Undocumented.\n\n".format(ident))
        _undocumented_report(py_func, module_name, identifier)


def _py_descr2sphinx(
        ident: str, fw:
        Callable[[str], object],
        module_name: str,
        descr: object,
        identifier: str,
) -> None:
    """
    Write RST for a descriptor (property/method).

    """
    if identifier.startswith("_"):
        return

    doc = descr.__doc__
    descr_type = type(descr)

    if descr_type in {_GetSetDescriptorType, MemberDescriptorType}:
        is_getset = descr_type == _GetSetDescriptorType
        writable = is_getset and _import_module("ion._internal").getset_writable(descr)
        # Written as `_pyprop2sphinx` writes a property.
        fw("{:s}.. {:s}:: {:s}\n\n".format(ident, "attribute" if writable else "data", identifier))
        if doc:
            _write_indented_lines(ident + "   ", fw, doc, False)
        else:
            fw("{:s}   Undocumented.\n".format(ident))
            _undocumented_report(descr, module_name, identifier)
        fw("\n")
        if is_getset and not writable:
            fw("{:s}   (readonly)\n".format(ident))
            fw("\n")
    elif descr_type in {_MethodDescriptorType, _ClassMethodDescriptorType}:
        doc = _strip_embedded_signature(doc)
        if doc:
            _write_indented_lines(ident, fw, doc, False)
            fw("\n")
        else:
            if descr_type == _ClassMethodDescriptorType:
                fw("{:s}.. classmethod:: {:s}{:s}\n\n".format(ident, identifier, _get_func_signature(descr)))
            else:
                fw("{:s}.. method:: {:s}{:s}\n\n".format(ident, identifier, _get_func_signature(descr)))
            fw("{:s}   Undocumented.\n\n".format(ident))
            _undocumented_report(descr, module_name, identifier)
    else:
        raise TypeError("type {:s} not default supported".format(str(descr_type)))


def _pyprop2sphinx(ident: str, fw: Callable[[str], object], identifier: str, py_prop: property) -> None:
    """
    Write RST for a Python property.

    """
    # Read-only properties use "data" directive, writable use "attribute".
    if py_prop.fset is None:
        fw("{:s}.. data:: {:s}\n\n".format(ident, identifier))
    else:
        fw("{:s}.. attribute:: {:s}\n\n".format(ident, identifier))

    if py_prop.__doc__:
        _write_indented_lines(ident + "   ", fw, py_prop.__doc__)
    fw("\n")

    if py_prop.fset is None:
        fw("{:s}   (readonly)\n".format(ident))
        fw("\n")


def _write_dunder_methods(
    fw: Callable[[str], object],
    cls: type,
    module_name: str,
    type_name: str,
    class_doc: str = "",
) -> None:
    """Emit known dunder (protocol) methods defined on this type.

    For each dunder present on *cls*, emit a ``.. method::`` directive with
    the docstring body (if any) followed by structured ``:param:`` /
    ``:type:`` / ``:rtype:`` fields drawn from :data:`_DUNDER_METHODS` and any
    per-class entry in :data:`_CLASS_OVERRIDES`. Dunders already documented
    in *class_doc* (manual ``.. method::`` blocks) are skipped.
    """
    # A dunder counts as defined here when it appears directly in
    # `cls.__dict__` with a non-`None` value. Inherited dunders are
    # documented on the defining base; a `None` entry (e.g. an explicit
    # `__hash__ = None`) marks the type as opting out and is skipped.
    dunder_keys = {
        key for key in _DUNDER_METHODS
        if cls.__dict__.get(key) is not None
    }
    if not dunder_keys:
        return

    overrides = _CLASS_OVERRIDES.get((module_name, type_name), _EMPTY_CLASS_OVERRIDES)
    class_dunders = overrides.dunders or {}

    # Wrap in a `.. details::` block (registered in conf.py) so the protocol
    # methods are nested in an HTML `<details>` drop-down. The stub
    # generator treats this directive as transparent.
    fw("   .. details:: Special Methods\n\n")

    for key in sorted(dunder_keys):
        # Skip if already documented in the class docstring.
        if class_doc and ".. method:: {:s}(".format(key) in class_doc:
            continue

        info = _merge_dunder_info(_DUNDER_METHODS[key], class_dunders.get(key))
        # Base entries always populate the first three fields, so non-None here.
        assert info.signature is not None
        assert info.params is not None
        assert info.return_type is not None

        descr = cls.__dict__.get(key)
        body_doc: str | None = None
        if descr is not None:
            body_doc = _strip_embedded_signature(getattr(descr, "__doc__", None), dunder_key=key)

        if info.overloads is not None:
            assert len(info.params) == 1, "dunder overloads only support a single param"
            (pname, param), = info.params.items()
            for i, overload in enumerate(info.overloads):
                fw("      .. method:: {:s}{:s}\n".format(key, info.signature))
                if i > 0:
                    fw("         :noindex:\n")
                fw("\n")
                # Emit body doc once on the first overload.
                if i == 0 and body_doc:
                    _write_indented_lines("         ", fw, body_doc, True)
                    fw("\n")
                fw("         :param {:s}: {:s}\n".format(pname, param.description))
                fw("         :type {:s}: {:s}\n".format(pname, overload.operand_type))
                fw("         :rtype: {:s}\n\n".format(overload.return_type))
            continue

        # Signatures starting with `(cls` describe classmethod-bound dunders
        # (e.g. `__class_getitem__`); emit a `.. classmethod::` directive so
        # the stub generator marks them with `@classmethod`.
        directive = "classmethod" if info.signature.startswith("(cls") else "method"
        fw("      .. {:s}:: {:s}{:s}\n\n".format(directive, key, info.signature))
        if body_doc:
            _write_indented_lines("         ", fw, body_doc, True)
            fw("\n")
        for pname, param in info.params.items():
            fw("         :param {:s}: {:s}\n".format(pname, param.description))
            fw("         :type {:s}: {:s}\n".format(pname, param.param_type))
        rtype = info.return_type
        if rtype == "self":
            fw("         :rtype: :class:`{:s}`\n\n".format(type_name))
        elif rtype:
            fw("         :rtype: {:s}\n\n".format(rtype))
        else:
            fw("\n")


def _find_class_instance(cls: type) -> object | None:
    """Find a live instance of *cls* across known ion modules."""
    for module_name in _get_module_tree():
        try:
            module = _import_module(module_name)
        except (ImportError, AttributeError):
            continue
        for name in dir(module):
            try:
                obj = getattr(module, name)
            except AttributeError:
                continue
            if isinstance(obj, cls):
                return obj
    return None


def _pyclass2sphinx(
    fw: Callable[[str], object],
    module_name: str,
    type_name: str,
    cls: type,
) -> None:
    """
    Write RST for a class.

    """
    # Class declaration - strip embedded signature from docstring
    class_doc = cls.__doc__
    if class_doc:
        class_doc = _strip_embedded_signature(class_doc)

    qualified_name = "{:s}.{:s}".format(module_name, type_name)
    if not cls.__flags__ & _TPFLAGS_BASETYPE:
        _FINAL_CLASSES.add(qualified_name)
    if "__new__" in cls.__dict__ and "__init__" not in cls.__dict__:
        _NEW_CLASSES.add(qualified_name)

    if class_doc:
        class_doc = _strip_text_fences(class_doc)
        if class_doc.startswith(".. class::"):
            fw(class_doc)
        else:
            fw(".. class:: {:s}\n\n".format(type_name))
            _write_indented_lines("   ", fw, class_doc, True)
        fw("\n\n")
    else:
        fw(".. class:: {:s}\n\n".format(type_name))

    # Get descriptors from class __dict__ to properly identify types.
    # Dunder methods are handled separately by write_dunder_methods.
    descr_items = [
        (key, descr)
        for key, descr in sorted(cls.__dict__.items())
        if not key.startswith("_")
    ]

    # Class method descriptors
    for key, descr in descr_items:
        if type(descr) == _ClassMethodDescriptorType:
            _py_descr2sphinx("   ", fw, module_name, descr, key)

    # Pure Python classmethods (classmethod wrapper)
    for key, descr in descr_items:
        if type(descr) == classmethod:
            actual_func = getattr(cls, key)
            if type(actual_func) in {BuiltinMethodType, BuiltinFunctionType}:
                _py_c_func2sphinx("   ", fw, module_name, key, actual_func)
            else:
                fw("   .. classmethod:: {:s}{:s}\n\n".format(key, _get_func_signature(actual_func)))
                doc = actual_func.__doc__
                if doc:
                    _write_indented_lines("      ", fw, doc, True)
                fw("\n")

    # Regular functions (pure Python methods)
    for key, descr in descr_items:
        if type(descr) == FunctionType:
            fw("   .. method:: {:s}{:s}\n\n".format(key, _get_func_signature(descr)))
            if descr.__doc__:
                _write_indented_lines("      ", fw, descr.__doc__, True)
            fw("\n")

    # Method descriptors (C/Rust methods)
    for key, descr in descr_items:
        if type(descr) == _MethodDescriptorType:
            _py_descr2sphinx("   ", fw, module_name, descr, key)

    # Getset and member descriptors (properties defined in C/Rust)
    for key, descr in descr_items:
        if type(descr) in {_GetSetDescriptorType, MemberDescriptorType}:
            _py_descr2sphinx("   ", fw, module_name, descr, key)

    # Python properties
    for key, descr in descr_items:
        if type(descr) == property:
            _pyprop2sphinx("   ", fw, key, descr)

    # Static methods
    for key, descr in descr_items:
        if type(descr) == _StaticMethodType:
            actual_func = getattr(cls, key)
            if type(actual_func) in {BuiltinMethodType, BuiltinFunctionType}:
                doc = _strip_embedded_signature(actual_func.__doc__)
                if doc:
                    _write_indented_lines("   ", fw, doc, False)
                    fw("\n")
            else:
                fw("   .. staticmethod:: {:s}{:s}\n\n".format(key, _get_func_signature(actual_func)))
                doc = actual_func.__doc__
                if doc:
                    doc = _strip_embedded_signature(doc)
                    _write_indented_lines("      ", fw, doc, True)
                fw("\n")

    # Builtin methods (PyO3 #[pymethods])
    for key, descr in descr_items:
        if type(descr) in {BuiltinMethodType, BuiltinFunctionType}:
            _py_c_func2sphinx("   ", fw, module_name, key, descr)

    # Class attributes (simple constant values, not descriptors)
    # These are simple values, not descriptors
    handled_types = {
        _ClassMethodDescriptorType, _MethodDescriptorType, _GetSetDescriptorType,
        MemberDescriptorType, FunctionType, property, classmethod, _StaticMethodType,
        BuiltinMethodType, BuiltinFunctionType, _WrapperDescriptorType,
    }
    class_attrs = [
        (key, descr) for key, descr in descr_items
        if type(descr) not in handled_types and not callable(descr) and key.isidentifier()
    ]
    for key, value in class_attrs:
        fw("   .. attribute:: {:s}\n\n".format(key))
        # A constant is typed by its value, so it passes where a `Literal`
        # admitting that value is expected.
        if type(value) in (str, int, bool):
            type_str = "Literal[{:s}]".format(repr(value))
        else:
            type_str = type(value).__name__
        fw("      :type: {:s}\n".format(type_str))
        fw("      :value: {:s}\n".format(_escape_rst(repr(value))))
        fw("\n")

    # Dunder (protocol) methods with structured signatures and return types.
    _write_dunder_methods(fw, cls, module_name, type_name, class_doc or "")

    # Dynamic attributes discovered via custom __dir__ (e.g. HooksRegistry hooks).
    if "__dir__" in cls.__dict__:
        instance = _find_class_instance(cls)
        if instance is not None:
            for attr_name in sorted(dir(instance)):
                if attr_name.startswith("_"):
                    continue
                try:
                    attr = getattr(instance, attr_name)
                except AttributeError:
                    continue
                doc = getattr(attr, "__doc__", None)
                if not doc:
                    continue
                doc = _strip_rst_method_blocks(doc)
                fw("   .. attribute:: {:s}\n\n".format(attr_name))
                _write_indented_lines("      ", fw, doc, False)
                fw("\n")

    fw("\n\n")


def _get_func_signature(func: object) -> str:
    """Get function signature, preferring __text_signature__ for PyO3.

    PyO3 puts type-annotated signatures in __doc__ when they contain
    syntax it can't parse (like 'str | None'). Format is:
    'func_name(params) -> return_type\\n--\\n\\nActual docstring'
    """
    # First check for signature embedded in __doc__ (PyO3 format)
    # This takes priority because it may contain type annotations
    doc = getattr(func, "__doc__", None)
    if isinstance(doc, str) and "\n--\n" in doc:
        # Extract signature from start of docstring
        sig_line = doc.split("\n--\n", 1)[0].strip()
        # Format: "func_name(params) -> return" or "func_name(params)"
        # We want just "(params) -> return" or "(params)"
        if "(" in sig_line:
            sig = sig_line[sig_line.index("("):]
            # PyO3 uses $self, Python convention is self
            return sig.replace("$self", "self")

    # Fall back to __text_signature__ (without type annotations)
    text_sig = getattr(func, "__text_signature__", None)
    if isinstance(text_sig, str) and text_sig:
        # PyO3 uses $self, Python convention is self
        return text_sig.replace("$self", "self")

    # Fall back to inspect.signature for pure Python functions.
    import inspect  # pylint: disable=import-outside-toplevel
    try:
        return str(inspect.signature(func))  # type: ignore[arg-type]
    except (ValueError, TypeError):
        pass

    return "()"


def _pymodule2sphinx(
    basepath: Path,
    module_name: str,
    module: object,
    submodules: list[str] | None = None,
    orphan: bool = False,
) -> Path:
    """
    Write RST for a module.

    """
    filepath = basepath / "{:s}.rst".format(module_name)

    with open(filepath, "w", encoding="utf-8") as file:
        fw = file.write

        if orphan:
            fw(":orphan:\n\n")

        # Title
        fw(_title_string(module_name, "="))

        # Module directive
        fw(".. module:: {:s}\n\n".format(module_name))

        # Hand-written module description (if present). Emitted before the
        # docstring because a module's __doc__ may end with `.. data::` (and
        # similar) directives, which would push this include below them.
        rst_include = _RST_DIR / "{:s}.rst".format(module_name)
        if rst_include.is_file():
            fw(".. include:: ../rst/{:s}.rst\n\n".format(module_name))

        # Module docstring
        if module.__doc__:
            fw(module.__doc__.strip())
            fw("\n")
            fw("\n")

        # Module-level examples.
        _write_example_ref("", fw, module_name)

        # Submodules toctree. A rubric titles the list without opening a
        # section, so the toctree entries attach to this page rather than to a
        # nested "Submodules" node, letting the index toctree expand them.
        if submodules:
            fw(".. rubric:: Submodules\n\n")
            fw(".. toctree::\n")
            fw("   :maxdepth: 1\n")
            fw("\n")
            for submod_name in sorted(submodules):
                fw("   {:s}.{:s}\n".format(module_name, submod_name))
            fw("\n")

        # Collect module members by type
        classes = []
        functions = []
        operator_items = []
        data_items = []

        module_dir = sorted(dir(module))
        for name in module_dir:
            if name.startswith("_"):
                continue

            try:
                obj = getattr(module, name)
            except AttributeError:
                continue

            if isinstance(obj, ModuleType):
                continue  # Skip submodules.

            if isinstance(obj, UnionType):
                continue  # Skip type aliases (documented in hand-written RST).

            if isinstance(obj, type):
                if hasattr(obj, '_ion_operator_id'):
                    operator_items.append((name, obj))
                else:
                    classes.append((name, obj))
            elif callable(obj):
                functions.append((name, obj))
            else:
                data_items.append((name, obj))

        # Write classes
        if classes:
            fw(_title_string("Classes", "-"))
            for name, cls in classes:
                _pyclass2sphinx(fw, module_name, name, cls)

        # Write functions
        if functions:
            fw(_title_string("Functions", "-"))
            for name, func in functions:
                _py_c_func2sphinx("", fw, module_name, name, func)
                _write_example_ref("   ", fw, module_name + "." + name)

        # Write operators as functions with NamedTuple field signatures.
        if operator_items:
            fw(_title_string("Operators", "-"))
            for name, value in operator_items:
                _write_operator_function(fw, name, value)
                _write_example_ref("   ", fw, module_name + "." + name)

        # Write data/constants (skip items that are submodules).
        submodule_names = set(submodules) if submodules else set()
        data_items_filtered = [(n, v) for n, v in data_items if n not in submodule_names]
        if data_items_filtered:
            fw(_title_string("Data", "-"))
            for name, value in data_items_filtered:
                fw(".. data:: {:s}\n\n".format(name))
                value_type = type(value)
                value_module = getattr(value_type, "__module__", None)
                # Skip __doc__ from builtin instances (bool, int, str) since
                # it describes the type, not this module attribute.
                instance_doc = _strip_embedded_signature(value.__doc__)
                if value_module == "builtins":
                    instance_doc = None
                if instance_doc:
                    # Strip `.. method::` blocks - methods are documented
                    # on the class page linked via `:type:` below.
                    instance_doc = _strip_rst_method_blocks(instance_doc)
                    _write_indented_lines("   ", fw, instance_doc)
                    fw("\n")
                    fw("   :type: :class:`{:s}`\n".format(_fully_qualified_name(value_type)))
                    fw("\n")
                elif value_module and value_module.startswith("ion."):
                    fw("   :type: :class:`{:s}`\n".format(_fully_qualified_name(value_type)))
                    fw("\n")
                else:
                    fw("   :value: {:s}\n".format(_escape_rst(repr(value))))
                    fw("   :type: {:s}\n".format(value_type.__name__))
                fw("\n")
                _write_example_ref("   ", fw, module_name + "." + name)

    return filepath


def _submodules_get(module_name: str, module: object) -> list[str]:
    """Return the public submodule names of *module*, sorted.

    Read off the loaded module rather than listed here, so a submodule
    cannot be added to the API and silently miss its documentation.
    Underscore-prefixed names are private and stay out of the toctree.

    Membership is decided by ``sys.modules``: the attribute counts as a
    submodule when it is the very object registered under the dotted path.
    ``__name__`` cannot serve, because a PyO3 submodule is built with its
    bare name and keeps it; and a plain ``import`` inside the module also
    lands in ``dir()``, so the attribute being a module is not enough.
    """
    subs = []
    for name in dir(module):
        if name.startswith("_"):
            continue
        obj = getattr(module, name, None)
        if not isinstance(obj, ModuleType):
            continue
        if sys.modules.get("{:s}.{:s}".format(module_name, name)) is obj:
            subs.append(name)
    return sorted(subs)


def _get_module_tree() -> tuple[str, ...]:
    """Return every module to generate documentation for.

    Parent/child structure is derived by :func:`_submodules_get`; this only
    decides what gets a page. A public submodule missing from here still
    reaches its parent's toctree, so Sphinx fails on the dangling
    reference rather than dropping it silently.
    """
    return (
        "ion",
        "ion.constants",
        "ion.constants.keys",
        "ion.constants.modifiers",
        "ion.constants.pointer_buttons",
        "ion.constants.event_actions",
        "ion.constants.resize_edges",
        "ion.types",
        "ion.ops",
        "ion.utils",
        "ion.app",
        "ion.app.input",
        "ion.ui",
        "ion.wm",
        # Underscore-prefixed, so no parent toctree lists it. Generated for its
        # stub alone, `conf.py` excludes its page from the published docs.
        "ion._internal",
    )


def _import_module(module_name: str) -> ModuleType:
    """Import a module by its full name."""
    parts = module_name.split(".")
    module = __import__(parts[0])
    for part in parts[1:]:
        module = getattr(module, part)
    return module


def _generate_cmdline_help(output_dir: Path) -> None:
    """Capture each command-line tool's ``--help`` into the build directory.

    The guide pages ``.. literalinclude::`` these by bare name, so writing them
    here (rather than committing a snapshot) keeps the help text in step with
    the binaries. The doc-generation launcher runs ``ionwl`` with its build
    directory first on ``PATH``, so the tools resolve by bare name. ``--help``
    exits before any Wayland connection and prints to stdout; stderr is
    captured too, so a warning printed alongside isn't lost.
    """
    import shutil  # pylint: disable=import-outside-toplevel
    import subprocess  # pylint: disable=import-outside-toplevel

    for filename, (binary_name, *subcommand) in _CMDLINE_HELP:
        binary = shutil.which(binary_name)
        if binary is None:
            print("Warning: command not on PATH for help capture: {:s}".format(binary_name), file=sys.stderr)
            _State.error_count += 1
            continue
        result = subprocess.run(
            [binary, *subcommand, "--help"], capture_output=True, text=True, check=False,
        )
        (output_dir / filename).write_text(result.stdout + result.stderr, encoding="utf-8")
        if _State.verbose:
            print("Generated: {:s}".format(str(output_dir / filename)))


def _copy_guide_pages(output_dir: Path) -> None:
    """Copy hand-written guide pages into the build directory.

    Unlike per-module descriptions (which are inlined via ``.. include::``),
    guide pages are standalone documents referenced from the index toctree,
    so they must exist as real files in the build directory.
    """
    for _caption, subdir, names in _GUIDE_SECTIONS:
        for name in names:
            src = _RST_DIR / subdir / "{:s}.rst".format(name)
            if not src.is_file():
                print("Warning: guide page not found: {:s}".format(str(src)), file=sys.stderr)
                _State.error_count += 1
                continue
            (output_dir / "{:s}.rst".format(name)).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8",
            )
            if _State.verbose:
                print("Generated: {:s}".format(str(output_dir / "{:s}.rst".format(name))))

    import shutil  # pylint: disable=import-outside-toplevel

    for rel_path in _GUIDE_ASSETS:
        src = _REPO_ROOT / rel_path
        if not src.is_dir():
            print("Warning: guide asset not found: {:s}".format(str(src)), file=sys.stderr)
            _State.error_count += 1
            continue
        dest = output_dir / rel_path
        shutil.copytree(
            src, dest,
            ignore=shutil.ignore_patterns("__pycache__"),
            dirs_exist_ok=True,
        )
        if _State.verbose:
            print("Generated: {:s}".format(str(dest)))


def _copy_static_files(output_dir: Path) -> None:
    """Copy hand-written static assets (CSS) into ``build/static/``."""
    if not _STATIC_DIR.is_dir():
        return
    dest = output_dir / "static"
    dest.mkdir(parents=True, exist_ok=True)
    for src in sorted(_STATIC_DIR.iterdir()):
        if src.is_file():
            (dest / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            if _State.verbose:
                print("Generated: {:s}".format(str(dest / src.name)))


def _generate_index_rst(output_dir: Path) -> Path:
    """Generate the index.rst landing page."""
    filepath = output_dir / "index.rst"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_title_string("IonWL Documentation", "=", double=True))

        # Landing prose introducing the two documentation sections below.
        f.write(
            "IonWL is a tiling Wayland compositor configured entirely in Python.\n"
            "\n"
            "The **Getting Started** and **Guide** pages cover how to install,\n"
            "configure, and drive the compositor. The **Python API** section is the\n"
            "full generated reference for the :mod:`ion` module and its submodules.\n"
            "\n"
        )

        # Narrative guides, one toctree per sidebar caption.
        for caption, _subdir, names in _GUIDE_SECTIONS:
            f.write(".. toctree::\n")
            f.write("   :caption: {:s}\n".format(caption))
            f.write("   :maxdepth: 1\n")
            f.write("\n")
            f.writelines("   {:s}\n".format(name) for name in names)
            f.write("\n")

        # Generated module reference.
        f.write(".. toctree::\n")
        f.write("   :caption: Python API\n")
        f.write("   :maxdepth: 2\n")
        f.write("\n")
        f.write("   ion\n")
        f.write("\n")

        # External link to the project's source repository.
        f.write(".. toctree::\n")
        f.write("   :caption: Links\n")
        f.write("\n")
        f.write("   Project Page <https://codeberg.org/ideasman42/IonWL>\n")
        f.write("\n")

        f.write(_title_string("Indices and tables", "="))
        f.write("* :ref:`genindex`\n")
        f.write("* :ref:`modindex`\n")
        f.write("* :ref:`search`\n")
    return filepath


def _cargo_version() -> str:
    """Read the crate version from ``Cargo.toml`` at the repository root."""
    import tomllib  # pylint: disable=import-outside-toplevel

    cargo_toml = _SCRIPT_DIR.parents[1] / "Cargo.toml"
    with open(cargo_toml, "rb") as f:
        data = tomllib.load(f)
    version = data["package"]["version"]
    assert isinstance(version, str)
    return version


def _install_conf_py(output_dir: Path) -> Path:
    """Copy ``conf.py`` into the build directory and substitute placeholders.

    The hand-written ``conf.py`` carries ``${IONWL_VERSION}`` placeholders that
    are filled in here via :class:`string.Template`. Each value is wrapped so
    it closes the surrounding quotes in the template and re-opens as a
    ``repr()`` literal, keeping arbitrary characters safe.
    """
    from string import Template  # pylint: disable=import-outside-toplevel

    def declare_in_quotes(value: str) -> str:
        return '" {!r} "'.format(value)

    substitutions = {
        "IONWL_VERSION": declare_in_quotes(_cargo_version()),
    }

    filepath = output_dir / "conf.py"
    template = _CONF_PY.read_text(encoding="utf-8")
    filepath.write_text(Template(template).substitute(substitutions), encoding="utf-8")
    return filepath


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    import argparse  # pylint: disable=import-outside-toplevel

    parser = argparse.ArgumentParser(
        description="Generate Sphinx RST documentation from the ion module.",
    )
    parser.add_argument(
        "-o", "--output", dest="output_dir",
        default=str(Path(__file__).parent / "build"),
        help="Output directory for generated RST files (default: %(default)s).",
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show per-module progress.",
    )
    verbosity.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress progress output, printing only errors and warnings.",
    )
    parser.add_argument(
        "--strict-docs", dest="strict_docs", action="store_true",
        help="Treat documentation warnings as errors.",
    )
    args = parser.parse_args(argv)

    _State.verbose = args.verbose
    _State.quiet = args.quiet
    _State.strict = args.strict_docs
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Try to import ion module
    try:
        import ion  # type: ignore[import-not-found]  # noqa: F401  # pylint: disable=unused-import,import-outside-toplevel
    except ImportError as e:
        print("Error: Could not import ion module: {:s}".format(str(e)), file=sys.stderr)
        print("Make sure the ionwl binary is built and ion module is loadable.", file=sys.stderr)
        return 1

    # Discover example files.
    if _EXAMPLES_DIR.is_dir():
        for p in sorted(_EXAMPLES_DIR.iterdir()):
            if p.suffix == ".py":
                _EXAMPLE_SET.add(p.stem)
    if _EXAMPLE_SET and _State.verbose:
        print("Found {:d} example file(s) in: {:s}".format(len(_EXAMPLE_SET), str(_EXAMPLES_DIR)))

    module_tree = _get_module_tree()
    generated_count = 0

    # Generate RST for each module
    for module_name in module_tree:
        try:
            module = _import_module(module_name)
        except (ImportError, AttributeError) as e:
            print("Warning: Could not import {:s}: {:s}".format(module_name, str(e)), file=sys.stderr)
            _State.error_count += 1
            continue

        if (module_all := getattr(module, "__all__", None)) is not None:
            _MODULE_ALL[module_name] = sorted(module_all)
        submodules = _submodules_get(module_name, module)
        # Modules whose basename starts with underscore are not listed in any
        # parent toctree, so mark them as orphan to suppress Sphinx warnings.
        orphan = module_name.rpartition(".")[2].startswith("_")
        rst_path = _pymodule2sphinx(output_dir, module_name, module, submodules, orphan=orphan)
        if _State.verbose:
            print("Generated: {:s}".format(str(rst_path)))
        generated_count += 1

    # Copy hand-written guide pages referenced by the index toctree.
    _copy_guide_pages(output_dir)

    # Capture command-line `--help` output the guide pages literalinclude.
    _generate_cmdline_help(output_dir)

    # Copy static assets (CSS) referenced by conf.py's html_static_path.
    _copy_static_files(output_dir)

    # Generate index.rst
    index_path = _generate_index_rst(output_dir)
    if _State.verbose:
        print("Generated: {:s}".format(str(index_path)))

    # Copy and template conf.py.
    conf_path = _install_conf_py(output_dir)
    if _State.verbose:
        print("Generated: {:s}".format(str(conf_path)))

    if not _State.quiet:
        print("\nGenerated {:d} module RST files in: {:s}".format(generated_count, str(output_dir)))
    # Warn about example files that were never referenced (catches naming typos).
    unused = _EXAMPLE_SET - _EXAMPLES_USED
    if unused:
        label = "Error" if _State.strict else "Warning"
        print("\n{:s}: {:d} example file(s) not referenced by any module:".format(label, len(unused)),
              file=sys.stderr)
        for name in sorted(unused):
            print("  {:s}.py".format(name), file=sys.stderr)
        if _State.strict:
            _State.error_count += 1
    if _State.error_count:
        print("Errors: {:d} problem(s) reported above".format(_State.error_count), file=sys.stderr)

    # Extract operator NamedTuple annotations for the stub generator.
    _write_operator_types(output_dir)
    _write_class_traits(output_dir)
    _write_module_all(output_dir)

    if not _State.quiet:
        print("Run 'sphinx-build -b html build build/_build/html' to build HTML documentation.")

    if _State.error_count:
        return 1
    return 0


def _write_operator_types(output_dir: Path) -> None:
    """Write operator NamedTuple annotations to a JSON sidecar file.

    The stub generator cannot import the ``ion`` module (it runs outside the
    compositor), so this file provides the precise type annotations from the
    live NamedTuple classes.
    """
    import json  # pylint: disable=import-outside-toplevel
    import typing  # pylint: disable=import-outside-toplevel

    import ion.ops  # type: ignore[import-not-found]  # pylint: disable=import-outside-toplevel,import-error

    operators: dict[str, list[dict[str, str | bool]]] = {}
    for name in sorted(dir(ion.ops)):
        value = getattr(ion.ops, name)
        if not isinstance(value, type) or not hasattr(value, '_ion_operator_id'):
            continue
        fields: list[dict[str, str | bool]] = []
        hints = typing.get_type_hints(value, include_extras=True)
        defaults: dict[str, object] = getattr(value, '_field_defaults', {})
        for field_name in getattr(value, '_fields', ()):
            hint = hints.get(field_name)
            fields.append({
                'name': field_name,
                'type': _type_hint_to_str(hint),
                'has_default': field_name in defaults,
            })
        operators[name] = fields

    path = output_dir / "operator_types.json"
    path.write_text(json.dumps(operators, indent=2) + "\n")
    if _State.verbose:
        print("Generated: {:s}".format(str(path)))


def _write_class_traits(output_dir: Path) -> None:
    """Write class traits the stubs need to a JSON sidecar file.

    Whether a class allows subclassing, and whether ``__new__`` constructs it,
    is known only from the live class, and the RST is left as its docstrings
    wrote it. The stub generator marks a class that cannot be subclassed
    ``@final``, and stubs the documented ``__init__`` of a class constructed by
    ``__new__`` as ``__new__``.
    """
    import json  # pylint: disable=import-outside-toplevel

    traits = {
        "final": sorted(_FINAL_CLASSES),
        "constructed_by_new": sorted(_NEW_CLASSES),
    }
    path = output_dir / "class_traits.json"
    path.write_text(json.dumps(traits, indent=2) + "\n")
    if _State.verbose:
        print("Generated: {:s}".format(str(path)))


def _write_module_all(output_dir: Path) -> None:
    """Write each module's ``__all__`` to a JSON sidecar file, for the stubs to declare."""
    import json  # pylint: disable=import-outside-toplevel

    path = output_dir / "module_all.json"
    path.write_text(json.dumps(_MODULE_ALL, indent=2, sort_keys=True) + "\n")
    if _State.verbose:
        print("Generated: {:s}".format(str(path)))


def _write_operator_function(fw: Callable[[str], object], name: str, cls: type) -> None:
    """Write an operator as a ``.. function::`` with a NamedTuple field signature."""
    fields: tuple[str, ...] = getattr(cls, '_fields', ())
    defaults: dict[str, object] = getattr(cls, '_field_defaults', {})

    # Build signature from NamedTuple fields. Types are omitted here
    # because Sphinx mangles complex annotations (e.g. stripping Literal);
    # the :type: fields in the body provide the canonical type information.
    params: list[str] = []
    for field_name in fields:
        param = field_name
        if field_name in defaults:
            param += "={:s}".format(repr(defaults[field_name]))
        params.append(param)

    sig = ", ".join(params)
    fw(".. function:: {:s}({:s})\n\n".format(name, sig))

    # Write description from docstring.
    instance_doc = _strip_embedded_signature(cls.__doc__)
    if instance_doc:
        instance_doc = _strip_rst_method_blocks(instance_doc)
        _write_indented_lines("   ", fw, instance_doc)
        fw("\n")

    # Write :param: / :type: fields.
    _write_namedtuple_fields(fw, cls)


def _write_namedtuple_fields(fw: Callable[[str], object], cls: type) -> None:
    """Write ``:param:`` / ``:type:`` RST for a NamedTuple's fields."""
    import typing  # pylint: disable=import-outside-toplevel

    fields: tuple[str, ...] = getattr(cls, '_fields', ())
    if not fields:
        return
    hints = typing.get_type_hints(cls, include_extras=True)
    for field_name in fields:
        hint = hints.get(field_name)
        # A field's description is the string metadata of `Annotated[T, "description"]`.
        desc = next((m for m in getattr(hint, '__metadata__', ()) if isinstance(m, str)), '')
        if desc:
            fw("   :param {:s}: {:s}\n".format(field_name, desc))
        else:
            fw("   :param {:s}:\n".format(field_name))
        if hint is not None:
            fw("   :type {:s}: {:s}\n".format(field_name, _type_hint_to_str(hint)))
    fw("\n")


def _type_hint_to_str(hint: object) -> str:
    """Convert a resolved type hint to a stub-compatible string."""
    import typing  # pylint: disable=import-outside-toplevel

    if hint is None:
        return "Any"
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if origin is typing.Annotated:
        return _type_hint_to_str(args[0])
    if origin is typing.Literal:
        return "Literal[{:s}]".format(", ".join(repr(a) for a in args))
    if origin is typing.Union:
        return " | ".join(_type_hint_to_str(a) for a in args)
    if isinstance(hint, type):
        return hint.__name__
    return str(hint)


if __name__ == "__main__":
    sys.exit(main())
