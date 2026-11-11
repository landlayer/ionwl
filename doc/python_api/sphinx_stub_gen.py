#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Generate Python type stubs (.pyi) from RST API documentation.

Reads RST files and produces .pyi stub files for use with mypy.

Usage:
    python doc/python_api/sphinx_stub_gen.py [BUILD_DIR] [-o OUTPUT_DIR]
"""

from __future__ import annotations

__all__ = (
    "main",
)

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, NamedTuple

from docutils import nodes  # type: ignore[import-untyped]
from docutils.frontend import get_default_settings  # type: ignore[import-untyped]
from docutils.parsers.rst import Directive, directives, roles  # type: ignore[import-untyped]
from docutils.parsers.rst import Parser as RstParser
from docutils.utils import new_document  # type: ignore[import-untyped]

# ----------------------------------------------------------------------------
# Mutable State


class _State:  # pylint: disable=too-few-public-methods
    """Mutable counters and flags shared across the stub-generation pass."""

    # Failure to parse a single signature shouldn't fail the whole run, but
    # should produce a non-zero exit so CI catches regressions.
    parse_errors: int = 0
    # RST structure issues (e.g. a top-level callable directive that should
    # be nested under a class). Fatal: returns non-zero exit.
    structure_errors: int = 0
    # `:param X:` / `:type X:` consistency issues. Surfaced as warnings;
    # only fatal when `--strict-docs` is passed.
    undocumented_errors: int = 0
    # Types referenced in an annotation but defined in no module, almost
    # always a mistyped cross-reference target. Fatal: the stub would
    # otherwise name a type nothing defines.
    missing_type_errors: int = 0
    strict_docs: bool = False
    verbose: bool = False
    # When true, suppress progress output and print only errors/warnings.
    quiet: bool = False


# ----------------------------------------------------------------------------
# Data Model

@dataclass
class _MethodInfo:
    """A method or staticmethod extracted from RST."""

    name: str
    params: str  # "(self, arg: Type = default, ...)"
    return_type: str | None = None
    is_static: bool = False
    is_classmethod: bool = False
    is_overload: bool = False
    body_param_types: dict[str, str] = field(default_factory=dict)


@dataclass
class _AttributeInfo:
    """A class attribute or data descriptor extracted from RST."""
    name: str
    type_str: str | None = None
    # The type assignment accepts, from a `:settype:` field, when wider than
    # the type the attribute reads as (e.g. a tuple coerced to a `Rect`).
    set_type_str: str | None = None
    # A `.. data::` member, which `sphinx_doc_gen` writes for a property or a
    # Rust attribute without a setter.
    read_only: bool = False


@dataclass
class _ClassInfo:
    """A class definition extracted from RST."""
    name: str
    bases: str | None = None  # Base class from ".. class:: Name(Base)"
    final: bool = False  # Cannot be subclassed, from `class_traits.json`.
    methods: list[_MethodInfo] = field(default_factory=list)
    attributes: list[_AttributeInfo] = field(default_factory=list)


@dataclass
class _FunctionInfo:
    """A module-level function extracted from RST."""
    name: str
    params: str
    return_type: str | None = None
    body_param_types: dict[str, str] = field(default_factory=dict)


@dataclass
class _DataInfo:
    """A module-level data/constant extracted from RST."""
    name: str
    type_str: str | None = None


@dataclass
class _ModuleInfo:
    """A module's collected classes, functions, and data."""
    name: str = ""
    classes: list[_ClassInfo] = field(default_factory=list)
    functions: list[_FunctionInfo] = field(default_factory=list)
    data: list[_DataInfo] = field(default_factory=list)
    all_names: list[str] | None = None  # The runtime `__all__`, from `module_all.json`.


# Base classes that cannot be expressed via `.. class:: Name(Base)` in RST.
_CLASS_BASES: dict[str, str] = {
    "Hook": "Generic[T]",
}

# Extra stub members for classes whose RST cannot express the full signature.
# Lines are emitted verbatim (indented) inside the class body.
_CLASS_EXTRA_MEMBERS: dict[str, list[str]] = {
    # HooksRegistry: __getattr__ fallback for dynamic hook access by name.
    "HooksRegistry": [
        "def __getattr__(self, name: str, /) -> Hook[Any]: ...",
    ],
}


# ----------------------------------------------------------------------------
# RST Parsing (docutils)

class _ApiNode(nodes.Element):  # type: ignore[misc]
    """Custom node representing an API directive (class, method, etc.)."""
    # pylint: disable=unnecessary-pass


class _ApiDirective(Directive):  # type: ignore[misc]
    """Captures API directives as an ApiNode with nested-parsed content."""
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = True
    has_content = True
    # Without this, `:noindex:` is folded into the argument by
    # `final_argument_whitespace`, corrupting the directive name.
    option_spec: ClassVar[dict[str, Any]] = {'noindex': directives.flag}

    def run(self) -> list[nodes.Node]:
        # `:noindex:` on a callable directive marks an `@overload` signature;
        # on any other directive it just suppresses a duplicate cross-reference
        # and the directive is dropped.
        is_callable = self.name in ('method', 'staticmethod', 'classmethod')
        if 'noindex' in self.options and not is_callable:
            return []
        node = _ApiNode()
        node['directive_type'] = self.name
        node['argument'] = self.arguments[0]
        node['noindex'] = 'noindex' in self.options
        if self.content:
            self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


class _ModuleDirective(Directive):  # type: ignore[misc]
    """Captures ``.. module::`` directives (no content body)."""
    required_arguments = 1
    optional_arguments = 0
    has_content = False

    def run(self) -> list[nodes.Node]:
        node = _ApiNode()
        node['directive_type'] = 'module'
        node['argument'] = self.arguments[0]
        return [node]


class _TransparentDirective(Directive):  # type: ignore[misc]
    """Parse content and emit its children directly into the parent node.

    Used for visual-only directives like ``.. details::`` whose contents
    must remain visible to stub generation. The wrapping is invisible.
    """
    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True
    has_content = True

    def run(self) -> list[nodes.Node]:
        if not self.content:
            return []
        temp = nodes.Element()
        self.state.nested_parse(self.content, self.content_offset, temp)
        # Detach from temp so docutils can re-parent into this directive's parent.
        children = list(temp.children)
        temp.children = []
        for child in children:
            child.parent = None
        return children


