# SPDX-License-Identifier: GPL-3.0-or-later

"""Run the code an IPC command sends, optionally streaming its output.

The one executor behind the Rust ``python_execute``, whether or not output is
redirected, so both modes compile, run and fail the same way.
"""

from __future__ import annotations

__all__ = (
    "execute",
)

import builtins
import contextlib
import io
import traceback
from typing import Any


def execute(code: str, mode: str, path: str | None, imports: list[str], fd: int | None) -> str | None:
    """Compile and run *code*, streaming stdout/stderr to *fd* when given.

    Output reaches *fd* as it is written, a write at a time. An exception
    propagates to the caller, which reports it; when streaming, its traceback
    is written to *fd* first, since that is what the client reads.

    :param code: Python source code.
    :param mode: ``"eval"`` or ``"exec"``.
    :param path: The file *code* was read from, or ``None`` for code sent
       inline. Either runs as ``__main__``.
    :param imports: Modules to import first, each bound to its top-level name.
    :param fd: File descriptor to write output to, ``None`` to leave output
       where it goes.
    :return: For eval, the ``str`` of the result, otherwise ``None``.
    """
    if fd is None:
        return _execute(code, mode, path, imports)
    # The buffered layer between the two is not for buffering - each write
    # passes straight through it - but because `TextIOWrapper` is specified
    # over a buffered stream and drops what a raw one declines to take. A
    # blocking pipe write returns short when a signal lands part way through
    # it, which is possible here: the reader drains the pipe as fast as it
    # can, but a write big enough to fill it still waits on the reader being
    # scheduled. Over the raw stream alone those bytes would go missing from
    # the middle of the output with nothing reporting it.
    writer = io.TextIOWrapper(
        io.BufferedWriter(io.FileIO(fd, mode="w", closefd=False), buffer_size=1),
        write_through=True,
    )
    try:
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            try:
                return _execute(code, mode, path, imports)
            except BaseException:
                # Not only `Exception`: a payload's `sys.exit()` raises
                # `SystemExit`, and the client wants its traceback like any other.
                # A client that hung up must not turn the payload's error into
                # a broken pipe, here or in the flush below.
                with contextlib.suppress(OSError):
                    writer.write(traceback.format_exc())
                raise
    finally:
        # Closed (flushing it; `closefd=False` leaves the descriptor to the
        # caller) rather than left to whenever its last reference goes. The
        # caller closes the descriptor as soon as this returns, and the
        # executed code may keep the writer - a logging handler bound to
        # `sys.stderr` - so a later write would land on a descriptor that is
        # closed, or worse, reused. Closed, it raises instead.
        with contextlib.suppress(OSError):
            writer.close()


def _execute(code: str, mode: str, path: str | None, imports: list[str]) -> str | None:
    # As `__main__` has them: `__builtins__` the module, where `exec` would
    # otherwise insert its dict, and `__name__`, which would otherwise resolve
    # to the builtins module's own.
    namespace: dict[str, Any] = {"__builtins__": builtins, "__name__": "__main__"}
    if path is not None:
        namespace["__file__"] = path
    for module in imports:
        namespace[module.partition(".")[0]] = __import__(module)
    compiled = compile(code, "<ipc>" if path is None else path, mode)
    if mode == "eval":
        return str(eval(compiled, namespace))
    exec(compiled, namespace)  # noqa: S102
    return None
