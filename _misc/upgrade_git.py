# SPDX-License-Identifier: GPL-3.0-or-later

"""Update git dependency revisions in Cargo.toml to their latest commits."""

__all__ = (
    "main",
)

import re
import subprocess
import sys
from pathlib import Path

_CARGO_TOML = Path(__file__).resolve().parent.parent / "Cargo.toml"


def _latest_sha(url: str) -> str | None:
    """Resolve the latest commit SHA for a git URL."""
    result = subprocess.run(
        ["git", "ls-remote", url, "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print("  warning: failed to query {:s}".format(url), file=sys.stderr)
        return None
    parts = result.stdout.split()
    return parts[0] if parts else None


def main() -> None:
    """Rewrite each git dependency `rev` in Cargo.toml to its latest commit."""
    text = _CARGO_TOML.read_text()
    lines = text.splitlines(True)
    out: list[str] = []
    git_url: str | None = None
    changed = 0
    # Cache so repeated URLs (e.g. smithay + smithay-drm-extras) query once.
    cache: dict[str, str | None] = {}

    for line in lines:
        # Reset on section boundaries to avoid stale git_url from a
        # dependency that uses branch/tag instead of rev.
        if line.startswith("["):
            git_url = None

        m_git = re.match(r'^git\s*=\s*"(.+?)"', line)
        if m_git:
            git_url = m_git.group(1)

        m_rev = re.match(r'^(rev\s*=\s*")([0-9a-f]+)(".*)', line)
        if m_rev and git_url is not None:
            if git_url not in cache:
                cache[git_url] = _latest_sha(git_url)
            sha = cache[git_url]
            old = m_rev.group(2)
            if sha is not None and sha != old:
                line = m_rev.group(1) + sha + m_rev.group(3) + "\n"
                changed += 1
                print("{:s}: {:s} -> {:s}".format(git_url, old[:12], sha[:12]))
            git_url = None

        out.append(line)

    if changed:
        _CARGO_TOML.write_text("".join(out))
    print("Updated {:d} revision(s).".format(changed))


if __name__ == "__main__":
    main()