def _setup_docutils() -> None:
    """Register handlers for Sphinx Python domain directives and roles."""
    for name in ('class', 'function', 'data', 'attribute',
                 'method', 'staticmethod', 'classmethod'):
        directives.register_directive(name, _ApiDirective)
    directives.register_directive('module', _ModuleDirective)
    directives.register_directive('currentmodule', _ModuleDirective)
    directives.register_directive('details', _TransparentDirective)

    # Capture Sphinx roles as inline nodes with role metadata.
    def preserve_role(
        name: str, rawtext: str, text: str, lineno: int,
        inliner: object, options: dict[str, str] | None = None,
        content: list[str] | None = None,
    ) -> tuple[list[nodes.Node], list[nodes.Node]]:
        del lineno, inliner, options, content
        node = nodes.inline(rawtext, text)
        node['role'] = name
        return [node], []

    for role_name in ('class', 'attr', 'meth', 'func',
                      'data', 'mod', 'obj', 'ref'):
        roles.register_local_role(role_name, preserve_role)


_setup_docutils()


# ---------------------------------------------------------------------------
# Docutils tree helpers
# ---------------------------------------------------------------------------

def _parse_document(path: Path) -> nodes.document:
    """Parse an RST file into a docutils document tree."""
    parser = RstParser()
    settings = get_default_settings(RstParser)
    settings.report_level = 5  # suppress warnings
    settings.halt_level = 5
    settings.line_length_limit = 100_000
    doc = new_document(str(path), settings)
    parser.parse(path.read_text(encoding="utf-8"), doc)
    return doc


# ---------------------------------------------------------------------------
# String helpers (regex-free)
# ---------------------------------------------------------------------------

def _is_word_char(c: str) -> bool:
    """Return True if *c* is alphanumeric or underscore (equivalent to ``\\w``)."""
    return c.isalnum() or c == '_'


def _split_leading_ident(s: str) -> tuple[str, str]:
    """Split *s* into a leading identifier and remainder."""
    i = 0
    while i < len(s) and _is_word_char(s[i]):
        i += 1
    return s[:i], s[i:]


def _replace_class_roles(text: str, fn: object) -> str:
    """Replace ``:class:`X``` patterns in *text* by calling *fn(X)*."""
    marker = ":class:`"
    parts: list[str] = []
    pos = 0
    while True:
        i = text.find(marker, pos)
        if i == -1:
            parts.append(text[pos:])
            break
        parts.append(text[pos:i])
        beg = i + len(marker)
        end = text.find("`", beg)
        if end == -1:
            parts.append(text[i:])
            break
        parts.append(fn(text[beg:end]))  # type: ignore[operator]
        pos = end + 1
    return "".join(parts)


def _iter_class_roles(text: str) -> list[str]:
    """Return content strings from all ``:class:`X``` patterns in *text*."""
    marker = ":class:`"
    result: list[str] = []
    pos = 0
    while True:
        i = text.find(marker, pos)
        if i == -1:
            break
        beg = i + len(marker)
        end = text.find("`", beg)
        if end == -1:
            break
        result.append(text[beg:end])
        pos = end + 1
    return result


def _replace_word(text: str, old: str, new: str) -> str:
    """Replace *old* with *new* at word boundaries in *text*."""
    parts: list[str] = []
    pos = 0
    old_len = len(old)
    while True:
        i = text.find(old, pos)
        if i == -1:
            parts.append(text[pos:])
            break
        # Check word boundary before.
        if i > 0 and _is_word_char(text[i - 1]):
            parts.append(text[pos:i + 1])
            pos = i + 1
            continue
        # Check word boundary after.
        end = i + old_len
        if end < len(text) and _is_word_char(text[end]):
            parts.append(text[pos:i + 1])
            pos = i + 1
            continue
        parts.append(text[pos:i])
        parts.append(new)
        pos = end
    return "".join(parts)


def _contains_word(text: str, word: str) -> bool:
    """Check if *word* exists at word boundaries in *text*."""
    word_len = len(word)
    pos = 0
    while True:
        i = text.find(word, pos)
        if i == -1:
            return False
        if i > 0 and _is_word_char(text[i - 1]):
            pos = i + 1
            continue
        end = i + word_len
        if end < len(text) and _is_word_char(text[end]):
            pos = i + 1
            continue
        return True


def _strip_outer_parens(params: str) -> str:
    """Remove only the outermost parentheses from a parameter string.

    Given the input ``(*, location: Vector = (0.0, 0.0))`` it is important
    to only remove the outermost parentheses.
    """
    if params.startswith("(") and params.endswith(")"):
        return params[1:-1]
    raise ValueError("Input is expected to be wrapped by parentheses: {:s}".format(params))


def _replace_bare_dict(text: str) -> str:
    """Replace bare ``dict`` (not followed by ``[``) with ``dict[str, Any]``."""
    parts: list[str] = []
    pos = 0
    while True:
        i = text.find("dict", pos)
        if i == -1:
            parts.append(text[pos:])
            break
        # Check word boundary before.
        if i > 0 and _is_word_char(text[i - 1]):
            parts.append(text[pos:i + 1])
            pos = i + 1
            continue
        end = i + 4  # len("dict")
        # Check word boundary after.
        if end < len(text) and _is_word_char(text[end]):
            parts.append(text[pos:i + 1])
            pos = i + 1
            continue
        # Check not followed by '['.
        if end < len(text) and text[end] == '[':
            parts.append(text[pos:end])
            pos = end
            continue
        parts.append(text[pos:i])
        parts.append("dict[str, Any]")
        pos = end
    return "".join(parts)


def _inline_node_text(node: nodes.Node) -> str:
    """Convert a single inline node to its text representation for type strings.

    ``:class:`` roles are preserved as ``:class:`ShortName``` so downstream
    consumers (``convert_rst_type``, ``collect_class_refs``) can identify
    class references structurally rather than relying on naming heuristics.
    """
    if isinstance(node, nodes.inline):
        role = node.get('role')
        target: str = node.astext()
        if role == 'class':
            short = target.split(".")[-1]
            return ":class:`{:s}`".format(short)
        return target
    result: str = node.astext()
    return result


