============
Architecture
============


Source Layout
=============

.. SOURCE_LAYOUT_BEGIN

::

  src/
  +- main.rs         IonWL - A Wayland compositor inspired by Notion
  +- lib.rs          IonWL - A Wayland compositor inspired by Notion
  +- collections.rs  Generic collection utilities shared across subsystems
  +- color.rs        Color types: [`ColorRGBA`] and [`ColorRGB`]
  +- enums.rs        Macros for string-keyed enum and map definitions
  +- geom.rs         Geometry primitives: [`Point`], [`Size`], and [`Rect`]
  +- system.rs       Thin wrappers around system calls
  +- state/          Compositor state and main event loop
  |   +- backend_drm.rs      DPMS power control: the hardware power state and the layout mirror of it
  |   +- client_popup.rs     Client popups: resolving an xdg or input-method popup's output,
  |   +- config.rs           Configuration loading and preference application: running the config
  |   +- cursor.rs           Cursor image state, the cursor-icon stack, the drag lifetime, and grab
  |   +- deferred.rs         Deferred-work engines, and how to choose between them
  |   +- devices.rs          Per-device state: keyboard, pointer, and tablet registries
  |   +- dnd.rs              Drag-and-drop state, from the `start_drag` that opens a drag to the drop
  |   +- focus.rs            Focus plumbing: resolving the focused surface, syncing keyboard and pointer
  |   +- generator.rs        Generator-based operator execution: dispatch, stepping and cancellation
  |   +- idle.rs             Idle tracking: the activity timer and the periodic inhibit check
  |   +- ipc.rs              IPC client plumbing: reading a client's commands and running them
  |   +- layer.rs            Layer-surface state: pending maps, focus release, exclusive zones, and the
  |   +- operator.rs         Operator dispatch and the post-step every outcome runs through
  |   +- output.rs           Output state: damage tracking, active-output sync, scale and
  |   +- output_geometry.rs  Output geometry: applying mode, position, scale and transform changes
  |   +- overlay_resolve.rs  Main-side overlay resolution: flatten the overlay tree into the order the
  |   +- pointer_over.rs     Cached "what is under the pointer" hit-test result
  |   +- reconfigure.rs      Window reconfigure (configure-event) propagation across frames and workspaces
  |   +- revisioned.rs       The two halves of change tracking: [`Revisioned`], a value whose counter
  |   +- run.rs              Compositor entry point: the `run()` event loop and the
  |   +- scene.rs            The shared render scene and its lock machinery: [`IonScene`], the
  |   +- text_resolve.rs     Main-side text resolution: rasterize the text the next frame draws so the
  |   +- titlebar.rs         Title widths measured for the titlebar, and the `xdg_toplevel_icon` sizes
  |   +- ui_popup.rs         Compositor-drawn popups: the menus, messages and tooltips on the UI popup
  |   +- window.rs           Window lifecycle: mapping a pending window, removal and its damage, and
  |
  +- tiling/         The window layout ([`LayoutManager`]) and the overlays drawn over it
  |   +- layout/       [`LayoutManager`]: the tiling model
  |   |   +- desktop.rs     `LayoutManager` desktop operations: creation, removal, switching, and
  |   |   +- floating.rs    `LayoutManager` floating-layer operations: entries, z-order, geometry
  |   |   +- frame.rs       `LayoutManager` frame operations: geometry, decoration rects, splitting
  |   |   +- fullscreen.rs  `LayoutManager` fullscreen tracking: which window is fullscreen on which
  |   |   +- output.rs      `LayoutManager` output operations: adding and removing outputs, their
  |   |   +- tabs.rs        Tab-layout geometry for frames on `LayoutManager`
  |   |   +- window.rs      Window-management methods on `LayoutManager`
  |   |   +- workspace.rs   `LayoutManager` workspace operations: creation, removal, naming, and
  |   |
  |   +- config.rs     Layout configuration for tiling
  |   +- desktop.rs    Desktop - groups floating windows, floating workspaces, and
  |   +- floating.rs   Floating window layer
  |   +- focus.rs      Focus state and navigation for tiling layout
  |   +- frame.rs      Frame - a tabbed container holding one or more windows
  |   +- ids.rs        `IonCore` ID types using slotmap for generational indices
  |   +- output.rs     Output state management
  |   +- overlay.rs    The user overlay tree: [`OverlayStore`] and the overlay types it holds
  |   +- split.rs      Split tree implementation using arena-based storage
  |   +- window.rs     `MappedWindow` - a toplevel window managed by the compositor
  |   +- workspace.rs  Workspace - a collection of tiled windows
  |
  +- wm/             `IonWM`'s operations, split by subject (keybinding actions, Python API
  |   +- compositor.rs  Compositor lifecycle: ending the session, directly or by closing every window
  |   +- desktop.rs     Desktop operations: create, remove, rename and reorder
  |   +- floating.rs    Floating-layer operations: z-order, rect, visibility, and moves across
  |   +- focus.rs       Focus operations: moving focus between windows, frames and outputs, and the
  |   +- frame.rs       Frame operations: the shape of the tiling tree, and the tabs within a frame
  |   +- keyboard.rs    Keyboard operations: runtime layout switching and the leader-key prompt
  |   +- output.rs      Output operations: the display-power and configuration changes the backend applies
  |   +- overlay.rs     Overlay operations: what an `OverlayAction` can ask for, applying one, and
  |   +- popup.rs       Compositor-drawn popup operations: the popup stack and its hit-testing,
  |   +- split.rs       Split-node operations: axis, children, ratio, divider and gap mutations
  |   +- window.rs      Window operations: where a window sits in the layout - tiled, floating or
  |   +- workspace.rs   Workspace operations: a workspace's lifetime, its floating form, and moving
  |
  +- handler/        Event handlers for the compositor
  |   +- input/         Input event handling for the compositor
  |   |   +- hit_test.rs          Result types for pointer z-order hit-test resolution
  |   |   +- keyboard.rs          Keyboard event handler
  |   |   +- pointer.rs           Pointer-over cache accessors, cursor-icon selection (resize-edge and
  |   |   +- pointer_button.rs    Pointer button event handling: press/release dispatch, popup
  |   |   +- pointer_hit_test.rs  Pointer z-order hit-test resolver: walks popup, fullscreen, floating,
  |   |   +- pointer_motion.rs    Pointer motion event handlers: relative/absolute motion, axis
  |   |   +- pointer_parity.rs    Debug-only parity assertions for the pointer-over cache
  |   |   +- tablet.rs            Tablet (graphics tablet / stylus) event handlers
  |   |   +- touch.rs             Touch event handlers
  |   |
  |   +- protocol/      Smithay protocol handler implementations for `IonMain`
  |   |   +- output_config/          Output configuration: `wlr-output-management`, gamma control, and output power
  |   |   +- decoration.rs           Decoration negotiation and shell extras: xdg/kde decoration, `xdg-foreign`, and `xdg-activation`
  |   |   +- foreign_toplevel.rs     `wlr-foreign-toplevel-management` handler
  |   |   +- icon.rs                 Toplevel icon protocol (`xdg_toplevel_icon_v1`)
  |   |   +- input_misc.rs           Assorted input handlers: idle-inhibit, keyboard-shortcuts-inhibit, tablet seat, and fractional scale
  |   |   +- lifecycle.rs            Core surface lifecycle: `wl_compositor`, `wl_buffer`, dmabuf, and shm handlers
  |   |   +- lock.rs                 Session lock (`ext-session-lock`) and the xwayland shell handler
  |   |   +- pointer_constraints.rs  Pointer constraints: pointer lock and confinement
  |   |   +- screencopy.rs           Screen capture (`wlr-screencopy`): screenshot and screen-share frame handling
  |   |   +- selection.rs            Seat, selection/clipboard, and drag-and-drop: seat, primary selection, data-device, and wlr/ext data-control
  |   |   +- shell.rs                Window shell protocols: `wl_output`, `wlr-layer-shell`, and `xdg-shell`
  |   |
  |   +- seat_focus.rs  Pointer and touch focus target type for smithay seat integration
  |   +- surface.rs     Surface lifecycle: mapping, unmapping, and destruction of toplevel and layer surfaces
  |
  +- input/          Input handling for keyboard and pointer events
  |   +- binding.rs     Binding, trigger, flag, and keymap matching logic
  |   +- event.rs       Input event types
  |   +- ids.rs         Identity types for registered keymaps and their bindings
  |   +- keysym.rs      XKB keysym name-to-code mapping
  |   +- menu.rs        Menu item definitions
  |   +- modifiers.rs   Which xkb real modifiers the binding modifier bits read, per keymap
  |   +- properties.rs  Operator property storage
  |   +- registry.rs    Keymap registry, cascade logic, and pointer hit-test context
  |
  +- render/         Render elements for `IonCore` compositor
  |   +- collection/     Backend render-element collection
  |   |   +- overlays/          User overlays: captured from the scene, then built into render elements
  |   |   |   +- desktop.rs  Desktop / desktop-item overlay captures and builds
  |   |   |   +- fbo.rs      The overlay FBO texture cache: composite an FBO overlay's elements
  |   |   |   +- reach.rs    Where the overlays show a window, for the main thread
  |   |   |   +- text.rs     Text overlay captures ([`OverlayKind::Text`], [`OverlayKind::TextDynamic`])
  |   |   |   +- window.rs   Window overlay captures ([`OverlayKind::Window`], [`OverlayKind::WindowIcon`])
  |   |   |
  |   |   +- frame_elements.rs  Top-level per-output element collection and frame callback dispatch
  |   |   +- workspace.rs       Workspace rendering: tiled windows, frame decorations, dividers, and
  |   |
  |   +- config.rs       The render config: the decoration look, fonts, backgrounds and scale
  |   +- coords.rs       Logical-to-physical coordinate conversion for rendering
  |   +- decorations.rs  Frame decoration geometry and rendering
  |   +- element.rs      Building render elements for a frame
  |   +- frame.rs        Assembling one output's frame
  |   +- icon.rs         Icon buffer for window tab icons
  |   +- icon_legacy.rs  Legacy icon loading from XDG desktop files and hicolor icon theme
  |   +- icon_worker.rs  Off-thread refinement of a window-icon overlay's image
  |   +- offscreen.rs    Rendering elements into an offscreen texture
  |   +- scene.rs        Scene composition helpers for rendering
  |   +- text.rs         Text rendering using swash and fontconfig
  |
  +- backend/        The display backends: winit, DRM and headless
  |   +- udev/          DRM backend for native hardware rendering
  |   |   +- device.rs          GPU device lifecycle: backend construction, udev add/change/remove, and
  |   |   +- outputs.rs         Connector hotplug and output geometry: bringing a connector up as a DRM
  |   |   +- render.rs          The render path: frame submission and pacing, vblank and its estimated
  |   |   +- render_thread.rs   Per-output render-thread primitives
  |   |   +- render_timings.rs  Render-time prediction for a per-output render thread
  |   |   +- screencopy.rs      Screencopy for the DRM backend: the per-node dmabuf probe and validation,
  |   |   +- session.rs         Session and per-output display controls: DPMS, VT switching, seat
  |   |
  |   +- headless.rs    Headless backend for running without a display
  |   +- helpers.rs     Cross-cutting backend utilities shared by every backend
  |   +- inline.rs      The one output the winit and headless backends draw inline
  |   +- screencopy.rs  Screencopy served from a frame's render elements, shared by every backend
  |   +- winit.rs       Winit backend for development and testing
  |
  +- protocols/      Wayland protocol implementations
  |   +- foreign_toplevel.rs   wlr-foreign-toplevel-management-unstable-v1 protocol implementation
  |   +- gamma_control.rs      wlr-gamma-control-unstable-v1 protocol implementation
  |   +- output_management.rs  wlr-output-management protocol implementation
  |   +- output_power.rs       wlr-output-power-management-unstable-v1 protocol implementation
  |   +- screencopy.rs         wlr-screencopy-unstable-v1 protocol implementation
  |   +- virtual_keyboard.rs   Virtual keyboard protocol support (`zwp_virtual_keyboard_v1`)
  |
  +- python/         Python embedding: hosts the `ion.*` module tree exposed to user configs and
  |   +- app.rs             `ion.app` Python module: application-level settings, lifecycle, and the
  |   +- config.rs          Config loading
  |   +- decor.rs           Decoration types: geometry, look, and active-decoration extraction
  |   +- desktop.rs         Desktop, floating entry, and tiling layer proxy types and collections
  |   +- events.rs          Event types and conversion helpers
  |   +- generator.rs       Python generator runtime
  |   +- geometry.rs        Geometry types: Point, Size, Rect, ColorRGBA, Direction
  |   +- helpers.rs         Shared helper traits, error constructors, and macros for Python proxy types
  |   +- hook_event.rs      Hook event and hook ID types for Python callback dispatch
  |   +- hooks.rs           Hook callback infrastructure for Python bindings
  |   +- init.rs            Python interpreter initialization and top-level `ion.*` module registration
  |   +- input_devices.rs   Input device proxies: `ion.app.input.keyboards` / `pointers` / `tablets`
  |   +- keymaps.rs         Keymap types: registry, matchers, handler, items collection
  |   +- operator.rs        Operator registration and execution via the Python `ion.ops` module
  |   +- overlays.rs        Overlay proxy types, subtypes, and overlay collection
  |   +- popups.rs          `ion.ui` Python module: popup menus, messages, and tooltips
  |   +- preferences.rs     Preference types accessed via `ion.app.preferences`
  |   +- run.rs             Python evaluation and execution helpers for IPC commands
  |   +- state_access.rs    Compositor state accessors for Python callbacks
  |   +- utils.rs           `ion.utils` Python module: logging, error reporting, shell / exec spawning,
  |   +- wm.rs              `ion.wm` Python module: top-level compositor-state accessors plus the
  |   +- wm_collections.rs  Collection accessors for window manager proxy types
  |   +- wm_types.rs        Window manager proxy types and split tree nodes
  |
  +- ipc/            IPC server for external command execution
  |   +- client.rs        The `ionwl-cmd` command line, and client-side encoders for the IPC wire
  |   +- socket_queue.rs  Writing to a client socket from the main loop, without waiting on the peer
  |
  +- cursor/         Cursor management for xcursor theme loading and rasterization
  +- constants/      Compositor-wide constants, grouped per subsystem: keymaps, input, layout,
  +- fixed/          Fixed-point arithmetic with 120 units per whole
  +- prefs/          Compositor preferences - plain Rust types populated from Python config
  +- xwayland/       XWayland support for running X11 applications
  +- bin/
      +- ionwl_cmd.rs  Command-line tool for sending commands to the IonWL compositor

  crates/
  +- argparse/     A small command-line argument parser, modeled on Python's `argparse`
  +- recycle_vec/  A `Vec` that gives back its allocation once a workload stops needing it

.. SOURCE_LAYOUT_END

``state/`` and ``wm/`` both hold ``impl IonWM`` blocks, so they are told apart
by who reaches the code rather than by type.
``state/`` is plumbing reached from an ``IonMain`` / ``IonCore`` entry point or
a Smithay handler, ``wm/`` is the operations the Python API and keymaps call,
and ``tiling/`` is the layout model those operations change.
The rule describes the tree rather than enforcing it: a file that stops
matching it is a candidate for moving, not a precedent.


Python API Documentation
========================

Requires ``sphinx`` and ``sphinx-rtd-theme``.
See ``make help`` for available documentation targets.


State Mutation
==============

``IonCore`` owns the Rust-side compositor state as three sibling fields,
``app``, ``registry`` and ``wm``, so callers can borrow them disjointly; its
doc says what separates them and where new state goes.
That split is what makes the ``wm/`` layer work, and it is also the source of
one recurring problem: code cannot always make the call it needs where it
stands.
Three mechanisms answer it - ``IonMain::wm_op``, ``DeferredPayload`` and
``IonWM::defer`` - and they are not interchangeable.
The ``src/state/deferred.rs`` module doc says which to pick, how Python
callbacks fit, and why there are three rather than one.

Dispatch schedule
-----------------

On top of calloop the compositor runs two fixed sequences of its own:
``IonMain::operator_post`` after every operator outcome and hook, and
``IonMain::main_loop_iteration`` once per pass of the loop.
Their docs give the order, and the comment beside each step justifies its
place.

A sync that runs at more than one point lists its call sites in its doc:
``render_inputs_sync``, ``overlay_resolve_sync``, ``windows_suspended_sync``
and ``foreign_toplevel_refresh``.

What a change owes
------------------

The post-step drains the follow-ups a dispatch asked for, but which to ask
for is the mutating site's to decide.
The ``src/wm/mod.rs`` module doc lists the follow-up channels and what each
kind of change owes.

Invariants
----------

Where the state keeps one fact in two places, one of four things holds it
together:

Type-enforced
   The compiler rejects the bad state, as with ``SceneReader`` and
   ``OutputModeInfo``.

Construction-enforced
   One function writes both sides, so no caller can update one alone.
   Its doc says so, as the one sanctioned way or the one owner of the pair
   (``fullscreen_window_enter``, ``window_frame_attach``).

Oracle-checked
   A debug-only check, placed by the failure it looks for: at the mutator for
   a write that corrupts, at ``operator_post`` for a missed call, at the
   main-loop tail for a missed sync, in ``render_inputs_sync`` for a mirror or
   an ordering, or on each read.
   Each is named ``*_parity_check``, ``*_check``, ``*_verify`` or
   ``*_parity_assert``, and its doc says where it runs and why.
   A *witnessed* check also has a ``#[should_panic]`` library test that stages
   the corruption, found by searching ``src/*/tests/`` for the check's name;
   the integration suite runs the rest, but nothing corrupts their state on
   purpose to show they can fire.

Unchecked
   Recorded beside the witnesses that cannot reach them, as
   ``window_parity_tests.rs`` does.

Every check is debug-only: in release a panic would end the session, so a
drift there goes unnoticed rather than fatal.

A new redundant store should derive one side from the other where it can.
One kept by hand owes a check placed by the rule above and a witness.

Python callback state
---------------------

The Python bindings meet the same borrow problem from the other side: a PyO3
object outlives any Rust borrow, so proxy types store a bare id and re-resolve
live state on every access through a thread-local accessor.
The ``src/python/state_access.rs`` module doc gives the rules, and
``StateAccessor`` which sites install each variant.

Interpreter-scoped state
------------------------

``IonCore`` is not the whole of the compositor's state: much of it, everything
the config declares included, lives with the interpreter.
``python::init`` lists it and how it is reset, and ``IonApp::preferences``
how the preferences mirror the Python objects.


Rendering
=========

Each output is drawn with smithay's ``GbmDrmCompositor`` (DRM backend) or a
damage tracker (winit and headless backends).
The DRM backend renders each output on its own thread by default; the winit and
headless backends always render inline.

Two render paths
----------------

On the DRM backend each output renders on its own thread by default, and
``IONWL_NO_RENDER_THREAD`` falls back to rendering every output on the main
loop.
The two write out their pacing separately, kept in step by a contract the
``src/backend/udev/mod.rs`` module doc states, along with where they differ.

What a backend owes
-------------------

Each backend implements ``Backend`` (``src/backend/mod.rs``), whose methods
have no defaults, so the compiler leads a new backend through every call.
The per-frame sequence it owes runs on each backend's own schedule, so it is
listed in that module's doc rather than on the trait.

The shared scene
----------------

Render-read state lives in ``IonScene`` (``layout``, ``render_config``,
``overlays``, ``outputs``, ``layer_shell``, ``session_lock``), held behind
``IonWM.scene`` as
``Arc<RwLock<IonScene>>`` (the ``SharedScene`` newtype).
``IonScene`` is asserted ``Send + Sync`` so the ``Arc`` can be cloned onto each
render thread.

The lock discipline is listed in the ``src/state/scene.rs`` module doc.

Mirroring main-loop state
-------------------------

A render thread reads the scene and nothing else, so main-loop state reaches
it resolved, before the thread is signaled:

``IonWM::render_inputs_sync``
   The compositor popup stack, the XWayland override-redirect windows, and
   each output's layer surfaces (``layer_bands_collect``).

``CursorRenderInputs``
   The pointer, drag icon and resolved cursor, carried by the signal itself.

``src/state/text_resolve.rs``
   Every text the next frame draws, rasterized.

``src/state/overlay_resolve.rs``
   The overlay tree, flattened into the order a frame draws it.

Each one's doc says what it mirrors and how its rebuild is gated.

Derived values in the scene
---------------------------

The layout, the overlay store and the render inputs hold values derived from
the scene's other state, each kept by one discipline, which the field's doc
names: who writes it, and the check holding it or that none does.
A new one copies the closest field, and a pass that gates on its inputs
follows the rule in ``src/state/revisioned.rs``.
A rebuilt value needs no check; a hand-kept one without a check says so.
``MappedWindow``'s own are listed on ``WindowPresentation`` and ``WindowSent``.

What a render keeps
-------------------

Each output's ``OutputRenderState`` keeps state across frames, so an
unchanged frame re-emits what it drew last time; its doc lists the caches, and
``Backend::caches_invalidate_all`` what must clear them.

Thread and main loop
--------------------

Each DRM output's render thread owns its compositor, GPU manager and caches,
and talks to the main loop over two channels, ``ThreadCommand`` and
``SurfaceCommand``.
The ``src/backend/udev/render_thread.rs`` module doc gives the division of
labour, the ordering the channels rely on, and the routes by which state
reaches a thread.

With the ``icon_legacy`` feature, a third thread searches XDG desktop files
for window icons (``src/render/icon_worker.rs``).


Input Dispatch
==============

Before the keymaps see an event, a series of latches may take it: the session
lock, input-consuming generators, compositor popups, leader keymaps and more.
Their order, and what reconciles them, is in the ``src/handler/input/mod.rs``
module doc, so a new interactive mode has a place to go; "Binding Resolution"
below takes over at the keymaps.


Binding Resolution
==================

Which keymaps an event consults, and the order of bindings within one, are
documented for users on ``ion.types.KeymapsRegistry``.
The ``src/input/registry.rs`` module doc names the code behind each rule, and
adds the rules the user documentation leaves out.


Python Error Reporting
======================

A Python exception that reaches the compositor is reported by
``python_error_report``: the traceback is logged at ``warn``, and shown in a
popup when ``notify_on_error`` is set, which it is by default.
Its doc gives what happens next at each entry point, and ``popup_error_show``
how a repeated error is held back.


The Rust-to-Python Boundary
===========================

The compositor imports some ``ion_utils._internal`` modules by name, so
renaming one is a Python rename and a Rust string literal.
The package's header comment (``share/ionwl/python/ion_utils/_internal/__init__.py``)
lists them and where each is reached.


Name Constraints
================

Desktop and workspace names share common constraints:

- Names are always globally unique within their type.
  Duplicates are resolved by appending a numeric suffix (e.g. ``work.1``, ``work.2``).
- Names are always valid UTF-8.
- Names cannot contain control sequences, nil bytes, tabs or line breaks.
- Names cannot exceed 256 bytes (will be truncated).
- Names cannot be empty. One created without a name is numbered (``1``, ``2``, ...);
  any other name left empty, by a rename or by removing control characters,
  becomes ``Untitled``.

Input device names come from the device, so only the first rule applies to
them, within each kind (keyboards, pointers, tablets): a second device
reporting a taken name gets the same numeric suffix.


Testing
=======

``make test`` runs five harnesses. Each reaches something the others cannot.

Library tests (``cargo test --workspace --lib``)
   ``src/<subsystem>/tests/<name>_tests.rs``, each mounted from the module it
   covers, plus the tests of the ``crates/`` packages. They call crate-private code directly: the layout, state and
   render logic, without a Wayland display. Tests that touch the process-wide
   Python interpreter hold ``ensure_python_init``'s lock.

Integration tests (``cargo test --test integration --features test_support``)
   ``tests/integration/``. ``Fixture`` runs the compositor with no backend
   (``ActiveBackend::Unset``), virtual outputs, and real Wayland clients
   connected over a socket. It can drive input, step Python generators and
   evaluate Python in the running compositor. ``frame_collect_test`` collects a
   frame's elements on a surfaceless EGL renderer, which needs Mesa. Within a
   process fixtures run one at a time, under ``TEST_MUTEX``. ``make test``
   shards the suite across processes instead.

Python API tests (``make test_pyapi``)
   ``tests/python/test_*.py``, run by ``tests/python/run.py`` inside the real
   binary at config load, then exiting. No backend, output or window exists
   yet, so these test the ``ion`` API's surface, not window management.

Render test (``make test_render``)
   ``tests/python/run_render.py`` runs the real binary on the headless backend
   (llvmpipe), drives it over IPC with ``ionwl-cmd``, and asserts on the
   ``[timing]`` frame probe it prints. The only harness that composites frames,
   though with no Wayland client, so no window content.

Shutdown test (``make test_shutdown``)
   ``tests/python/run_shutdown.py`` runs the real binary on the headless
   backend and signals it from ``compositor_startup_post``, asserting a clean
   exit, the shutdown hook, and a spawned child's signal mask.

The ``test_support`` feature only exposes. It makes ``system`` public and adds
the ``*_test`` accessors and the few simulations a test needs (such as
``pending_toplevels_send_configure``). It must not change behaviour, since
the integration tests would then test a different compositor from the one
that ships. The one exception is ``ion.utils.notify``, which records the
notification instead of sending it, so a test run never reaches the desktop's
notification daemon.

A ``*_test`` accessor is warranted when an integration test must observe
crate-private state, or run a step the main loop would.

The fixture's dispatch runs ``main_loop_iteration``, and ``wm_op`` and the
Python calls end in ``operator_post``, so every integration test runs the
chokepoint checks and the verifiers whether or not it asserts on them.
That holds only while a test reaches its state the way production does: a
test that writes the scene or layout directly must make the follow-up call
production would, such as a keyboard sync after a focus write, or a verifier
reports drift the compositor cannot reach.
"Invariants" above says how to find which checks also have a witness.

What no harness reaches:

- The DRM backend: its render threads and inline path, vblank pacing, VT
  switching and hotplug of real connectors.
- Pixels: frames are checked as element lists or by the frame probe.
- XWayland: it cannot be started, so ``xwayland.rs`` tests the
  compositor-side teardown only.
- Touchpad gestures (swipe, pinch, hold).
- Most of the interactive Python operators (the overviews, the carousels,
  interactive resize). ``generators_step_until`` sleeps in real time to each
  generator wake, so an animation costs its full duration per test.


Limitations
===========

- No mixed DPI support.

  Given the nature of this window manager tiling across multiple outputs
  (with "unified" workspaces enabled), mixed monitor DPIs are not supported.
  The highest scaling across all outputs is used.

  Although supporting per-workspace scale would be possible with "unified" disabled,
  this is an acceptable limitation for now.

- A single seat.

  One ``wl_seat`` is created at start-up and never joined by another, so there
  is one keyboard focus, one pointer and one clipboard for the session.
  Several physical keyboards and pointers are supported and all drive that
  seat; the keyboard layout follows whichever device was last used
  (``keyboard_active_device_sync``).

  Nothing in the input model is written to be per-seat, so this is a design
  assumption rather than a configuration: ``ion.app.input`` enumerates devices,
  not seats, and an event carries no seat of its own.

- Touch is forwarded only.

  Taps reach clients, but they don't move focus, activate tabs, reach the
  spatial regions or trigger bindings. A touch can drive an interactive
  operation a pointer started, but cannot start one.

- Scroll cannot be bound.

  Keymaps match keys and pointer buttons only (``InputTrigger``). Scroll
  reaches clients, and reaches generators as ``Scroll`` events.


Supported Protocols
===================

Listed in the user guide, ``doc/python_api/rst/guide/features.rst``
("Wayland Protocols"), the only list maintained.


Expected Behavior
=================


Workspace States
----------------

A workspace is in one of three states:

- **Tiled**: assigned to an output via ``output.workspaces.add(ws)``.
- **Floating**: in a desktop's floating layer, via ``desktop.items_floating.add(ws)``.
- **Detached**: not assigned to any output and not floating (e.g. freshly created).

Tiled and floating are mutually exclusive.
A tiled workspace must be removed from its output before it can be floated,
and a floating workspace must be hidden before it can be assigned to an output.

Floating Workspaces
-------------------

- When toggled on, they will show on top of everything else.
  Except windows flagged with "always-on-top".

Fullscreen
----------

Each output has at most one fullscreen window.
The fullscreen window is rendered above all other content on that output.

Entering and Exiting
^^^^^^^^^^^^^^^^^^^^

- A window enters fullscreen on its own output.
  The active output is not used - this avoids surprises when the
  pointer is on a different monitor than the focused window.
- Standalone floating frames are hidden while their window is
  fullscreen, preventing them from rendering behind the fullscreen
  surface. They are restored when fullscreen exits.

Fullscreen Sync
^^^^^^^^^^^^^^^

When multiple windows are fullscreen on the same output, only one is
shown. The winner is the window whose container was focused most
recently (using the container's focus time), and within one container
the window that last took the output or was focused while fullscreen.
Each output holds its
winner until an event such as a desktop switch, a fullscreen exit or
a container shown or hidden re-derives it, even when a rival's
container is focused more recently in between. The events, and why
the winner holds, are in the ``src/tiling/layout/fullscreen.rs``
module doc.

Container Hide/Show
^^^^^^^^^^^^^^^^^^^

Hiding a container (e.g. toggling a floating workspace off) does not
exit fullscreen for its windows. Their fullscreen state is preserved
so they re-enter fullscreen when the container is shown again.

While hidden, the output no longer shows a fullscreen window and
another fullscreen candidate on the same output (if any) is promoted.

New Window Focus Protection
^^^^^^^^^^^^^^^^^^^^^^^^^^^

When a fullscreen window is active on an output, new windows opening
on that output do not steal focus or displace the fullscreen window.
The fullscreen window remains visible and focused.

If the new window itself requests fullscreen, it is marked as
fullscreen but does not replace the current fullscreen window.
The existing fullscreen window's container keeps a more recent
focus time so it stays ahead in ordering. When the current
fullscreen window later exits, the new window is promoted.