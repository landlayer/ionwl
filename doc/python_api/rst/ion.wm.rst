This module exposes live compositor state through five
collections: :data:`desktops`, :data:`outputs`, :data:`workspaces`,
:data:`frames`, and :data:`windows`. It is only accessible inside
callbacks (keybinding handlers, hook callbacks, operator ``exec``
functions).

Entity hierarchy
   As a simplified mental model: Desktop -> Workspace -> Frame ->
   Window. The fuller picture is two layers per desktop. The tiling
   layer (``desktop.items_tiling``) holds workspaces, each assigned to
   all outputs or to a single output; a workspace owns a split tree of
   frames and a frame holds one or more tabbed windows. The floating
   layer (``desktop.items_floating``) holds free-positioned frames and
   floating workspaces, interleaved in one z-order.

   Entities link both ways: ``workspace.frames`` lists the frames in a
   workspace, while ``window.workspace`` returns the workspace a window
   belongs to. Scoped sub-collections (``frame.windows``,
   ``workspace.frames``, ``desktop.items_tiling``) filter to one parent;
   top-level collections (``ion.wm.windows``) span all parents.

Tiled vs floating
   Tiled windows live inside the split tree. Floating windows live in the
   desktop's floating layer and have no workspace - ``window.workspace``
   returns ``None``. Whole workspaces can also float.

Focus chain
   Each collection has an ``active`` property. Walking from the active
   desktop down to the active window passes through entry wrappers, not
   directly through the entities: ``desktops.active`` ->
   ``desktop.items_tiling.active`` (a
   :class:`~ion.types.DesktopItemTilingWorkspace`, so take its
   ``.workspace``) -> ``workspace.frames.active`` ->
   ``frame.windows.active``. When focus is on the floating layer,
   ``desktop.items_floating.active`` is the mutually exclusive
   alternative; it returns a
   :class:`~ion.types.DesktopItemFloatingFrame` or
   :class:`~ion.types.DesktopItemFloatingWorkspace` entry.

Split tree
   The tiling structure is a binary tree accessible from
   ``workspace.split_root``. Each node is either a container (with children
   and a split axis) or a leaf holding a single frame.

Context
   ``ion.wm.context`` is the action context accessor - for example, which
   tab is under the pointer when a tab-bar binding fires. Use this when
   the target differs from the focused item.

Cursor stack
   The compositor maintains a stack of CSS cursor icons; the top of
   the stack is what the user sees. Push and pop entries via the
   cursor functions in this module. The stack clears when all
   generators exit.

Overlays
   ``ion.wm.overlay_root`` is the root of the overlay tree. Append
   :class:`~ion.types.Overlay` children to draw custom geometry on
   the compositor surface. The root places and scales what it holds
   like any other group, but nothing is drawn above it for a composite
   to be drawn into, so :attr:`~ion.types.OverlayGroup.alpha` fades
   nothing there until ``use_alpha_merged`` is cleared.

Coordinates
   Positions and rectangles are in global logical pixels: one space
   shared by every output, in which an output's ``rect`` places it.
   Overlays are the exception: an overlay is placed in its parent
   group's space, which is global only while every enclosing group,
   :data:`overlay_root` included, keeps the default position and scale.

Output and workspaces
   Outputs do not directly reference their workspace. Workspace-to-output
   assignments are managed through the desktop.

Collections
   Collections generally provide sequence-style access - ``len()``,
   iteration, and indexing - and most expose an ``active`` property for
   the currently focused item plus ``find_by_*`` methods for reverse
   lookups. Every collection supports membership testing with ``in``,
   and one that accepts a name in ``[]`` also accepts the name in
   ``in``. Positions in ``windows``, ``frames``, ``workspaces`` and
   ``outputs`` are not stable; hold the proxy or its ``id`` instead.
   Check the generated class for each collection for its exact protocol
   support.

.. _proxy-objects:

Proxy objects
   Values returned by collections are lightweight proxies identified by
   a unique ``id``. The input devices expose none - look one up by name
   or position - though two handles to one device still compare equal.
   A proxy goes stale once what it refers to is gone. This most often
   bites when a proxy is held across callbacks or yields, since the
   underlying window, frame, or workspace may be removed - or a device
   unplugged - before it is reused.

   ``ReferenceError``
      Raised by reading or writing a stale proxy, naming its type and id.
   ``id`` and ``repr()``
      Always answer, so a stale proxy can still be logged and compared.
   ``ValueError``
      Raised for a live object passed to a collection it is not a member
      of, such as ``items_tiling.remove`` given another desktop's entry.
   ``is_valid``
      Whether the proxy can still be used. For most proxies this is
      whether the object exists. A desktop entry, a split node and a
      keymap binding refer to an object's place, so theirs is whether it
      is still there: ``desktop.items_tiling.find_by_workspace(ws).is_valid``
      turns ``False`` once ``ws`` is floated, while ``ws.is_valid`` stays
      ``True``.
   ``is_live``
      Overlays have this instead of ``is_valid``: one removed with
      ``remove`` or ``pop`` is detached rather than stale and can be added
      again, so it says whether the overlay is in the compositor now.