def _paragraph_to_type_str(para: nodes.paragraph) -> str:
    """Build a type string from a paragraph node by walking its children."""
    parts: list[str] = []
    for child in para.children:
        parts.append(_inline_node_text(child))
    return "".join(parts).strip()


def _field_raw_value(field_node: nodes.field) -> str:
    """Extract type string from a field body using the docutils node tree."""
    body = field_node.children[1]  # field_body
    for child in body.children:
        if isinstance(child, nodes.paragraph):
            return _paragraph_to_type_str(child)
    result: str = body.astext()
    return result.strip()


def _node_fields(node: nodes.Element) -> dict[str, str]:
    """Extract field-list entries from direct children of *node*.

    Returns ``{"type position": "tuple[int, int]", "rtype": "str", ...}``.
    """
    result: dict[str, str] = {}
    for child in node.children:
        if isinstance(child, nodes.field_list):
            for field_node in child.children:
                if isinstance(field_node, nodes.field):
                    name = field_node.children[0].astext()
                    result[name] = _field_raw_value(field_node)
    return result


# ---------------------------------------------------------------------------
# Document -> data-model extraction
# ---------------------------------------------------------------------------

def _parse_rst_file(path: Path) -> _ModuleInfo:
    """Parse an RST file into a ModuleInfo using docutils."""
    doc = _parse_document(path)
    module = _ModuleInfo()

    # Walk the tree collecting only *top-level* API nodes (those whose
    # parent is NOT another ApiNode). Titles create nested sections, so
    # we cannot simply iterate `doc.children`.
    for node in doc.findall(_ApiNode):
        if isinstance(node.parent, _ApiNode):
            continue  # handled by extract_class / extract_method
        dtype = node['directive_type']
        if dtype == 'module':
            module.name = node['argument']
        elif dtype == 'class':
            module.classes.append(_extract_class(node, path))
        elif dtype == 'function':
            module.functions.append(_extract_function(node, path))
        elif dtype in ('method', 'staticmethod', 'classmethod'):
            # A method/staticmethod/classmethod directive at module level
            # is almost always an authoring mistake (it should be nested
            # inside a `.. class::` block). Surface rather than silently
            # reclassifying as a free function.
            print(
                "Warning: top-level '{:s}' directive in {:s}: {:s}".format(
                    dtype, path.name, node['argument'],
                ),
                file=sys.stderr,
            )
            _State.structure_errors += 1
        elif dtype == 'data':
            module.data.append(_extract_data(node))

    return module


def _extract_class(node: _ApiNode, source_path: Path) -> _ClassInfo:
    """Extract ClassInfo from a ``.. class::`` node."""
    arg = node['argument']
    name, rest = _split_leading_ident(arg)
    if not name:
        raise ValueError("Expected identifier in class directive: {:s}".format(arg))
    rest = rest.strip()

    # Parens on `.. class::` always denote a base class.
    # Constructor parameters come from `.. method:: __init__`.
    bases: str | None = None
    if rest.startswith('('):
        bases = _strip_outer_parens(rest)

    cls = _ClassInfo(name=name, bases=bases)

    # Collect methods first; overload vs duplicate is decided after the pass.
    collected_methods: list[_MethodInfo] = []
    seen_attrs: set[str] = set()

    for child in node.children:
        if not isinstance(child, _ApiNode):
            continue
        dtype = child['directive_type']
        if dtype in ('method', 'staticmethod', 'classmethod'):
            collected_methods.append(_extract_method(child, source_path, class_name=name))
        elif dtype in ('attribute', 'data'):
            attr = _extract_attribute(child)
            if attr.name not in seen_attrs:
                seen_attrs.add(attr.name)
                cls.attributes.append(attr)

    # A method name marked with `:noindex:` anywhere in the group denotes
    # an overload set: keep every entry and mark all as @overload. Otherwise
    # treat duplicates as authoring noise and keep only the first.
    overload_names = {m.name for m in collected_methods if m.is_overload}
    seen_methods: set[str] = set()
    for method in collected_methods:
        if method.name in overload_names:
            method.is_overload = True
            cls.methods.append(method)
        elif method.name not in seen_methods:
            seen_methods.add(method.name)
            cls.methods.append(method)

    return cls


def _extract_callable(
    node: _ApiNode,
    source_path: Path,
    class_name: str | None = None,
) -> tuple[str, str, str | None, dict[str, str]]:
    """Extract name, params, return type, and body param types from a callable node."""
    arg = node['argument']
    name, sig_rest = _split_leading_ident(arg)
    if not name:
        raise ValueError("Expected identifier in callable directive: {:s}".format(arg))
    sig_rest = sig_rest.strip()

    params, return_type, parsed_args = _split_signature(sig_rest, source_path)

    fields = _node_fields(node)
    body_param_types = {
        k[5:]: v for k, v in fields.items() if k.startswith('type ')
    }
    body_rtype = fields.get('rtype')

    if return_type is None and body_rtype:
        return_type = body_rtype

    qual_name = "{:s}.{:s}".format(class_name, name) if class_name else name
    _check_params_consistent(qual_name, parsed_args, fields, source_path)

    return name, params, return_type, body_param_types


def _extract_method(node: _ApiNode, source_path: Path, class_name: str) -> _MethodInfo:
    """Extract MethodInfo from a ``.. method::`` / ``.. staticmethod::`` node."""
    name, params, return_type, body_param_types = _extract_callable(
        node, source_path, class_name=class_name,
    )
    return _MethodInfo(
        name=name,
        params=params,
        return_type=return_type,
        is_static=node['directive_type'] == 'staticmethod',
        is_classmethod=node['directive_type'] == 'classmethod',
        is_overload=bool(node.get('noindex')),
        body_param_types=body_param_types,
    )


