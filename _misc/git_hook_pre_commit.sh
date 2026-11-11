#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later

# Pre-commit gate: reject a commit that `make format` would change, or that
# fails `make check_all` or `make test_all`.
#
# Install with `make hooks_install`, which symlinks this file into
# `.git/hooks/`. The symlink means editing this file changes the live hook, and
# it also means a fresh clone has no gate at all until that target is run.
#
# Deferring to `check_all` rather than naming individual checks is deliberate: a
# check added to the Makefile is then gated without editing this file. Naming a
# subset here instead lets a check drift out of the gate unnoticed, since
# nothing cross-references the two lists.
#
# `check_all` and `test_all` overlap on `check_mypy`, `check_namespace`,
# `check_python_comments` and `check_rust_comments`, so those four run twice.
# The duplicated cost is one stub regeneration plus one mypy pass, paid so that
# either target stays correct when run on its own.

# Stash unstaged changes so we only check what is being committed.
# Modern git's `stash push` exits 0 even when nothing was stashed, so
# `if git stash push; then stashed=1` would falsely set stashed=1 on a
# clean tree -- the cleanup pop would then pop a *pre-existing* stash
# entry, conflicting against the working tree. Gate on whether
# unstaged changes actually exist before pushing.
stashed=0
if ! git diff --quiet; then
    if git stash push --keep-index --quiet --message "pre-commit format check"; then
        stashed=1
    fi
fi

cleanup() {
    if [ "$stashed" = 1 ]; then
        git stash pop --quiet 2>/dev/null
    fi
}
trap cleanup EXIT

format_output=$(make format 2>&1)
format_status=$?
if [ "$format_status" -ne 0 ]; then
    echo "ERROR: 'make format' failed to run:" >&2
    echo "$format_output" >&2
    exit 1
fi

if ! git diff --quiet; then
    echo "ERROR: 'make format' would modify the following files:" >&2
    git diff --name-only >&2
    echo "" >&2
    echo "Run 'make format' and stage the changes before committing." >&2
    git checkout -- . 2>/dev/null
    exit 1
fi

# Run every check. Clippy and rustdoc lint levels are denied in Cargo.toml, and
# each check keeps its own cargo cache, so none invalidates another.
if ! make check_all; then
    echo "ERROR: 'make check_all' failed." >&2
    exit 1
fi

# Run the full test suite. Warnings fail the build itself: `build.warnings` in
# .cargo/config.toml denies them, so cargo exits non-zero rather than this hook
# scanning the output text for them.
if ! make test_all; then
    echo "ERROR: 'make test_all' failed." >&2
    exit 1
fi
