############
Command Line
############

ionwl
=====

This runs the compositor. It is configured through the Python config file
(see :doc:`configure`), so the command line stays minimal.

.. literalinclude:: ionwl_help.txt
   :language: none

ionwl-cmd
=========

This communicates with the running compositor over its IPC socket.

Only the user running the compositor can connect to the socket, and a process
running as anyone else is refused. The Python sent over it runs inside the
compositor with its full authority, just as the config does, so access to the
socket is equivalent to editing the config and reloading it.

Commands run on the compositor's main loop, with no time limit. One that does
not return, such as an endless loop, a ``time.sleep`` or a ``subprocess.run``
waiting on its child, freezes the session until it does. Start long-running
work with :func:`ion.utils.exec` or :func:`ion.utils.shell` rather than
waiting on it.

The exit status and output cover the command alone, not a hook or generator
step it leaves to run later. Those run after ``ionwl-cmd`` exits, with output
going to the compositor's stdout, errors to its log, and
:data:`ion.app.ipc_args` empty.

``ionwl-cmd`` must match the running compositor's version: after upgrading,
restart the compositor. Scripts should run ``ionwl-cmd`` rather than connect to
the socket, whose format is private and may change.

The primary way to perform tasks is by executing Python.

.. literalinclude:: ionwl_cmd_help.txt
   :language: none

Each command has options of its own, which follow it on the command line.

ping
----

.. literalinclude:: ionwl_cmd_ping_help.txt
   :language: none

python-eval
-----------

.. literalinclude:: ionwl_cmd_python_eval_help.txt
   :language: none

python-exec
-----------

.. literalinclude:: ionwl_cmd_python_exec_help.txt
   :language: none

python-file
-----------

.. literalinclude:: ionwl_cmd_python_file_help.txt
   :language: none