def _extract_attribute(node: _ApiNode) -> _AttributeInfo:
    """Extract AttributeInfo from a ``.. attribute::`` / ``.. data::`` node."""
    name = node['argument'].strip()
    fields = _node_fields(node)

    type_str = fields.get('type')
    set_type_str = fields.get('settype')
    read_only = node['directive_type'] == 'data'
    if set_type_str is not None and read_only:
        raise ValueError("{:s}: read-only attribute has a :settype: field".format(name))
    return _AttributeInfo(name=name, type_str=type_str, set_type_str=set_type_str, read_only=read_only)


def _extract_function(node: _ApiNode, source_path: Path) -> _FunctionInfo:
    """Extract FunctionInfo from a ``.. function::`` node."""
    name, params, return_type, body_param_types = _extract_callable(node, source_path)
    return _FunctionInfo(
        name=name,
        params=params,
        return_type=return_type,
        body_param_types=body_param_types,
    )


def _check_params_consistent(
    qual_name: str,
    args: ast.arguments | None,
    fields: dict[str, str],
    source_path: Path,
) -> None:
    """Warn about ``:param:`` / ``:type:`` inconsistencies in a callable.

    Flags both missing documentation (an argument with no ``:type X:`` or
    ``:param X:`` field) and orphans (``:type X:`` / ``:param X:`` whose
    ``X`` is not actually an argument). ``self`` / ``cls`` are already
    stripped from RST signatures so no skip is needed.
    """
    if args is None:
        return
    arg_names: set[str] = set()
    for arg in args.posonlyargs + args.args + args.kwonlyargs:
        argname = arg.arg
        # `self` / `cls` appear in ionwl's RST signatures but are not
        # expected to carry `:param:` / `:type:` documentation.
        if argname in ("self", "cls"):
            arg_names.add(argname)
            continue
        arg_names.add(argname)
        has_param = "param {:s}".format(argname) in fields
        has_type = "type {:s}".format(argname) in fields
        issue: str | None = None
        if not has_param and not has_type:
            issue = "param '{:s}' is undocumented".format(argname)
        elif not has_param:
            issue = "param '{:s}' has no :param:".format(argname)
        elif not has_type:
            issue = "param '{:s}' has no :type:".format(argname)
        if issue is not None:
            label = "Error" if _State.strict_docs else "Warning"
            print(
                "{:s}: {:s}: {:s}: {:s}".format(label, source_path.name, qual_name, issue),
                file=sys.stderr,
            )
            _State.undocumented_errors += 1

    # Orphan check: skip when the signature is variadic, since `*args` /
    # `**kwargs` can legitimately accept any caller-supplied name.
    if args.vararg is None and args.kwarg is None:
        for key in fields:
            for prefix in ("param ", "type "):
                if key.startswith(prefix):
                    pname = key[len(prefix):]
                    if pname not in arg_names:
                        label = "Error" if _State.strict_docs else "Warning"
                        print(
                            "{:s}: {:s}: {:s}: orphan ':{:s}{:s}:' (no matching argument)".format(
                                label, source_path.name, qual_name, prefix, pname,
                            ),
                            file=sys.stderr,
                        )
                        _State.undocumented_errors += 1
                    break


def _extract_data(node: _ApiNode) -> _DataInfo:
    """Extract DataInfo from a ``.. data::`` node."""
    name = node['argument'].strip()
    fields = _node_fields(node)
    type_str = fields.get('type')
    return _DataInfo(name=name, type_str=type_str)


def _split_signature(
    sig_str: str,
    source_path: Path | None = None,
) -> tuple[str, str | None, ast.arguments | None]:
    """Split ``(params) -> RetType`` into (params_str, return_type, parsed_args)."""
    if not sig_str:
        return "()", None, None

    # Parse as a function definition and inspect the AST.
    try:
        tree = ast.parse("def _{:s}: pass".format(sig_str))
    except SyntaxError:
        where = source_path.name + ": " if source_path is not None else ""
        print(
            "Warning: {:s}could not parse signature: {:s}".format(where, sig_str),
            file=sys.stderr,
        )
        _State.parse_errors += 1
        return sig_str.strip(), None, None
    func_def = tree.body[0]
    assert isinstance(func_def, ast.FunctionDef)
    params = "({:s})".format(ast.unparse(func_def.args))
    return_type = ast.unparse(func_def.returns) if func_def.returns else None
    return params, return_type, func_def.args


# ----------------------------------------------------------------------------
# Type Conversion

_PYTHON_BUILTINS = frozenset({
    "bool", "int", "float", "str", "bytes", "list", "dict", "tuple", "set",
    "frozenset", "type", "object", "None",
})


def _resolve_class_ref(
    fqn: str,
    imports: set[tuple[str, str]],
    current_module: str,
    class_locations: dict[str, str],
) -> str:
    """Resolve a fully-qualified class name to its short form, tracking imports."""
    parts = fqn.split(".")
    short = parts[-1]
    if short in _PYTHON_BUILTINS:
        return short
    actual_module = class_locations.get(short, ".".join(parts[:-1]))
    if actual_module and actual_module != current_module:
        imports.add((actual_module, short))
    return short


def _convert_rst_type(
    type_str: str,
    imports: set[tuple[str, str]],
    current_module: str,
    class_locations: dict[str, str],
) -> str:
    """Convert RST type string to Python type annotation, tracking imports.

    Tree-walked type strings preserve ``:class:`` markup so class references
    can be identified structurally. The resolver replaces ``:class:`Name```
    with the short name and tracks the import.
    """
    if not type_str:
        imports.add(("typing", "Any"))
        return "Any"

    result = type_str

    # Resolve :class: references.
    if ":class:" in result:
        result = _replace_class_roles(
            result,
            lambda ref: _resolve_class_ref(ref, imports, current_module, class_locations),
        )
    result = result.replace("``", "")

    result = result.strip()

    # Convert 'or None' union syntax to PEP 604 '| None'.
    result = _replace_word(result, "or None", "| None")

    # Replace bare 'dict' (without type params) with 'dict[str, Any]'.
    result = _replace_bare_dict(result)

    # Replace undefined recursive type placeholder 'spec' with Any.
    result = _replace_word(result, "spec", "Any")

    _track_imports(result, imports)

    return result


