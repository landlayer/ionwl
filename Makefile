# Makefile for ionwl.

.PHONY: \
	all \
	help \
	build \
	build-bin \
	install \
	install_only \
	uninstall \
	hooks_install \
	test \
	test_all \
	test_pyapi \
	test_render \
	test_shutdown \
	doc \
	doc-gen \
	doc-gen-build \
	doc-html \
	doc-html-build \
	doc-stubs \
	doc-stubs-fresh \
	doc-readme \
	doc-publish \
	clean \
	clean-doc \
	check_all \
	check_ascii \
	check_clippy \
	check_features \
	check_integration_scripts \
	check_licenses \
	check_rustdoc \
	check_mypy \
	check_namespace \
	check_python_comments \
	check_readme \
	check_rtype \
	check_rust_comments \
	check_pylint \
	check_ruff \
	check_stubtest \
	check_vulture \
	format \
	update \
	upgrade \
	upgrade_git

# Optional local configuration. A `.env` file (KEY = value, gitignored) can
# override variables such as PREFIX, e.g. to `make install` into a local prefix:
#     PREFIX = $(HOME)/.local
# Command-line overrides (`make install PREFIX=...`) still take precedence.
-include .env

# -----------------------------------------------------------------------------
# Number of cores, for parallel recipes.
#
# $(OS) is only pre-set on Windows; derive it from uname elsewhere so the
# per-platform core counts below resolve.

OS ?= $(shell uname -s)

ifndef NPROCS
    NPROCS := 1
    ifeq ($(OS), Linux)
        NPROCS := $(shell nproc)
    endif
    ifeq ($(OS), NetBSD)
        NPROCS := $(shell getconf NPROCESSORS_ONLN)
    endif
    ifneq (,$(filter $(OS),Darwin FreeBSD))
        NPROCS := $(shell sysctl -n hw.ncpu)
    endif
endif

# Install directories.
PREFIX ?= /usr/local
BINDIR := $(PREFIX)/bin
DATADIR := $(PREFIX)/share/ionwl
# Display managers scan `wayland-sessions` directories on `XDG_DATA_DIRS`, so
# the session entry must land here rather than under the ionwl data directory.
SESSIONDIR := $(PREFIX)/share/wayland-sessions

# Documentation directories.
DOC_DIR := doc/python_api
BUILD_DIR := $(DOC_DIR)/build
HTML_DIR := $(BUILD_DIR)/_build/html

