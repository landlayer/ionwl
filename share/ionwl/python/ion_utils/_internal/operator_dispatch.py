# SPDX-License-Identifier: GPL-3.0-or-later

# Operator dispatch functions used by the Rust `operator_poll` / `operator_exec`
# entry points. Installed on `ion.ops` as `_poll`, `_exec`, and
# `_operator_call` during module creation.

from __future__ import annotations

__all__ = (
    "call",
)

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import ion.types


def _poll(instance: tuple[Any, ...]) -> str | None:
    """Call the poll function of the operator this instance belongs to.

    :param instance: The operator NamedTuple instance.
    :type instance: tuple[Any, ...]
    :rtype: str | None
    """
    poll_fn = getattr(type(instance), '_ion_poll', None)
    if poll_fn is None:
        return None
    result: str | None = poll_fn(instance)
    return result


def _exec(instance: tuple[Any, ...], event: ion.types.Event) -> bool | None:
    """Call the exec function of the operator this instance belongs to.

    :param instance: The operator NamedTuple instance.
    :type instance: tuple[Any, ...]
    :param event: The input event that triggered the operator.
    :type event: :class:`~ion.types.Event`
    :rtype: bool | None
    """
    cls: Any = type(instance)
    result = cls._ion_exec(instance, event)
    if result is not None and not isinstance(result, bool):
        raise RuntimeError(
            "Operator '{:s}' exec must return bool or None, got {:s}".format(
                cls._ion_operator_id, type(result).__name__,
            )
        )
    return result


def call(self: tuple[Any, ...], event: ion.types.Event) -> bool | None:
    """Execute this operator instance (descriptor-compatible).

    :param self: The operator NamedTuple instance.
    :type self: tuple[Any, ...]
    :param event: The event to forward to the operator.
    :type event: :class:`~ion.types.Event`
    :rtype: bool | None
    """
    import ion
    return ion._internal.operator_execute(self, event)