def _augment_params(
    params: str,
    body_types: dict[str, str],
    imports: set[tuple[str, str]],
    current_module: str,
    class_locations: dict[str, str],
) -> str:
    """Add type annotations to params from ``:type:`` directives using ``ast``."""
    if not body_types:
        return params

    try:
        tree = ast.parse("def _{:s}: pass".format(params))
    except SyntaxError:
        return params
    func_def = tree.body[0]
    assert isinstance(func_def, ast.FunctionDef)
    args = func_def.args

    all_args = args.posonlyargs + args.args + args.kwonlyargs
    if args.vararg:
        all_args.append(args.vararg)
    if args.kwarg:
        all_args.append(args.kwarg)

    # Skip if any parameter already has an annotation.
    if any(a.annotation is not None for a in all_args):
        return params

    # Map each arg to its default expression (for implicit-Optional detection).
    defaults_for: dict[int, ast.expr] = {}
    positional = args.posonlyargs + args.args
    if args.defaults:
        offset = len(positional) - len(args.defaults)
        for i, pos_default in enumerate(args.defaults):
            defaults_for[id(positional[offset + i])] = pos_default
    for kw, kw_default in zip(args.kwonlyargs, args.kw_defaults):
        if kw_default is not None:
            defaults_for[id(kw)] = kw_default

    changed = False
    for a in all_args:
        if a.arg not in body_types:
            continue
        type_ann = _convert_rst_type(body_types[a.arg], imports, current_module, class_locations)
        # Implicit Optional: default is None but type doesn't include None.
        arg_default = defaults_for.get(id(a))
        if (arg_default is not None and isinstance(arg_default, ast.Constant)
                and arg_default.value is None and "None" not in type_ann):
            type_ann = type_ann + " | None"
        try:
            a.annotation = ast.parse(type_ann, mode="eval").body
        except SyntaxError:
            # Type string isn't a valid Python expression; inject as a
            # string annotation but surface the bug rather than swallow it.
            print(
                "Warning: could not parse type annotation: {:s}".format(type_ann),
                file=sys.stderr,
            )
            _State.parse_errors += 1
            a.annotation = ast.Constant(value=type_ann)
        changed = True

    if not changed:
        return params

    return "({:s})".format(ast.unparse(args))


# ----------------------------------------------------------------------------
# Stub Emission

_OperatorTypes = dict[str, list[dict[str, str | bool]]]


def _sort_classes_by_hierarchy(classes: list[_ClassInfo]) -> list[_ClassInfo]:
    """Reorder classes so each appears after its locally-defined bases.

    Base classes are evaluated at class-definition time, so a stub file like
    ``class Sub(Base): ...`` fails to import when ``Base`` is defined later
    in the same module (``from __future__ import annotations`` does not defer
    base-class evaluation). Original order is preserved as a tiebreaker.
    """
    by_name = {cls.name: cls for cls in classes}
    result: list[_ClassInfo] = []
    written: set[str] = set()

    def visit(cls: _ClassInfo) -> None:
        if cls.name in written:
            return
        written.add(cls.name)
        bases_str = cls.bases or _CLASS_BASES.get(cls.name) or ""
        # bases_str may be e.g. `"BaseA, BaseB"` or `"Generic[T]"`;
        # strip generic args before looking up locally-defined bases.
        for base in bases_str.split(","):
            base_name = base.strip().split("[", 1)[0].strip()
            base_cls = by_name.get(base_name)
            if base_cls is not None:
                visit(base_cls)
        result.append(cls)

    for cls in classes:
        visit(cls)
    return result


def _emit_stub(
    module: _ModuleInfo,
    output_dir: Path,
    class_locations: dict[str, str],
    all_modules: dict[str, _ModuleInfo],
    operator_types: _OperatorTypes | None = None,
) -> Path:
    """Generate a .pyi stub file for a module."""
    imports: set[tuple[str, str]] = set()
    body_lines: list[str] = []
    current_module = module.name

    # Defined class names in this module (for self-reference)
    local_classes = {cls.name for cls in module.classes}

    # Emit type aliases before classes that may reference them.
    type_alias_data = [d for d in module.data if d.type_str and d.type_str.startswith("TypeAlias = ")]
    for data in type_alias_data:
        _emit_data(data, body_lines, imports, current_module, class_locations)

    # Emit classes (hierarchy-sorted so locally-defined bases come first).
    for cls in _sort_classes_by_hierarchy(module.classes):
        _emit_class(cls, body_lines, imports, current_module, class_locations)
        body_lines.append("")

    # Emit functions. Operator functions are emitted as NamedTuple classes.
    for func in module.functions:
        if operator_types is not None and func.name in operator_types:
            _emit_operator_from_types(func.name, operator_types[func.name], body_lines, imports)
        else:
            _emit_function(func, body_lines, imports, current_module, class_locations)

    # Emit data.
    for data in module.data:
        if data in type_alias_data:
            continue  # Already emitted above.
        _emit_data(data, body_lines, imports, current_module, class_locations)

    # Emit submodule re-exports for package __init__
    submodules = _get_submodules(current_module, all_modules)
    if submodules:
        for sub in submodules:
            # pylint: disable-next=duplicate-string-formatting-argument
            body_lines.append("from {:s} import {:s} as {:s}".format(current_module, sub, sub))

    # Build import header
    header: list[str] = []
    header.append("# Auto-generated by sphinx_stub_gen.py - do not edit")
    header.append("from __future__ import annotations")
    header.append("")

    # Ahead of the imports, as PEP 8 places module dunders.
    if module.all_names is not None:
        header.append("__all__ = [")
        header.extend("    {!r},".format(name) for name in module.all_names)
        header.append("]")
        header.append("")
    imports_start = len(header)

    typing_names = sorted({name for mod, name in imports if mod == "typing"})
    if typing_names:
        header.append("from typing import {:s}".format(", ".join(typing_names)))

    import_groups: dict[str, set[str]] = {}
    for mod, name in imports:
        if mod in ("typing", current_module):
            continue
        # Don't import names that are locally defined
        if name in local_classes:
            continue
        import_groups.setdefault(mod, set()).add(name)

    for mod in sorted(import_groups):
        names = ", ".join(sorted(import_groups[mod]))
        header.append("from {:s} import {:s}".format(mod, names))

    if len(header) > imports_start:
        header.append("")

    # Add TypeVar declarations when Generic base classes are used.
    if "TypeVar" in typing_names:
        header.append("T = TypeVar('T')")
        header.append("")

    # Determine output path
    parts = current_module.split(".")
    stub_dir = output_dir
    for part in parts:
        stub_dir = stub_dir / part
    stub_dir.mkdir(parents=True, exist_ok=True)
    stub_path = stub_dir / "__init__.pyi"

    content = "\n".join(header + body_lines) + "\n"
    stub_path.write_text(content, encoding="utf-8")
    return stub_path


