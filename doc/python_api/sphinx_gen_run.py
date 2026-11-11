#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Run sphinx_doc_gen.py inside ionwl to extract documentation, or with
``--stubtest``, sphinx_stubtest.py to check the stubs against the runtime.

Both need the live ``ion`` module, which exists only inside ionwl. This script
creates a temporary HOME with an ion_init.py that runs the chosen script and
then exits ionwl. It runs ionwl on its own headless backend, so it needs no
display and no host compositor.
"""

__all__ = (
    "main",
)

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    """Launch ionwl headless and run a documentation script against the live module."""
    parser = argparse.ArgumentParser(
        description="Run ionwl headless to extract Sphinx RST documentation, or check the stubs.",
    )
    parser.add_argument(
        "--stubtest", action="store_true",
        help="Check the generated stubs against the runtime instead.",
    )
    parser.add_argument(
        "--strict-docs", dest="strict_docs", action="store_true",
        help="Treat documentation warnings as errors.",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress progress output, printing only errors and warnings.",
    )
    args = parser.parse_args()
    if args.stubtest and (args.strict_docs or args.quiet):
        parser.error("--stubtest takes neither --strict-docs nor --quiet")

    script_dir = Path(__file__).parent.resolve()
    script_name = "sphinx_stubtest" if args.stubtest else "sphinx_doc_gen"
    script_path = script_dir / "{:s}.py".format(script_name)

    if not script_path.exists():
        print("Error: {:s} not found".format(str(script_path)), file=sys.stderr)
        sys.exit(1)

    # Locate the ionwl binary. An explicit `IONWL_BIN` overrides detection so
    # the test and commit paths can pin the freshly-built debug binary (doc
    # content is opt-level independent); otherwise prefer release over debug.
    project_root = script_dir.parent.parent
    ionwl_env = os.environ.get("IONWL_BIN")
    if ionwl_env:
        ionwl_bin = Path(ionwl_env).resolve()
    else:
        ionwl_bin = project_root / "target" / "release" / "ionwl"
        if not ionwl_bin.exists():
            ionwl_bin = project_root / "target" / "debug" / "ionwl"
    if not ionwl_bin.exists():
        print("Error: ionwl binary not found (IONWL_BIN, target/release, or target/debug)", file=sys.stderr)
        print("Run 'cargo build' first.", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="ionwl_doc_") as tmp_home_str:
        tmp_home = Path(tmp_home_str)

        # Create .config/ionwl directory structure
        config_dir = tmp_home / ".config" / "ionwl"
        config_dir.mkdir(parents=True)

        # The compositor creates its Wayland and IPC sockets here.
        runtime_dir = tmp_home / "runtime"
        runtime_dir.mkdir()
        os.chmod(runtime_dir, 0o700)

        # Build args list forwarded to the script's `main()`.
        script_args: list[str] = []
        if args.strict_docs:
            script_args.append("--strict-docs")
        if args.quiet:
            script_args.append("--quiet")

        # Write ion_init.py that runs the script and exits via startup hook.
        init_py = config_dir / "ion_init.py"
        init_py.write_text('''\
# Auto-generated config for running a documentation script
import sys
sys.path.insert(0, {script_dir!r})

def on_startup():
    import os
    import sys
    import traceback
    try:
        import {script_name}
        rc = {script_name}.main({script_args!r})
    except SystemExit as ex:
        # Stubtest and argparse exit on error, which must still reach `os._exit`.
        if isinstance(ex.code, int | None):
            rc = ex.code
        else:
            # Report a message exit code as the interpreter would.
            print(ex.code, file=sys.stderr)
            rc = 1
    except Exception:
        traceback.print_exc(file=sys.stderr)
        rc = 1
    # `os._exit` skips Python's atexit/stdio flush, so flush manually
    # to ensure any prints (especially warnings) reach the caller.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(int(rc or 0))

import ion.app
ion.app.hooks.compositor_startup_post.append(on_startup)
'''.format(script_dir=str(script_dir), script_name=script_name, script_args=script_args))

        env = os.environ.copy()
        env["HOME"] = str(tmp_home)
        env["XDG_RUNTIME_DIR"] = str(runtime_dir)
        # Put the built binaries' directory first on PATH so doc generation can
        # capture `ionwl` / `ionwl-cmd` `--help` by invoking them by bare name.
        env["PATH"] = os.pathsep.join((str(ionwl_bin.parent), env.get("PATH", "")))
        env["IONWL_BACKEND"] = "headless"
        # Extraction draws nothing worth a GPU, and software rendering keeps
        # this runnable where there is no usable one.
        env["LIBGL_ALWAYS_SOFTWARE"] = "1"
        # Suppress noisy log output during doc generation.
        env["RUST_LOG"] = "error"
        # Doc extraction has no need to display fonts.
        env["IONWL_NO_FONTS"] = "1"

        try:
            result = subprocess.run(
                [str(ionwl_bin)],
                env=env,
                # Stubtest writes a non-strict mypy cache into its working
                # directory, which would invalidate the `check_mypy` one.
                cwd=str(tmp_home if args.stubtest else project_root),
                capture_output=False,
                check=False,
            )
            if result.returncode != 0:
                print("ionwl exited with code {:d}".format(result.returncode), file=sys.stderr)
                sys.exit(result.returncode)
        except KeyboardInterrupt:
            print("\nInterrupted.")
            sys.exit(1)

    if not args.quiet and not args.stubtest:
        print("Documentation extraction complete.")


if __name__ == "__main__":
    main()
