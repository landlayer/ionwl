# SPDX-License-Identifier: GPL-3.0-or-later

"""
Check that all tracked source files have an SPDX license header.

Every ``*.py`` and ``*.rs`` file must contain ``SPDX-License-Identifier``
on the first line, or on the second line when the first is a shebang. The
license is ``GPL-3.0-or-later``, except in a crate under ``crates/``, whose
files carry the ``license`` of its own ``Cargo.toml``. The Python API
examples are exempt: the docs include them verbatim.
"""

__all__ = (
    "main",
)

import functools
import sys
import tomllib

from git_files import tracked_paths_get

_LICENSE_DEFAULT = "GPL-3.0-or-later"
_CRATES_DIR = "crates/"


@functools.cache
def _crate_license_get(crate_dir: str) -> str:
    """Return the ``license`` of the crate in *crate_dir*."""
    with open("{:s}/Cargo.toml".format(crate_dir), "rb") as fh:
        license_id: str = tomllib.load(fh)["package"]["license"]
    return license_id


def _license_get(filepath: str) -> str:
    """Return the license the file at *filepath* must carry."""
    if filepath.startswith(_CRATES_DIR):
        crate_name = filepath[len(_CRATES_DIR):].split("/", 1)[0]
        return _crate_license_get(_CRATES_DIR + crate_name)
    return _LICENSE_DEFAULT


def _check_file(filepath: str) -> str | None:
    """Return an error string, or None if the file is correct."""
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            first_line = fh.readline()
            if first_line.startswith("#!"):
                spdx_line = fh.readline()
            else:
                spdx_line = first_line
            next_line = fh.readline()
    except (OSError, UnicodeDecodeError):
        return None  # Skip unreadable files.

    license_id = _license_get(filepath)
    if "SPDX-License-Identifier: {:s}".format(license_id) not in spdx_line:
        return "missing SPDX header ({:s})".format(license_id)
    if next_line.strip():
        return "missing blank line after SPDX header"
    return None


def main() -> int:
    """Check all tracked source files for SPDX headers."""
    paths = tracked_paths_get("*.py", "*.rs", ":(exclude)doc/python_api/examples/")
    if paths is None:
        return 1

    errors = [(p, err) for p in paths if (err := _check_file(p)) is not None]
    for path, err in errors:
        print("{:s}: {:s}".format(path, err))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