def _emit_class(
    cls: _ClassInfo,
    lines: list[str],
    imports: set[tuple[str, str]],
    current_module: str,
    class_locations: dict[str, str],
) -> None:
    """Emit a class definition."""
    if cls.final:
        imports.add(("typing", "final"))
        lines.append("@final")
    bases = cls.bases or _CLASS_BASES.get(cls.name)
    if bases:
        lines.append("class {:s}({:s}):".format(cls.name, bases))
        # Track imports for base class generics.
        if "Generic" in bases:
            imports.add(("typing", "Generic"))
            imports.add(("typing", "TypeVar"))
    else:
        lines.append("class {:s}:".format(cls.name))

    has_members = False

    # Names supplied by CLASS_EXTRA_MEMBERS suppress the auto-emitted versions
    # so the manual stubs (typically with richer typing like
    # `Point | Size | tuple[int, int]`) win over the generic auto entries.
    extra = _CLASS_EXTRA_MEMBERS.get(cls.name) or []
    extra_names = {_extract_stub_member_name(line) for line in extra}
    extra_names.discard("")

    # Methods
    for method in cls.methods:
        if method.name in extra_names:
            continue
        _emit_method(method, lines, imports, current_module, class_locations)
        has_members = True

    # Attributes
    for attr in cls.attributes:
        if attr.name in extra_names:
            continue
        _emit_attribute(attr, lines, imports, current_module, class_locations)
        has_members = True

    # Extra members for classes that need manual stubs.
    if extra:
        for line in extra:
            lines.append("    " + line)
        has_members = True

    if not has_members:
        lines.append("    ...")


def _extract_stub_member_name(line: str) -> str:
    """Return the member name declared by a CLASS_EXTRA_MEMBERS entry.

    Handles ``def NAME(...): ...`` and ``NAME: TYPE`` / ``NAME = ...`` forms.
    Returns ``""`` if the line doesn't look like a member declaration.
    """
    stripped = line.lstrip()
    if stripped.startswith("def "):
        head = stripped[4:]
        paren = head.find("(")
        if paren > 0:
            return head[:paren].strip()
        return ""
    # Attribute / data line: `NAME: TYPE` or `NAME = ...`.
    name, rest = _split_leading_ident(stripped)
    if name and rest.lstrip()[:1] in (":", "="):
        return name
    return ""


def _emit_method(
    method: _MethodInfo,
    lines: list[str],
    imports: set[tuple[str, str]],
    current_module: str,
    class_locations: dict[str, str],
) -> None:
    """Emit a method definition."""
    name = method.name

    params = method.params
    if method.body_param_types:
        params = _augment_params(params, method.body_param_types, imports, current_module, class_locations)

    # Convert any RST type references in the params.
    params = _convert_params_types(params, imports, current_module, class_locations)

    ret_type = "None"
    if method.return_type:
        ret_type = _convert_rst_type(method.return_type, imports, current_module, class_locations)

    inner = _strip_outer_parens(params)
    if method.is_overload:
        imports.add(("typing", "overload"))
        lines.append("    @overload")
    if method.is_static:
        lines.append("    @staticmethod")
    elif method.is_classmethod:
        lines.append("    @classmethod")
        if _split_leading_ident(inner)[0] != "cls":
            inner = "cls, " + inner if inner else "cls"
    else:
        # `__new__` is implicitly static, taking the class.
        first = "cls" if name == "__new__" else "self"
        if _split_leading_ident(inner)[0] != first:
            inner = first + ", " + inner if inner else first
        # Protocol methods take positional-only parameters, as CPython's slots do.
        # A PyO3 `__call__` takes keywords.
        if (
                name.startswith("__") and name.endswith("__") and
                name not in {"__init__", "__new__", "__call__"} and
                "," in inner and not any(c in inner for c in "*/")
        ):
            inner += ", /"
    lines.append("    def {:s}({:s}) -> {:s}: ...".format(name, inner, ret_type))


def _emit_attribute(
    attr: _AttributeInfo,
    lines: list[str],
    imports: set[tuple[str, str]],
    current_module: str,
    class_locations: dict[str, str],
) -> None:
    """Emit an attribute declaration."""
    name = attr.name

    # Skip attributes whose names aren't valid Python identifiers
    if not name.isidentifier():
        return

    if attr.type_str:
        type_ann = _convert_rst_type(attr.type_str, imports, current_module, class_locations)
    else:
        imports.add(("typing", "Any"))
        type_ann = "Any"
    if attr.read_only or attr.set_type_str:
        lines.append("    @property")
        lines.append("    def {:s}(self) -> {:s}: ...".format(name, type_ann))
        if attr.set_type_str:
            set_type_ann = _convert_rst_type(attr.set_type_str, imports, current_module, class_locations)
            lines.append("    @{:s}.setter".format(name))
            lines.append("    def {:s}(self, value: {:s}) -> None: ...".format(name, set_type_ann))
        return
    # Initialize with `= ...` so the name is a real class attribute. Without
    # it, `from __future__ import annotations` turns `name: type` into a
    # string-only entry in `__annotations__`, so `Class.name` raises
    # `AttributeError` at runtime - which breaks stubs that reference it as
    # a default value.
    lines.append("    {:s}: {:s} = ...".format(name, type_ann))


def _emit_function(
    func: _FunctionInfo,
    lines: list[str],
    imports: set[tuple[str, str]],
    current_module: str,
    class_locations: dict[str, str],
) -> None:
    """Emit a module-level function."""
    params = func.params
    if func.body_param_types:
        params = _augment_params(params, func.body_param_types, imports, current_module, class_locations)

    params = _convert_params_types(params, imports, current_module, class_locations)

    ret_type = "None"
    if func.return_type:
        ret_type = _convert_rst_type(func.return_type, imports, current_module, class_locations)

    inner = _strip_outer_parens(params)
    lines.append("def {:s}({:s}) -> {:s}: ...".format(func.name, inner, ret_type))