# Binary the doc extraction runs. Defaults to the release build (what ships,
# used by `make install`); the test and commit paths override this to the debug
# binary to skip a slow release compile, since doc content does not depend on
# the optimization level. `DOC_IONWL_BIN`, when set, pins the exact binary via
# IONWL_BIN so a stale release build cannot be picked up in its place.
DOC_IONWL_TARGET ?= build
DOC_IONWL_BIN ?=
DOC_SCRIPTS := $(sort $(shell find doc -name '*.py' -not -path '$(DOC_DIR)/examples/*' -not -path '$(BUILD_DIR)/*'))
DOC_EXAMPLES := $(wildcard $(DOC_DIR)/examples/*.py)
BUILTIN_SCRIPTS := $(sort $(shell find share/ionwl/python -name '*.py'))
CONFIG_SCRIPTS := config/default/ion_init.py
USER_SCRIPTS := $(wildcard scripts/*.py)
# All Python in tests/python: the unittest modules plus the run.py launcher.
PYAPI_SCRIPTS := $(sort $(wildcard tests/python/*.py))
# Python halves of the integration tests, called in-process via python_call.
INTEGRATION_SCRIPTS := $(sort $(wildcard tests/integration/python/scripts/*.py))
RESOURCE_SCRIPTS := $(sort $(shell find share/ionwl/resources -name '*.py'))
MISC_SCRIPTS := $(sort $(shell find _misc -name '*.py'))

# Sources that affect RST generation.
RST_INPUTS := $(shell find src -name '*.rs') $(DOC_DIR)/sphinx_doc_gen.py $(DOC_DIR)/sphinx_gen_run.py

# Codeberg Pages publishing. git-pages serves the tip of the `pages` branch at
# PAGES_URL. A Forgejo webhook (repository Settings -> Webhooks, type Forgejo,
# Target URL = PAGES_URL, Branch filter = pages) must be configured once so a
# push to the branch is served instead of ignored.
PAGES_REMOTE ?= origin
PAGES_BRANCH ?= pages
PAGES_URL ?= https://ideasman42.codeberg.page/IonWL/

# Default target: build everything ready for `make install`. The doc steps use
# the echo-less `*-build` workers so an install stays quiet; direct `make doc`
# keeps the progress markers.
all: build doc-html-build doc-stubs

# Sentinel tracking RST generation - rebuilds when inputs change.
$(BUILD_DIR)/.rst_stamp: $(RST_INPUTS)
	$(MAKE) doc-gen-build DOC_IONWL_TARGET=build-bin DOC_IONWL_BIN=target/debug/ionwl
	@touch $@

# Show available targets.
help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Build:"
	@echo "  build          Build the project (release)"
	@echo "  install        Build and install (PREFIX=$(PREFIX))"
	@echo "  install_only   Install binary, data files, and docs (PREFIX=$(PREFIX))"
	@echo "  uninstall      Remove installed files"
	@echo "  hooks_install  Install the git pre-commit hook"
	@echo "  test           Run all tests"
	@echo "  test_all       Run tests, rebuild docs/stubs, run checks"
	@echo "  test_render    Check the headless backend composes frames"
	@echo "  test_shutdown  Check a signal shuts the compositor down cleanly"
	@echo "  format         Format Rust and Python source files"
	@echo "  update         Update all cargo packages"
	@echo "  upgrade        Bump Cargo.toml version pins to the latest releases"
	@echo "  upgrade_git    Upgrade git dep revisions to latest commits"
	@echo ""
	@echo "Documentation:"
	@echo "  doc            Generate RST and build HTML docs"
	@echo "  doc-gen        Generate RST files from Python docstrings"
	@echo "  doc-html       Build HTML documentation with Sphinx"
	@echo "  doc-stubs      Regenerate .pyi type stubs from RST"
	@echo "  doc-readme     Update source layout in architecture readme"
	@echo "  doc-publish    Publish HTML docs to Codeberg Pages ($(PAGES_BRANCH) branch)"
	@echo "  clean          Remove build artifacts and generated docs"
	@echo ""
	@echo "Checks:"
	@echo "  check_all      Run all checks"
	@echo "  check_ascii    Ensure source files are ASCII-only"
	@echo "  check_clippy   Run clippy (levels set in Cargo.toml)"
	@echo "  check_integration_scripts  Check integration test scripts against their Rust callers"
	@echo "  check_licenses Check SPDX license headers"
	@echo "  check_mypy     Run mypy strict type checking"
	@echo "  check_namespace Verify Python modules define __all__"
	@echo "  check_python_comments  Ensure comments don't violate our conventions"
	@echo "  check_readme   Check the architecture readme's source layout is current"
	@echo "  check_rtype    Check each documented :rtype: against its Rust function"
	@echo "  check_rust_comments  Ensure Rust comments end with punctuation"
	@echo "  check_stubtest Check the stubs against the runtime with stubtest"
	@echo "  check_pylint   Run pylint on doc scripts"
	@echo "  check_ruff     Run ruff linter on doc scripts"
	@echo "  check_vulture  Run vulture dead code finder"

# Build the project.
build:
	cargo build --release

# Build the debug ionwl binary (used by tests and commit-path doc extraction).
build-bin:
	cargo build --bin ionwl

# Build and install.
install: all install_only

# Install without rebuilding. The `install` target may rebuild even when an
# existing build has just been produced. This isolates the install step to
# copying files, for use when the caller can rely on an existing build.
install_only:
	install -Dm755 target/release/ionwl $(DESTDIR)$(BINDIR)/ionwl
	install -Dm755 target/release/ionwl-cmd $(DESTDIR)$(BINDIR)/ionwl-cmd
	install -Dm644 share/wayland-sessions/ionwl.desktop $(DESTDIR)$(SESSIONDIR)/ionwl.desktop
	rm -rf $(DESTDIR)$(DATADIR)
	# Ensure the parent directory exists for `cp -r`.
	install -d $(dir $(DESTDIR)$(DATADIR))
	cp -r share/ionwl $(DESTDIR)$(DATADIR)
	find $(DESTDIR)$(DATADIR)/python -type d -name __pycache__ -exec rm -rf {} +
	cp -r $(DOC_DIR)/stubs/ion $(DESTDIR)$(DATADIR)/python/ion
	install -d $(DESTDIR)$(DATADIR)/doc
	cp -r $(HTML_DIR)/. $(DESTDIR)$(DATADIR)/doc/
	# Sphinx build cache is not needed at runtime.
	rm -rf $(DESTDIR)$(DATADIR)/doc/.doctrees

# Remove installed files.
uninstall:
	rm -f $(DESTDIR)$(BINDIR)/ionwl
	rm -f $(DESTDIR)$(BINDIR)/ionwl-cmd
	rm -f $(DESTDIR)$(SESSIONDIR)/ionwl.desktop
	rm -rf $(DESTDIR)$(DATADIR)

# Install the git pre-commit hook, which gates a commit on `format`,
# `check_all` and `test_all`.
#
# A symlink rather than a copy, so the tracked hook and the installed one
# cannot drift, and a relative one so it survives the checkout being moved.
# Git ignores `.git/hooks/`, so a fresh clone has no gate until this runs; it
# is not wired into `all` because installing a hook is a choice the person
# cloning makes, not a build step.
#
# The hooks directory comes from `git rev-parse` rather than a literal
# `.git/hooks`: in a worktree `.git` is a file and the hooks live in the main
# checkout, and `core.hooksPath` moves them anywhere. That also makes the
# final `test -e` meaningful, since a relative link only resolves from a hooks
# directory two levels inside the work tree.
#
# An existing regular file is somebody's own hook, so refuse rather than
# overwrite it. Re-installing over our own symlink is the common case.
hooks_install:
	@hooks_dir=$$(git rev-parse --git-path hooks) && test -d "$$hooks_dir" || { \
		echo "ERROR: no git hooks directory, not a git checkout."; \
		exit 1; \
	}; \
	hook="$$hooks_dir/pre-commit"; \
	if [ -e "$$hook" ] && [ ! -L "$$hook" ]; then \
		echo "ERROR: $$hook already exists and is not a symlink."; \
		echo "Move it aside first, it will not be overwritten."; \
		exit 1; \
	fi; \
	ln -sf ../../_misc/git_hook_pre_commit.sh "$$hook" && test -e "$$hook" || { \
		echo "ERROR: $$hook does not resolve, install it by hand."; \
		exit 1; \
	}; \
	echo "Installed $$hook -> _misc/git_hook_pre_commit.sh"

# Run all tests (regenerates RST docs if sources changed).
# Doctests are skipped because RST docstrings in `python/mod.rs` are not valid Rust.
test: $(BUILD_DIR)/.rst_stamp
	cargo test --workspace --lib
	_misc/test_cargo_integration_sharded.sh $(NPROCS)
	$(MAKE) test_pyapi
	$(MAKE) test_render
	$(MAKE) test_shutdown

# Run the Python API unit tests inside the real ionwl binary.
# `tests/python/run.py` launches ionwl with a temporary config that runs the
# `test_*.py` unittest modules at config-load and exits (no display needed).
test_pyapi:
	cargo build --bin ionwl
	IONWL_BIN=target/debug/ionwl python3 tests/python/run.py

# Check the render path composes frames. Drives the real binary on the headless
# backend and reads the `IONWL_TIMING` frame probe back, so this is the only
# suite that renders; `ionwl-cmd` drives the compositor's state over IPC.
test_render:
	cargo build --bin ionwl --bin ionwl-cmd
	IONWL_BIN=target/debug/ionwl python3 tests/python/run_render.py

# Check that a termination signal shuts the compositor down rather than
# killing it. Drives the real binary on the headless backend, reaching the
# main loop that the unit suites never enter.
test_shutdown:
	cargo build --bin ionwl
	IONWL_BIN=target/debug/ionwl python3 tests/python/run_shutdown.py

# Run all tests, rebuild docs and stubs from scratch, run checks.
# Docs are regenerated before integration tests because
# `python_config_mypy_strict` requires RST files to exist.
test_all:
	cargo test --workspace --lib
	rm -rf doc/python_api/build doc/python_api/stubs
	$(MAKE) doc-stubs DOC_IONWL_TARGET=build-bin DOC_IONWL_BIN=target/debug/ionwl
	_misc/test_cargo_integration_sharded.sh $(NPROCS)
	$(MAKE) test_pyapi
	$(MAKE) test_render
	$(MAKE) test_shutdown
	status=0; \
	$(MAKE) check_mypy & mypy_pid=$$!; \
	$(MAKE) check_python_comments & comments_pid=$$!; \
	$(MAKE) check_rust_comments & rust_comments_pid=$$!; \
	$(MAKE) check_namespace & namespace_pid=$$!; \
	wait $$mypy_pid || status=$$?; \
	wait $$comments_pid || status=$$?; \
	wait $$rust_comments_pid || status=$$?; \
	wait $$namespace_pid || status=$$?; \
	exit $$status

# Generate RST files and build HTML documentation (with progress output).
doc: doc-gen doc-html

# Progress-reporting wrappers for direct use. The actual work lives in the
# echo-less `*-build` workers below, which `make install` (via `all`) and
# `doc-stubs` share so an install produces no doc chatter.
doc-gen: doc-gen-build
	@echo "Generated RST documentation."

doc-html: doc-html-build
	@echo "Documentation built at: $(HTML_DIR)/index.html"

# Generate RST files from Python doc-strings (runs ionwl to access ion module).
# `--strict-docs` promotes soft warnings (e.g. unreferenced examples) to errors.
doc-gen-build: $(DOC_IONWL_TARGET)
	IONWL_BIN="$(DOC_IONWL_BIN)" python3 $(DOC_DIR)/sphinx_gen_run.py --strict-docs --quiet

# Build HTML documentation with Sphinx.
# `-W` treats Sphinx warnings as errors; `--keep-going` collects all of them
# before failing so a single run surfaces the full list.
doc-html-build: doc-gen-build
	sphinx-build -W --keep-going --quiet --jobs $(NPROCS) -b html $(BUILD_DIR) $(HTML_DIR)

# Regenerate .pyi type stubs from RST.
# The stub generator refuses to overwrite a non-empty output dir, so wipe it first.
# `--strict-docs` promotes :param:/:type: omissions to errors so CI catches them.
doc-stubs: doc-gen-build
	rm -rf $(DOC_DIR)/stubs
	python3 $(DOC_DIR)/sphinx_stub_gen.py --strict-docs --quiet

# Update auto-generated source layout in architecture README.
doc-readme:
	python3 doc/architecture/readme_update.py

# Build the HTML docs and publish them to Codeberg Pages. A freshly built orphan
# commit is force-pushed to $(PAGES_REMOTE)/$(PAGES_BRANCH), so the branch holds
# only the current snapshot. The publish helper strips the Sphinx build cache.
doc-publish: doc-html-build
	python3 _misc/doc_publish.py \
		--html-dir $(HTML_DIR) \
		--remote $(PAGES_REMOTE) \
		--branch $(PAGES_BRANCH)
	@echo "Live at $(PAGES_URL) once the Forgejo webhook fires."

# Run all checks.
check_all: \
	check_ascii \
	check_clippy \
	check_features \
	check_integration_scripts \
	check_licenses \
	check_mypy \
	check_namespace \
	check_pylint \
	check_python_comments \
	check_readme \
	check_rtype \
	check_ruff \
	check_rust_comments \
	check_rustdoc \
	check_stubtest \
	check_vulture

# Ensure all source files are ASCII-only.
# The C locale matches bytes, as a UTF-8 locale skips invalid UTF-8.
check_ascii:
	@LC_ALL=C git --no-pager grep -n -P '[^\x00-\x7F]' -- '*.rs' '*.py' '*.rst' '*.toml' Makefile; \
	case $$? in \
		0) echo "ERROR: non-ASCII characters found"; exit 1;; \
		1) ;; \
		*) echo "ERROR: git grep failed"; exit 1;; \
	esac

# Run clippy on all targets of every workspace member. The lint policy lives
# in Cargo.toml's `[workspace.lints.clippy]` so the gate, a manual
# `cargo clippy`, and rust-analyzer share one configuration and never
# invalidate each other's compile cache.
check_clippy:
	cargo clippy --workspace --all-targets --features test_support

# Lint the feature combinations and release profile no other check compiles.
#
# Clippy rather than `cargo check`: an `#[expect]` naming a clippy lint is only
# validated when clippy is what compiles the code, and `check_clippy` builds
# default features only - so without this, one inside a `not(feature = ...)` arm
# would rot unseen.
#
# `icon_legacy` implies `icon`, so the icon axis has three reachable states and
# the default build only ever exercises the last of them. Code behind `#[cfg]`
# guards that select on `icon` alone is otherwise never compiled, so a borrow or
# type error there reaches a release without any check failing.
#
# The release profile is a further axis: every other check compiles with
# `debug_assertions`, so code that only builds with them on would first fail at
# `make build`. Test targets are left out as they never ship. Three lints are
# allowed for it alone, as they judge a function's body, which loses its debug
# assertions in release: the layout parity checks are left empty and
# `IonScene::read` looks pure.
#
# Each combination builds into its own target directory so the four run
# concurrently. Sharing one directory serializes them on cargo's
# build-directory lock, gaining nothing over running them in sequence. The
# cost is the duplicated artifacts, kept under `target/` so `cargo clean`
# reaches them.
check_features:
	CARGO_TARGET_DIR=target/features/none \
		cargo clippy --no-default-features & none_pid=$$!; \
	CARGO_TARGET_DIR=target/features/icon \
		cargo clippy --no-default-features --features icon & icon_pid=$$!; \
	CARGO_TARGET_DIR=target/features/legacy \
		cargo clippy --no-default-features --features icon,icon_legacy & legacy_pid=$$!; \
	CARGO_TARGET_DIR=target/features/release \
		cargo clippy --release -- \
		-A clippy::must_use_candidate \
		-A clippy::unnecessary_struct_initialization \
		-A clippy::unused_self & release_pid=$$!; \
	status=0; wait $$none_pid || status=$$?; wait $$icon_pid || status=$$?; \
	wait $$legacy_pid || status=$$?; wait $$release_pid || status=$$?; exit $$status

# Check that all source files have SPDX license headers.
check_licenses:
	python3 _misc/check_licenses.py

# Regenerate the stubs for the checks that read them: the stubs on disk
# describe whichever commit last generated them, and a checkout leaves them in
# place. A prerequisite, so one `make` regenerates them once for all its checks.
doc-stubs-fresh:
	$(MAKE) doc-stubs DOC_IONWL_TARGET=build-bin DOC_IONWL_BIN=target/debug/ionwl

# Run mypy strict type checking on the Python, against fresh stubs.
check_mypy: doc-stubs-fresh
	mypy --strict $(DOC_SCRIPTS)
	MYPYPATH=$(DOC_DIR)/stubs:share/ionwl/python \
		mypy --strict \
		$(DOC_EXAMPLES) $(BUILTIN_SCRIPTS) $(CONFIG_SCRIPTS) $(USER_SCRIPTS) $(RESOURCE_SCRIPTS) $(MISC_SCRIPTS) \
		$(PYAPI_SCRIPTS) $(INTEGRATION_SCRIPTS)

# Check the stubs against the live `ion` module with mypy's stubtest, inside
# the binary where `ion` exists, against fresh stubs.
check_stubtest: doc-stubs-fresh
	IONWL_BIN=target/debug/ionwl python3 $(DOC_DIR)/sphinx_gen_run.py --stubtest

# Check each documented method's `:rtype:` against the Rust `fn` behind it,
# reading the freshly generated RST so macro-built docstrings are covered.
check_rtype: doc-stubs-fresh
	python3 _misc/check_rtype.py

# Verify that every Python module defines `__all__`.
check_namespace:
	python3 _misc/check_namespace.py --skip doc/python_api/build --skip doc/python_api/examples \
		--skip config/default/ion_init.py --skip config/minimal/ion_init.py \
		$(DOC_SCRIPTS) $(BUILTIN_SCRIPTS) $(CONFIG_SCRIPTS) $(USER_SCRIPTS) $(MISC_SCRIPTS)

# Check that every public name in the integration test scripts is named by a
# Rust test, and that every name a Rust test passes is defined.
check_integration_scripts:
	python3 _misc/check_integration_scripts.py

# Ensure Python `#` comments don't violate our conventions.
check_python_comments:
	python3 _misc/check_python_comments.py

# Ensure the architecture readme's generated source layout matches `src`.
check_readme:
	python3 doc/architecture/readme_update.py --check

# Ensure standalone Rust `//` comments end with terminating punctuation.
check_rust_comments:
	python3 _misc/check_rust_comments.py

# Run pylint on doc generation, user and misc scripts.
check_pylint:
	pylint $(DOC_SCRIPTS) $(USER_SCRIPTS) $(MISC_SCRIPTS)

# Run ruff linter on doc generation scripts and the shipped library.
check_ruff:
	ruff check $(DOC_SCRIPTS) $(BUILTIN_SCRIPTS)

# Check the rustdoc comments: intra-doc links resolve, code blocks parse.
#
# The lint levels live in Cargo.toml's `[workspace.lints.rustdoc]` so this and
# a bare `cargo doc` share one configuration. `--document-private-items` is required,
# not cosmetic: almost everything here is `pub(crate)`, and without it rustdoc
# never examines the doc comments that carry the links. Shares no cache with
# clippy, so neither invalidates the other.
check_rustdoc:
	cargo doc --workspace --no-deps --document-private-items --features test_support

# Run vulture dead code finder on doc generation scripts and the shipped library.
check_vulture:
	vulture --min-confidence=61 $(DOC_SCRIPTS) $(BUILTIN_SCRIPTS)

# Format Rust and Python source files (both run concurrently, each parallelized).
format:
	find src tests crates -name '*.rs' -print0 | xargs -0 -P $(NPROCS) -n 8 rustfmt --edition 2024 & rustfmt_pid=$$!; \
	autopep8 --in-place --jobs 0 --recursive doc/ src/ scripts/ share/ & autopep8_pid=$$!; \
	status=0; wait $$rustfmt_pid || status=$$?; wait $$autopep8_pid || status=$$?; exit $$status

# Update `Cargo.lock` to the newest versions permitted by the `Cargo.toml` pins.
# This never edits `Cargo.toml`; use `upgrade` to raise the pins themselves.
update:
	cargo update

# Rewrite the `Cargo.toml` version requirements to the latest releases, then
# refresh the lockfile to match. Needs cargo-edit (`cargo install cargo-edit`),
# which provides the `cargo upgrade` subcommand.
upgrade:
	@command -v cargo-upgrade >/dev/null 2>&1 || { \
		echo "ERROR: cargo-upgrade not found; install with 'cargo install cargo-edit'."; \
		exit 1; \
	}
	cargo upgrade --incompatible
	cargo update

# Upgrade GIT dependency revisions in `Cargo.toml` to their latest commits.
upgrade_git:
	python3 _misc/upgrade_git.py

# Remove build artifacts and generated documentation.
clean: clean-doc
	cargo clean

# Clean generated documentation.
clean-doc:
	rm -rf doc/python_api/build