def _emit_data(
    data: _DataInfo,
    lines: list[str],
    imports: set[tuple[str, str]],
    current_module: str,
    class_locations: dict[str, str],
) -> None:
    """Emit a module-level data declaration."""
    if data.type_str and data.type_str.startswith("TypeAlias = "):
        # Recursive type alias: emit as `Name = ...` assignment.
        imports.add(("typing", "TypeAlias"))
        alias_rhs = data.type_str[len("TypeAlias = "):]
        lines.append("{:s}: TypeAlias = {:s}".format(data.name, alias_rhs))
        return
    if data.type_str:
        type_ann = _convert_rst_type(data.type_str, imports, current_module, class_locations)
    else:
        imports.add(("typing", "Any"))
        type_ann = "Any"
    lines.append("{:s}: {:s}".format(data.name, type_ann))


def _load_operator_types(build_dir: Path) -> _OperatorTypes | None:
    """Load operator NamedTuple annotations from the JSON sidecar file.

    Written by ``sphinx_doc_gen.py`` which runs inside the compositor and
    has access to the live NamedTuple classes.
    """
    import json  # pylint: disable=import-outside-toplevel
    path = build_dir / "operator_types.json"
    if not path.exists():
        return None
    data: _OperatorTypes = json.loads(path.read_text())
    return data


class _ClassTraits(NamedTuple):
    """Qualified class names by trait, from ``class_traits.json``."""
    # Cannot be subclassed.
    final: frozenset[str]
    # Constructed by `__new__`.
    constructed_by_new: frozenset[str]


def _load_class_traits(build_dir: Path) -> _ClassTraits:
    """Load the class traits from the JSON sidecar file written by ``sphinx_doc_gen.py``."""
    import json  # pylint: disable=import-outside-toplevel
    traits: dict[str, list[str]] = json.loads((build_dir / "class_traits.json").read_text())
    return _ClassTraits(
        final=frozenset(traits["final"]),
        constructed_by_new=frozenset(traits["constructed_by_new"]),
    )


def _constructor_to_new(cls: _ClassInfo) -> None:
    """Stub a class's documented ``__init__`` as the ``__new__`` that constructs it.

    The documentation keeps ``__init__``, which reads naturally for a
    constructor; the stub has to name the method the runtime defines.
    """
    for method in cls.methods:
        if method.name != "__init__":
            continue
        method.name = "__new__"
        if method.params.startswith(("(self,", "(self)")):
            method.params = "(cls" + method.params[len("(self"):]
        method.return_type = "Self"


def _load_module_all(build_dir: Path) -> dict[str, list[str]]:
    """Load each module's ``__all__`` from the JSON sidecar file written by ``sphinx_doc_gen.py``."""
    import json  # pylint: disable=import-outside-toplevel
    module_all: dict[str, list[str]] = json.loads((build_dir / "module_all.json").read_text())
    return module_all


def _track_imports(text: str, imports: set[tuple[str, str]]) -> None:
    """Add typing / ``collections.abc`` imports for names appearing in *text*.

    Uses word-boundary matching so identifiers like ``MySequence`` do not
    falsely trigger a ``Sequence`` import.
    """
    for name in ("Any", "Literal", "NamedTuple", "Self"):
        if _contains_word(text, name):
            imports.add(("typing", name))
    # PEP 585: prefer `collections.abc` over the deprecated `typing` aliases.
    for name in ("Callable", "Generator", "Iterable", "Iterator", "Sequence"):
        if _contains_word(text, name):
            imports.add(("collections.abc", name))
    if _contains_word(text, "AbstractContextManager"):
        imports.add(("contextlib", "AbstractContextManager"))


def _emit_operator_from_types(
    name: str,
    fields: list[dict[str, str | bool]],
    lines: list[str],
    imports: set[tuple[str, str]],
) -> None:
    """Emit an operator stub from NamedTuple annotation data."""
    imports.add(("typing", "NamedTuple"))
    lines.append("class {:s}(NamedTuple):".format(name))

    for field_info in fields:
        field_name = str(field_info['name'])
        type_ann = str(field_info['type'])
        _track_imports(type_ann, imports)
        if field_info.get('has_default', False):
            lines.append("    {:s}: {:s} = ...".format(field_name, type_ann))
        else:
            lines.append("    {:s}: {:s}".format(field_name, type_ann))
    imports.add(("ion.types", "Event"))
    lines.append("    def call(self, event: Event) -> bool | None: ...")
    lines.append("")


def _convert_params_types(
    params: str,
    imports: set[tuple[str, str]],
    current_module: str,
    class_locations: dict[str, str],
) -> str:
    """Convert ``:class:`` markup in a params string to plain names and track imports."""
    result = params

    if ":class:" in result:
        result = _replace_class_roles(
            result,
            lambda ref: _resolve_class_ref(ref, imports, current_module, class_locations),
        )

    _track_imports(result, imports)

    return result


def _get_submodules(module_name: str, all_modules: dict[str, _ModuleInfo]) -> list[str]:
    """Get submodule names for a package module."""
    prefix = module_name + "."
    subs = []
    for name in sorted(all_modules):
        if name.startswith(prefix) and "." not in name[len(prefix):]:
            subs.append(name[len(prefix):])
    return subs


# ----------------------------------------------------------------------------
# Main

def _build_class_locations(modules: dict[str, _ModuleInfo]) -> dict[str, str]:
    """Build a mapping from class name to the module where it's defined."""
    locations: dict[str, str] = {}
    for mod_name, mod in modules.items():
        for cls in mod.classes:
            locations.setdefault(cls.name, mod_name)
    return locations


def _collect_class_refs(type_str: str | None, out: set[str]) -> None:
    """Add short class names from ``:class:`` references in *type_str* to *out*."""
    if type_str:
        for ref in _iter_class_roles(type_str):
            out.add(ref.split(".")[-1])


def _find_missing_types(
    modules: dict[str, _ModuleInfo],
    class_locations: dict[str, str],
) -> frozenset[str]:
    """Find types referenced in annotations but not defined in any module."""
    referenced: set[str] = set()

    for mod in modules.values():
        for cls in mod.classes:
            for attr in cls.attributes:
                _collect_class_refs(attr.type_str, referenced)
            for method in cls.methods:
                _collect_class_refs(method.return_type, referenced)
                for v in method.body_param_types.values():
                    _collect_class_refs(v, referenced)
        for func in mod.functions:
            _collect_class_refs(func.return_type, referenced)
            for v in func.body_param_types.values():
                _collect_class_refs(v, referenced)
        for data in mod.data:
            _collect_class_refs(data.type_str, referenced)

    defined = set(class_locations.keys())
    # Exclude builtins, typing names, and common non-class identifiers.
    builtin_and_typing = {
        "Any", "Callable", "Generator", "Generic", "Iterable", "Iterator",
        "Literal", "NamedTuple", "Self", "Sequence", "TypeVar",
        "None", "True", "False",
        "bool", "bytes", "dict", "float", "int", "list", "set", "str", "tuple", "type",
    }
    return frozenset(referenced - defined - builtin_and_typing)


def main() -> int:  # pylint: disable=too-many-return-statements
    """Generate .pyi stubs from RST documentation."""
    parser = argparse.ArgumentParser(description="Generate .pyi stubs from RST API documentation.")
    parser.add_argument(
        "build_dir", nargs="?",
        default=str(Path(__file__).parent / "build"),
        help="Directory containing RST files (default: %(default)s)",
    )
    parser.add_argument(
        "-o", "--output", dest="output_dir",
        default=str(Path(__file__).parent / "stubs"),
        help="Output directory for .pyi stubs (default: %(default)s)",
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show per-module progress and informational warnings.",
    )
    verbosity.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress progress output, printing only errors and warnings.",
    )
    parser.add_argument(
        "--strict-docs", action="store_true",
        help="Treat undocumented parameter issues as errors (non-zero exit).",
    )
    args = parser.parse_args()

    _State.verbose = args.verbose
    _State.quiet = args.quiet
    _State.strict_docs = args.strict_docs
    build_dir = Path(args.build_dir)
    output_dir = Path(args.output_dir)

    if not build_dir.exists():
        print("Error: {:s} directory not found. Run sphinx_gen_run.py first.".format(
            str(build_dir)), file=sys.stderr)
        return 1

    # Refuse to overwrite a non-empty output directory; this guards against
    # `-o` accidentally pointing at the wrong tree. The Makefile is
    # expected to remove the previous tree before invoking.
    if output_dir.exists() and any(output_dir.iterdir()):
        print(
            "Error: output directory is not empty: {:s}".format(str(output_dir)),
            file=sys.stderr,
        )
        return 1

    # Parse all RST files.
    rst_files = sorted(build_dir.glob("ion*.rst"))
    modules: dict[str, _ModuleInfo] = {}

    for rst_path in rst_files:
        if rst_path.name == "index.rst":
            continue
        module = _parse_rst_file(rst_path)
        if not module.name:
            continue
        existing = modules.get(module.name)
        if existing:
            existing.classes.extend(module.classes)
            existing.functions.extend(module.functions)
            existing.data.extend(module.data)
        else:
            modules[module.name] = module
            if _State.verbose:
                print("Parsed: {:s}".format(module.name))

    # Create implied parent packages so every module is part of a proper
    # package hierarchy.
    all_names = set(modules.keys())
    for name in sorted(all_names):
        parts = name.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[:i])
            if parent not in modules:
                modules[parent] = _ModuleInfo(name=parent)

    # Build class location map.
    class_locations = _build_class_locations(modules)

    # A type referenced in an annotation but defined in no module is almost
    # always a mistyped cross-reference target. Report it rather than emit a
    # stub naming a type nothing defines, which `mypy` would then read as an
    # unchecked annotation rather than as the error it is.
    for name in sorted(_find_missing_types(modules, class_locations)):
        print("Error: referenced type not defined: {:s}".format(name), file=sys.stderr)
        _State.missing_type_errors += 1

    # Load operator NamedTuple annotations (written by sphinx_doc_gen.py).
    operator_types = _load_operator_types(build_dir)

    class_traits = _load_class_traits(build_dir)
    module_all = _load_module_all(build_dir)
    for module in modules.values():
        module.all_names = module_all.get(module.name)
        for cls in module.classes:
            qualified_name = "{:s}.{:s}".format(module.name, cls.name)
            cls.final = qualified_name in class_traits.final
            if qualified_name in class_traits.constructed_by_new:
                _constructor_to_new(cls)

    # Generate stubs.
    stub_paths: list[Path] = []
    for _, module in sorted(modules.items()):
        op_types = operator_types if module.name == "ion.ops" else None
        stub_path = _emit_stub(
            module, output_dir, class_locations, modules, op_types,
        )
        stub_paths.append(stub_path)
        if _State.verbose:
            print("Generated: {:s}".format(str(stub_path)))

    if not _State.quiet:
        print("\nStubs written to: {:s}".format(str(output_dir)))
        print("Add to mypy config: mypy_path = doc/python_api/stubs")

    from sphinx_stub_validate import validate_stubs  # pylint: disable=import-outside-toplevel
    if validate_stubs(output_dir, stub_paths, sorted(modules.keys())) != 0:
        return 1

    if _State.parse_errors:
        print(
            "\n{:d} parse error(s) encountered".format(_State.parse_errors),
            file=sys.stderr,
        )
        return 1

    if _State.structure_errors:
        print(
            "\n{:d} structure error(s) encountered".format(_State.structure_errors),
            file=sys.stderr,
        )
        return 1

    if _State.missing_type_errors:
        print(
            "\n{:d} referenced type(s) not defined".format(_State.missing_type_errors),
            file=sys.stderr,
        )
        return 1

    if _State.undocumented_errors:
        print(
            "\n{:d} parameter documentation issue(s) encountered".format(
                _State.undocumented_errors,
            ),
            file=sys.stderr,
        )
        if _State.strict_docs:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
