# SPDX-License-Identifier: GPL-3.0-or-later

# Built-in operators implemented in Python.

# Only needed for Python < 3.14.
from __future__ import annotations

__all__ = (
    "keymap_names",
    "register",
)

from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING, Annotated, Any, Literal, NamedTuple

import ion

from ion_utils._internal.desktop_layout import EdgeDirection, desktop_adjacent, desktop_focus
from ion_utils._internal.operators import modal_keymap_get

if TYPE_CHECKING:
    from ion.types import DesktopItemFloating, Output, Rect, SplitNode

from ion.types import (
    Desktop,
    DesktopItemFloatingWorkspace,
    DesktopItemTilingWorkspace,
    Frame,
    SplitNodeContainer,
    SplitNodeLeaf,
    Window,
    Workspace,
)

_LiteralDirection = Literal['LEFT', 'RIGHT', 'UP', 'DOWN']

# Use -1 toggles, 0/1 to disable/enable.
_LiteralToggleOrSet = Literal[-1, 0, 1]


# Private on purpose, don't export: it only gathers each built-in operator's
# values for `ion.ops.register`, which is the public way to define an operator.
class _Operator:
    """Base class for operator definitions."""

    __slots__ = ()

    # Required - subclasses must define these.
    idname: str
    description: str
    Properties: type[NamedTuple]
    name: Callable[[Any], str]
    exec: Callable[[Any, Any], bool | None]

    # Optional - subclasses may override these.
    poll: Callable[[Any], str | None] | None = None
    pointer_only: bool = False
    lifetime: Callable[[], AbstractContextManager[Any]] | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Enforce that subclasses define all required attributes.
        # Required attributes are those declared in annotations without a
        # default value on the base class (annotations that have no
        # corresponding class attribute).
        for attr in _Operator.__annotations__:
            if not hasattr(_Operator, attr) and not hasattr(cls, attr):
                raise TypeError(
                    "{!s} missing required attribute {!r}".format(cls.__name__, attr)
                )


def _class_register(cls: type[_Operator]) -> None:
    """Register an operator class with `ion.ops`."""
    kwargs: dict[str, Any] = {}
    if (poll := getattr(cls, 'poll', None)) is not None:
        kwargs['poll'] = poll
    if getattr(cls, 'pointer_only', False):
        kwargs['pointer_only'] = True
    if (lifetime := getattr(cls, 'lifetime', None)) is not None:
        kwargs['lifetime'] = lifetime
    ion.ops.register(
        cls.idname,
        name=cls.name,
        exec=cls.exec,
        description=cls.description,
        properties_type=cls.Properties,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Compositor operators
# ---------------------------------------------------------------------------


class _CompositorQuit(_Operator):
    __slots__ = ()

    idname = 'compositor_quit'
    description = 'Exit the compositor.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _CompositorQuit.Properties) -> str:
        return 'Quit'

    @staticmethod
    def exec(properties: _CompositorQuit.Properties, event: ion.types.Event) -> bool:
        ion.app.quit()
        return True


class _CompositorLogout(_Operator):
    __slots__ = ()

    idname = 'compositor_logout'
    description = 'Graceful logout: close all windows, exit when none remain.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _CompositorLogout.Properties) -> str:
        return 'Logout'

    @staticmethod
    def exec(properties: _CompositorLogout.Properties, event: ion.types.Event) -> bool:
        ion.app.logout()
        return True


class _CompositorReload(_Operator):
    __slots__ = ()

    idname = 'compositor_reload'
    description = 'Re-run the configuration by reloading the ``ion_init`` module.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _CompositorReload.Properties) -> str:
        return 'Reload'

    @staticmethod
    def poll(properties: _CompositorReload.Properties) -> str | None:
        # `reload` refuses too; checked here so the refusal comes before the notification.
        if ion._internal.hook_running():
            return 'Not available from a hook callback'
        return None

    @staticmethod
    def exec(properties: _CompositorReload.Properties, event: ion.types.Event) -> bool:
        import ion_utils.config

        ion.utils.notify("Reload")
        # Key, pointer & menu dispatch all run the builtin with full state
        # access, so the reload runs in place; a raising config propagates,
        # reported as this operator's failure.
        ion_utils.config.reload()
        return True


class _TagSet(_Operator):
    __slots__ = ()

    idname = 'tag_set'
    description = 'Set the tagged state of the focused window.'

    class Properties(NamedTuple):
        mode: Annotated[_LiteralToggleOrSet, '-1 to toggle, 0 to untag, 1 to tag.'] = -1

    @staticmethod
    def name(properties: _TagSet.Properties) -> str:
        if properties.mode > 0:
            return 'Tag'
        if properties.mode == 0:
            return 'Untag'
        return 'Tag Toggle'

    @staticmethod
    def poll(properties: _TagSet.Properties) -> str | None:
        from ion.wm import context
        if context.window is None:
            return 'No focused window'
        return None

    @staticmethod
    def exec(properties: _TagSet.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (window := context.window) is None:
            return False
        mode = properties.mode
        if mode < 0:
            window.tag ^= True
        else:
            window.tag = mode > 0
        return True


class _TagClear(_Operator):
    __slots__ = ()

    idname = 'tag_clear'
    description = 'Untag all tagged windows.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _TagClear.Properties) -> str:
        return 'Tag Clear'

    @staticmethod
    def exec(properties: _TagClear.Properties, event: ion.types.Event) -> bool:
        for window in ion.wm.windows:
            if window.tag:
                window.tag = False
        return True


class _TagAttach(_Operator):
    __slots__ = ()

    idname = 'tag_attach'
    description = 'Attach all tagged windows to the current frame as tabs.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _TagAttach.Properties) -> str:
        return 'Tag Attach'

    @staticmethod
    def poll(properties: _TagAttach.Properties) -> str | None:
        from ion.wm import context
        if context.frame is None:
            return 'No focused frame'
        return None

    @staticmethod
    def exec(properties: _TagAttach.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (frame := context.frame) is not None:
            frame.attach_tagged()
        return True


# ---------------------------------------------------------------------------
# Window operators
# ---------------------------------------------------------------------------


class _WindowKill(_Operator):
    __slots__ = ()

    idname = 'window_kill'
    description = 'Force-kill an unresponsive window.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WindowKill.Properties) -> str:
        return 'Kill'

    @staticmethod
    def poll(properties: _WindowKill.Properties) -> str | None:
        from ion.wm import context
        if context.window is None:
            return 'No focused window'
        return None

    @staticmethod
    def exec(properties: _WindowKill.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (window := context.window) is not None:
            window.kill()
        return True


class _FloatingDepthToFront(_Operator):
    __slots__ = ()

    idname = 'floating_depth_to_front'
    description = 'Raise a floating item to the front.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _FloatingDepthToFront.Properties) -> str:
        return 'To Front'

    @staticmethod
    def poll(properties: _FloatingDepthToFront.Properties) -> str | None:
        if ion.wm.desktops.active.items_floating.active is None:
            return 'No focused floating item'
        return None

    @staticmethod
    def exec(properties: _FloatingDepthToFront.Properties, event: ion.types.Event) -> bool:
        if (floating_active := ion.wm.desktops.active.items_floating.active) is not None:
            floating_active.depth_to_front()
        return True


class _FloatingDepthToBack(_Operator):
    __slots__ = ()

    idname = 'floating_depth_to_back'
    description = 'Lower a floating item to the back.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _FloatingDepthToBack.Properties) -> str:
        return 'To Back'

    @staticmethod
    def poll(properties: _FloatingDepthToBack.Properties) -> str | None:
        if ion.wm.desktops.active.items_floating.active is None:
            return 'No focused floating item'
        return None

    @staticmethod
    def exec(properties: _FloatingDepthToBack.Properties, event: ion.types.Event) -> bool:
        if (floating_active := ion.wm.desktops.active.items_floating.active) is not None:
            floating_active.depth_to_back()
        return True


class _FloatingRaise(_Operator):
    __slots__ = ()

    idname = 'floating_raise'
    description = 'Raise the floating item under the pointer (pointer binding only).'
    pointer_only = True

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _FloatingRaise.Properties) -> str:
        return 'Float Raise'

    @staticmethod
    def exec(properties: _FloatingRaise.Properties, event: ion.types.Event) -> bool:
        ion._internal.floating_raise_at_pointer()
        return True


class _FloatingLower(_Operator):
    __slots__ = ()

    idname = 'floating_lower'
    description = 'Lower the floating item under the pointer (pointer binding only).'
    pointer_only = True

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _FloatingLower.Properties) -> str:
        return 'Float Lower'

    @staticmethod
    def exec(properties: _FloatingLower.Properties, event: ion.types.Event) -> bool:
        ion._internal.floating_lower_at_pointer()
        return True


class _WindowFloatingSet(_Operator):
    __slots__ = ()

    idname = 'window_floating_set'
    description = 'Set the floating state of the focused window.'

    class Properties(NamedTuple):
        mode: Annotated[_LiteralToggleOrSet, '-1 to toggle, 0 to tile, 1 to float.'] = -1

    @staticmethod
    def name(properties: _WindowFloatingSet.Properties) -> str:
        if properties.mode > 0:
            return 'Float'
        if properties.mode == 0:
            return 'Tile'
        return 'Float Toggle'

    @staticmethod
    def poll(properties: _WindowFloatingSet.Properties) -> str | None:
        from ion.wm import context
        if context.window is None:
            return 'No focused window'
        return None

    @staticmethod
    def _tile_target(window: Window, desktop: Desktop) -> Frame | None:
        """Find the tiled frame to tile a floating window into.

        The frame the window's rect best overlaps, else the nearest frame by
        union area. Geometry alone decides it, whatever the focus preferences
        say - where the pointer ends up is settled after the move, as the
        fullscreen enter settles it in ``window_fullscreen_apply``.

        Returns None when the desktop holds no frame to tile into.
        """
        if (win_rect := window.frame_rect) is None:
            return None
        # Collect all tiling frame/rect pairs on this desktop.
        frame_rects = [
            (f, n.rect)
            for entry in desktop.items_tiling
            if isinstance(entry, DesktopItemTilingWorkspace)
            for f in entry.workspace.frames
            if (n := f.split_node) is not None
        ]
        if not frame_rects:
            return None
        # Find the tiled frame whose rectangle best overlaps the floating window.
        if (frame := _best_by_rect_overlap(win_rect, frame_rects)) is not None:
            return frame
        # No intersection: fall back to the nearest frame by union area.
        return min(frame_rects, key=lambda entry: win_rect.union(entry[1]).area())[0]

    @staticmethod
    def exec(properties: _WindowFloatingSet.Properties, event: ion.types.Event) -> bool:
        from ion.app import preferences
        from ion.wm import context
        if (window := context.window) is None:
            return False
        mode = properties.mode
        if mode < 0:
            mode = 0 if window.is_floating else 1
        if mode == 0 and window.is_floating:
            if (frame_best := _WindowFloatingSet._tile_target(window, ion.wm.desktops.active)) is None:
                return False
            # One decision, split by the move: either the pointer follows the
            # window into its frame, or it stays and focus comes back to it.
            #
            # Warp first: the move empties the floating frame and the layout
            # drops it, leaving the warp to read the tiled frame underneath
            # and land the cursor off the window it followed.
            pointer_warp = preferences.focus.pointer_warp
            if pointer_warp:
                frame_best.pointer_warp_if_needed()
            window.move_to_frame(frame_best)
            if not pointer_warp:
                # The tile may be nowhere near the pointer, and `move_to_frame`
                # focused it.
                ion._internal.sloppy_focus_update()
        elif mode > 0 and not window.is_floating:
            window.move_to_floating(ion.wm.desktops.active)
        return True


class _WindowFullscreenSet(_Operator):
    __slots__ = ()

    idname = 'window_fullscreen_set'
    description = 'Set the fullscreen state of the focused window.'

    class Properties(NamedTuple):
        mode: Annotated[_LiteralToggleOrSet, '-1 to toggle, 0 to disable, 1 to enable.'] = -1

    @staticmethod
    def name(properties: _WindowFullscreenSet.Properties) -> str:
        if properties.mode > 0:
            return 'Fullscreen'
        if properties.mode == 0:
            return 'Unfullscreen'
        return 'Fullscreen Toggle'

    @staticmethod
    def poll(properties: _WindowFullscreenSet.Properties) -> str | None:
        from ion.wm import context
        if context.window is None:
            return 'No focused window'
        return None

    @staticmethod
    def exec(properties: _WindowFullscreenSet.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (window := context.window) is None:
            return False
        mode = properties.mode
        if mode < 0:
            window.fullscreen ^= True
        else:
            window.fullscreen = mode > 0
        return True


class _WindowFullscreenAllSet(_Operator):
    __slots__ = ()

    idname = 'window_fullscreen_all_set'
    description = 'Set the fullscreen state of the focused window over all outputs.'

    # The `data` key marking a desktop's spanning workspace, so the cleanup
    # hook finds them without knowing the caller's chosen name. The mark moves
    # with the workspace, so a reload that merges the desktops keeps it.
    _MARK = '{:s}.spanning'.format(idname)
    # The window `data` key recording where to restore the window to.
    _RETURN = '{:s}.return'.format(idname)

    class _ReturnRecord(NamedTuple):
        """Where `_restore` puts a window back; the default record restores to any frame."""
        is_floating: bool = False
        # The floating rect, None while the window was hidden.
        rect: ion.types.Rect | None = None
        # The origin tiling frame, restored to while it is still valid.
        frame: ion.types.Frame | None = None
        fullscreen: bool = False

    class Properties(NamedTuple):
        name: Annotated[
            str,
            'Name of the shared workspace spanning every output; '
            'pick one unlikely to collide with your own workspaces.',
        ]
        mode: Annotated[_LiteralToggleOrSet, '-1 to toggle, 0 to disable, 1 to enable.'] = -1

    @staticmethod
    def name(properties: _WindowFullscreenAllSet.Properties) -> str:
        if properties.mode > 0:
            return 'Fullscreen All Outputs'
        if properties.mode == 0:
            return 'Unfullscreen All Outputs'
        return 'Fullscreen All Outputs Toggle'

    @staticmethod
    def poll(properties: _WindowFullscreenAllSet.Properties) -> str | None:
        from ion.wm import context
        if context.window is None:
            return 'No focused window'
        return None

    @staticmethod
    def exec(properties: _WindowFullscreenAllSet.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        cls = _WindowFullscreenAllSet
        if (window := context.window) is None:
            return False
        # Already fullscreen across all outputs if the window sits in a
        # spanning workspace.
        on = window.workspace in cls._spanning_all()
        mode = properties.mode
        if mode < 0:
            mode = 0 if on else 1
        if mode > 0 and not on:
            cls._enter(window, context.frame, properties.name)
        elif mode == 0 and on:
            # Move the window out; the cleanup hook disposes the now-empty
            # spanning workspace.
            cls._restore(window, ion.wm.desktops.active)
        return True

    @staticmethod
    @contextmanager
    def lifetime() -> Iterator[None]:
        cls = _WindowFullscreenAllSet

        def watch_restore() -> None:
            # The reload cleared the cleanup hooks, while the spanning
            # workspaces outlive it.
            cls._watch_set(bool(cls._spanning_all()))

        hook = ion.app.hooks.compositor_reload_post
        hook.append(watch_restore)
        try:
            yield
        finally:
            # Already gone when a reset cleared hooks before unregistering.
            if watch_restore in hook:
                hook.remove(watch_restore)

    @staticmethod
    def _spanning(desktop: ion.types.Desktop) -> Iterator[ion.types.Workspace]:
        """Yield the desktop's spanning workspaces.

        Usually one, but a reload that merges desktops can bring several.
        Only a floating workspace counts, so one the user tiled is left alone.
        """
        mark = _WindowFullscreenAllSet._MARK
        for item in desktop.items_floating:
            if isinstance(item, DesktopItemFloatingWorkspace) and (ws := item.workspace).data.get(mark):
                yield ws

    @staticmethod
    def _spanning_all() -> list[ion.types.Workspace]:
        """Return every desktop's spanning workspaces."""
        return [ws for desktop in ion.wm.desktops for ws in _WindowFullscreenAllSet._spanning(desktop)]

    @staticmethod
    def _fallback_frame(desktop: ion.types.Desktop) -> ion.types.Frame | None:
        """Return any tiling frame on the desktop, or None when it has none.

        Used to restore a window whose original frame no longer exists.
        """
        for entry in desktop.items_tiling:
            if (
                isinstance(entry, DesktopItemTilingWorkspace)
                and (frame := next(iter(entry.workspace.frames), None)) is not None
            ):
                return frame
        return None

    @staticmethod
    def _floating_rect_from_content_rect(content: ion.types.Rect) -> ion.types.Rect:
        """Grow a target content rect to the workspace floating rect presenting it.

        A lone frame insets its content below the tab bar only: with no
        divider-adjacent edges it draws no side or bottom border, so only the top
        is grown by the tab bar height and pad.
        """
        geom = ion.app.decor.geom
        top = geom.titlebar_height + max(geom.window_pad, geom.tab_pad)
        return ion.types.Rect(
            (content.min.x, content.min.y - top),
            (content.max.x, content.max.y),
        )

    @staticmethod
    def _enter(window: ion.types.Window, origin_frame: ion.types.Frame | None, name: str) -> None:
        """Move a window into its desktop's spanning workspace, creating it if needed."""
        cls = _WindowFullscreenAllSet
        if (bounds := ion.wm.outputs.bounds_calc()) is None:
            return
        desktop = ion.wm.desktops.find_by_window(window) or ion.wm.desktops.active
        if (ws := next(cls._spanning(desktop), None)) is None:
            ws = ion.wm.workspaces.new(bounds, name)
            if desktop.items_floating.add(ws) is None:
                return
            ws.data[cls._MARK] = True
        # Size the workspace so the window contents -- not the decorations -- fill
        # every output.
        ws.floating_rect = cls._floating_rect_from_content_rect(bounds)
        if (target := next(iter(ws.frames), None)) is None:
            return
        # Replace occupancy: any window already fullscreen here is restored, but
        # only after the new window is in so the workspace never empties mid-swap
        # (which would trip the cleanup hook).
        previous = [other for other in ws.windows if other != window]
        # A move keeps fullscreen, and the surface would go on covering the
        # output. Exit before the rect is read: the exit restores that rect.
        fullscreen = window.fullscreen
        if fullscreen:
            window.fullscreen = False
        # Remember where the window came from so it can be restored on toggle-off.
        if window.is_floating:
            window.data[cls._RETURN] = cls._ReturnRecord(
                is_floating=True,
                rect=window.frame_rect,
                fullscreen=fullscreen,
            )
            window.move_to_tiling(workspace=ws, frame=target)
        else:
            window.data[cls._RETURN] = cls._ReturnRecord(frame=origin_frame, fullscreen=fullscreen)
            window.move_to_frame(target)
        for other in previous:
            cls._restore(other, desktop)
        # Watch for windows leaving so workspaces are disposed even when a window
        # is closed rather than toggled off.
        cls._watch_set(True)

    @staticmethod
    def _restore(window: ion.types.Window, desktop: ion.types.Desktop) -> None:
        """Move a window back to where it was before it went fullscreen across all outputs."""
        cls = _WindowFullscreenAllSet
        record: _WindowFullscreenAllSet._ReturnRecord = window.data.pop(cls._RETURN, cls._ReturnRecord())
        if record.is_floating:
            window.move_to_floating(desktop, record.rect)
        else:
            # Restore to the origin frame while it is still valid, else any frame.
            frame = record.frame
            if frame is None or not frame.is_valid:
                frame = cls._fallback_frame(desktop)
            if frame is not None:
                window.move_to_frame(frame)
        # After the move, so the fullscreen lands on the output the window is
        # back on rather than the one the spanning workspace put it on.
        if record.fullscreen:
            window.fullscreen = True

    @staticmethod
    def _watch_set(enable: bool) -> None:
        """Register or unregister the spanning-workspace cleanup hooks.

        The watch exists only while a window is fullscreen across all outputs:
        it is enabled on enter and again after a reload, which clears hooks,
        and removed once every spanning workspace empties.
        """
        hooks = ion.app.hooks
        cls = _WindowFullscreenAllSet
        watched = (
            (hooks.window_close_post, cls._cleanup_after_close),
            (hooks.window_move_post, cls._cleanup_after_relocate),
            (hooks.window_floating_post, cls._cleanup_after_relocate),
        )
        # The hooks are always registered together, so membership of any one
        # reflects them all. Skip when already in the requested state.
        if enable == (cls._cleanup_after_close in hooks.window_close_post):
            return
        for hook, callback in watched:
            if enable:
                hook.append(callback)
            else:
                hook.remove(callback)

    @staticmethod
    def _cleanup_after_close(window: ion.types.Window) -> None:
        """Run the spanning-workspace cleanup for a window that has been closed."""
        _WindowFullscreenAllSet._cleanup_if_empty(window, is_window_valid=False)

    @staticmethod
    def _cleanup_after_relocate(window: ion.types.Window) -> None:
        """Run the spanning-workspace cleanup for a window that moved or floated."""
        _WindowFullscreenAllSet._cleanup_if_empty(window, is_window_valid=True)

    @staticmethod
    def _cleanup_if_empty(window: ion.types.Window, *, is_window_valid: bool) -> None:
        """Dispose any desktop's spanning workspace once its last window leaves.

        Reached from the window close, move and float hooks while a window is
        fullscreen across all outputs. Any of those events can empty a spanning
        workspace, so every one is re-checked and empty ones are disposed. Once
        none remain the hooks remove themselves.

        `is_window_valid` says whether `window` still exists, which is why each
        hook has its own entry point: the close hook fires after removal, so
        its proxy is stale and must not be touched.
        """
        cls = _WindowFullscreenAllSet
        spanning = cls._spanning_all()
        empty = [ws for ws in spanning if ws.is_empty]
        # The window that emptied a workspace has a spent return record --
        # only toggle-off runs `_restore` to pop it, leaving every other route
        # naming a frame the user has moved on from. It is the hook's window,
        # unless that one is still sitting in a spanning workspace: then the
        # workspace emptied on its own (an `_enter` that found no frame, say)
        # and the record is live. A closed window took its data with it
        # either way.
        if empty and is_window_valid and window.workspace not in spanning:
            window.data.pop(cls._RETURN, None)
        for ws in empty:
            # Removing the workspace also removes it from the desktop's
            # floating layer (`layout.workspace_remove`).
            ion.wm.workspaces.remove(ws)
        if len(empty) == len(spanning):
            cls._watch_set(False)


class _FloatingMove(_Operator):
    __slots__ = ()

    idname = 'floating_move'
    description = 'Move a floating item by dragging (pointer binding only).'
    pointer_only = True

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _FloatingMove.Properties) -> str:
        return 'Float Move'

    @staticmethod
    def exec(properties: _FloatingMove.Properties, event: ion.types.Event) -> bool:
        from ion_utils._internal.operators.floating_move_impl import exec_generator
        ion.utils.exec_generator(exec_generator(event))
        return True


class _FloatingResize(_Operator):
    __slots__ = ()

    idname = 'floating_resize'
    description = 'Resize a floating item by dragging (pointer binding only).'
    pointer_only = True

    class Properties(NamedTuple):
        border: Annotated[bool, 'Use border-relative edge detection (drag initiated from border).'] = False

    @staticmethod
    def name(properties: _FloatingResize.Properties) -> str:
        return 'Float Resize'

    @staticmethod
    def exec(properties: _FloatingResize.Properties, event: ion.types.Event) -> bool:
        from ion_utils._internal.operators.floating_resize_impl import exec_generator
        ion.utils.exec_generator(exec_generator(event, border=properties.border))
        return True


class _FrameTabDrag(_Operator):
    __slots__ = ()

    idname = 'frame_tab_drag'
    description = 'Drag a tiled tab to move it between frames (pointer binding only).'
    pointer_only = True

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _FrameTabDrag.Properties) -> str:
        return 'Tab Drag'

    @staticmethod
    def exec(properties: _FrameTabDrag.Properties, event: ion.types.Event) -> bool:
        from ion_utils._internal.operators.frame_tab_drag_impl import exec_generator
        ion.utils.exec_generator(exec_generator(event))
        return True


class _FrameTabActivate(_Operator):
    __slots__ = ()

    idname = 'frame_tab_activate'
    description = 'Activate the tab under the pointer.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _FrameTabActivate.Properties) -> str:
        return 'Tab Activate'

    @staticmethod
    def exec(properties: _FrameTabActivate.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (window := context.window) is not None and (frame := context.frame) is not None:
            frame.windows.active = window
        return True


class _TilingDividerResize(_Operator):
    __slots__ = ()

    idname = 'tiling_divider_resize'
    description = 'Resize by dragging the split divider under the pointer (pointer binding only).'
    pointer_only = True

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _TilingDividerResize.Properties) -> str:
        return 'Divider Resize'

    @staticmethod
    def exec(properties: _TilingDividerResize.Properties, event: ion.types.Event) -> bool:
        from ion_utils._internal.operators.tiling_divider_resize_impl import exec_generator
        ion.utils.exec_generator(exec_generator(event))
        return True


# ---------------------------------------------------------------------------
# Frame operators
# ---------------------------------------------------------------------------


class _FrameDelete(_Operator):
    __slots__ = ()

    idname = 'frame_delete'
    description = 'Remove the current frame from its parent split.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _FrameDelete.Properties) -> str:
        return 'Frame Delete'

    @staticmethod
    def poll(properties: _FrameDelete.Properties) -> str | None:
        from ion.wm import context
        frame = context.frame
        if frame is None:
            return 'No focused frame'
        if frame.windows:
            return 'Frame is not empty'
        return None

    @staticmethod
    def exec(properties: _FrameDelete.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (
            (frame := context.frame) is not None
            and (node := frame.split_node) is not None
            and (parent := node.parent) is not None
        ):
            parent.child_remove(node)
        return True


class _FrameJoin(_Operator):
    __slots__ = ()

    idname = 'frame_join'
    description = 'Recursively merge the parent split into a single frame.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _FrameJoin.Properties) -> str:
        return 'Join Frames'

    @staticmethod
    def poll(properties: _FrameJoin.Properties) -> str | None:
        if _split_target(0) is None:
            return 'No split to join'
        return None

    @staticmethod
    def exec(properties: _FrameJoin.Properties, event: ion.types.Event) -> bool:
        if (target := _split_target(0)) is not None:
            target.join()
        return True


class _WindowClose(_Operator):
    __slots__ = ()

    idname = 'window_close'
    description = 'Close focused window, or remove frame if empty.'

    class Properties(NamedTuple):
        delete_empty_frame: Annotated[bool, 'Remove the frame when it has no windows.'] = False
        delete_empty_workspace: Annotated[bool, 'Delete the workspace if it has only one empty frame.'] = False

    @staticmethod
    def target_resolve(properties: _WindowClose.Properties) -> Window | Workspace | Frame | None:
        """Resolve the element to act on, None when there is nothing to do.

        The type selects the action: close a window, delete a workspace, or join
        a frame back into its parent split.
        """
        from ion.wm import context
        if (window := context.window) is not None:
            return window
        if properties.delete_empty_frame and (frame := context.frame) is not None:
            if (
                properties.delete_empty_workspace
                and (ws := context.workspace) is not None
                and len(ws.frames) == 1
                and not ws.frames[0].windows
            ):
                # Nothing to collapse, interpret as a request to close the workspace.
                return ws
            return frame
        return None

    @staticmethod
    def name(properties: _WindowClose.Properties) -> str:
        target = _WindowClose.target_resolve(properties)
        if isinstance(target, Workspace):
            return 'Close Workspace'
        if isinstance(target, Frame):
            return 'Join Frames'
        return 'Close Window'

    @staticmethod
    def poll(properties: _WindowClose.Properties) -> str | None:
        if _WindowClose.target_resolve(properties) is None:
            return 'No window to close'
        return None

    @staticmethod
    def exec(properties: _WindowClose.Properties, event: ion.types.Event) -> bool:
        from ion.app import preferences
        target = _WindowClose.target_resolve(properties)
        if isinstance(target, Window):
            target.close()
        elif isinstance(target, Workspace):
            ion.wm.workspaces.remove(target)
            return False
        elif (
            isinstance(target, Frame)
            and (node := target.split_node) is not None
            and (parent := node.parent) is not None
        ):
            parent.child_remove(node)
            if preferences.focus.pointer_warp and (new_frame := ion.wm.frames.active) is not None:
                new_frame.pointer_warp_if_needed()
        return True


def _split_container_at_depth(parent_depth: int) -> SplitNodeContainer | None:
    """Resolve the target container node for axis operations."""
    from ion.wm import context
    if parent_depth == -1:
        if (ws := context.workspace) is not None:
            root = ws.root
            if isinstance(root, SplitNodeContainer):
                return root
        return None
    if (frame := context.frame) is not None:
        node = frame.split_node
        if node is not None:
            target = node.parent
            for _ in range(parent_depth):
                if target is None:
                    return None
                target = target.parent
            return target
    return None


def _split_target(parent_depth: int) -> SplitNodeContainer | None:
    """Resolve the split a divider operator acts on.

    Prefers the context split when one is set -- the split whose divider is
    under the pointer when the divider menu is open. Falls back to the
    container at `parent_depth` from the active frame, which is the path for
    the frame menu, where the pointer was over a frame and so carries none.
    """
    from ion.wm import context
    if (split := context.split) is not None:
        return split
    return _split_container_at_depth(parent_depth)


class _TilingSplitAxisSet(_Operator):
    __slots__ = ()

    idname = 'tiling_split_axis_set'
    description = 'Set or toggle the split direction at a given depth.'

    class Properties(NamedTuple):
        axis: Annotated[_LiteralToggleOrSet, '-1 to toggle, 0 for horizontal, 1 for vertical.'] = -1
        parent_depth: Annotated[int, "0 for the frame's parent, 1 for grandparent, etc. -1 for root."] = 0
        pointer_warp: Annotated[bool, 'Warp pointer to the active frame after changing.'] = True

    @staticmethod
    def name(properties: _TilingSplitAxisSet.Properties) -> str:
        if properties.parent_depth == -1:
            return 'Set Root Axis Direction'
        return 'Set Axis Direction'

    @staticmethod
    def poll(properties: _TilingSplitAxisSet.Properties) -> str | None:
        if _split_target(properties.parent_depth) is None:
            return 'No target split node'
        return None

    @staticmethod
    def exec(properties: _TilingSplitAxisSet.Properties, event: ion.types.Event) -> bool:
        if (target := _split_target(properties.parent_depth)) is not None:
            axis = properties.axis
            if axis == -1:
                axis = 0 if target.split_axis == 1 else 1
            target.split_axis_set(axis=axis, pointer_warp=properties.pointer_warp)
        return True


class _TilingSplitAxisRotate(_Operator):
    __slots__ = ()

    idname = 'tiling_split_axis_rotate'
    description = 'Rotate the split axis by 90, 180, or 270 degrees.'

    class Properties(NamedTuple):
        angle: Annotated[Literal[90, 180, 270], '90 (left), 180 (flip), or 270 (right).'] = 90
        parent_depth: Annotated[int, "0 for the frame's parent, 1 for grandparent, etc. -1 for root."] = 0
        pointer_warp: Annotated[bool, 'Warp pointer to the active frame after changing.'] = True

    @staticmethod
    def name(properties: _TilingSplitAxisRotate.Properties) -> str:
        label = {90: 'Left', 180: 'Flip', 270: 'Right'}.get(properties.angle, str(properties.angle))
        prefix = 'Root ' if properties.parent_depth == -1 else ''
        return '{:s}Rotate Axis {:s}'.format(prefix, label)

    @staticmethod
    def poll(properties: _TilingSplitAxisRotate.Properties) -> str | None:
        if _split_target(properties.parent_depth) is None:
            return 'No target split node'
        return None

    @staticmethod
    def exec(properties: _TilingSplitAxisRotate.Properties, event: ion.types.Event) -> bool:
        target = _split_target(properties.parent_depth)
        if target is None:
            return True
        angle = properties.angle
        # 90: flip axis + swap, 180: swap only, 270: flip axis only.
        target.axis_rotate(
            flip_axis=angle != 180,
            swap_children=angle != 270,
            pointer_warp=properties.pointer_warp,
        )
        return True


class _TilingSwap(_Operator):
    __slots__ = ()

    idname = 'tiling_swap'
    description = 'Swap the two children at a given depth.'

    class Properties(NamedTuple):
        parent_depth: Annotated[int, "0 for the frame's parent, 1 for grandparent, etc. -1 for root."] = 0
        pointer_warp: Annotated[bool, 'Warp pointer to the active frame after swapping.'] = True

    @staticmethod
    def name(properties: _TilingSwap.Properties) -> str:
        return 'Swap Child Frames'

    @staticmethod
    def poll(properties: _TilingSwap.Properties) -> str | None:
        if _split_target(properties.parent_depth) is None:
            return 'No target split node'
        return None

    @staticmethod
    def exec(properties: _TilingSwap.Properties, event: ion.types.Event) -> bool:
        if (target := _split_target(properties.parent_depth)) is not None:
            target.child_swap(pointer_warp=properties.pointer_warp)
        return True


class _TilingDividerGaplessSet(_Operator):
    __slots__ = ()

    idname = 'tiling_divider_gapless_set'
    description = 'Set whether the split divider renders flush, with no gap between its frames.'

    class Properties(NamedTuple):
        mode: Annotated[
            Literal[-1, 0, 1, 2],
            '-1 to toggle, 0 to show the divider, 1 to make it gapless, 2 for automatic.',
        ] = -1
        parent_depth: Annotated[int, "0 for the frame's parent, 1 for grandparent, etc. -1 for root."] = 0

    @staticmethod
    def name(properties: _TilingDividerGaplessSet.Properties) -> str:
        if properties.mode == 2:
            return 'Automatic Divider'
        if properties.mode > 0:
            return 'Gapless Divider'
        if properties.mode == 0:
            return 'Show Divider'
        return 'Gapless Divider Toggle'

    @staticmethod
    def poll(properties: _TilingDividerGaplessSet.Properties) -> str | None:
        if _split_target(properties.parent_depth) is None:
            return 'No target split node'
        return None

    @staticmethod
    def exec(properties: _TilingDividerGaplessSet.Properties, event: ion.types.Event) -> bool:
        if (target := _split_target(properties.parent_depth)) is not None:
            mode = properties.mode
            if mode == 2:
                target.gapless_manual = False
            elif mode < 0:
                target.gapless ^= True
            else:
                target.gapless = mode > 0
        return True


class _TilingResize(_Operator):
    __slots__ = ()

    idname = 'tiling_resize'
    description = 'Resize the current frame by a delta in logical pixels.'

    class Properties(NamedTuple):
        delta: Annotated[int, 'Amount in logical pixels (positive grows, negative shrinks).']

    @staticmethod
    def name(properties: _TilingResize.Properties) -> str:
        return 'Grow' if properties.delta > 0 else 'Shrink'

    @staticmethod
    def poll(properties: _TilingResize.Properties) -> str | None:
        from ion.wm import context
        if context.frame is None:
            return 'No focused frame'
        return None

    @staticmethod
    def exec(properties: _TilingResize.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (
            (frame := context.frame) is not None
            and (node := frame.split_node) is not None
            and (parent := node.parent) is not None
            and (dim := parent.rect.size[parent.split_axis]) > 0
        ):
            # Ratio is the fraction for child_min, so negate the delta when the
            # focused frame is child_max.
            sign = 1 if parent.child_min == node else -1
            parent.split_ratio += sign * properties.delta / dim
        return True


class _FrameUntile(_Operator):
    __slots__ = ()

    idname = 'frame_untile'
    description = 'Extract frame from tiling into a floating workspace.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _FrameUntile.Properties) -> str:
        return 'Untile Frame'

    @staticmethod
    def poll(properties: _FrameUntile.Properties) -> str | None:
        from ion.wm import context
        if context.frame is None:
            return 'No focused frame'
        return None

    @staticmethod
    def exec(properties: _FrameUntile.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (frame := context.frame) is not None and (node := frame.split_node) is not None:
            ws = ion.wm.workspaces.new_from_split_node(node)
            ion.wm.desktops.active.items_floating.add(ws)
        return True


class _WorkspaceUntile(_Operator):
    __slots__ = ()

    idname = 'workspace_untile'
    description = 'Convert tiled workspace to a floating workspace.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WorkspaceUntile.Properties) -> str:
        return 'Untile Workspace'

    @staticmethod
    def poll(properties: _WorkspaceUntile.Properties) -> str | None:
        from ion.wm import context
        if (workspace := context.workspace) is None:
            return 'No workspace under the pointer'
        if not workspace.is_tiling:
            return 'Workspace is not tiled'
        return None

    @staticmethod
    def exec(properties: _WorkspaceUntile.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (workspace := context.workspace) is not None:
            # `items_floating.add` auto-removes from tiling and seeds
            # `floating_rect` from the tile rect, so the workspace appears
            # where the user just saw the workspace.
            ion.wm.desktops.active.items_floating.add(workspace)
        return True


class _TilingFloatingSplit(_Operator):
    __slots__ = ()

    idname = 'tiling_floating_split'
    description = 'Extract the sibling subtree of the current frame into a floating workspace.'

    class Properties(NamedTuple):
        direction: Annotated[_LiteralDirection, 'Direction to move.']

    @staticmethod
    def name(properties: _TilingFloatingSplit.Properties) -> str:
        return 'Float Split'

    @staticmethod
    def poll(properties: _TilingFloatingSplit.Properties) -> str | None:
        from ion.wm import context
        if context.frame is None:
            return 'No focused frame'
        return None

    @staticmethod
    def exec(properties: _TilingFloatingSplit.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (
            (frame := context.frame) is not None
            and (node := frame.split_node) is not None
            and (adjacent := node.find_adjacent(properties.direction)) is not None
        ):
            ws = ion.wm.workspaces.new_from_split_node(adjacent)
            ion.wm.desktops.active.items_floating.add(ws)
        return True


class _FrameTile(_Operator):
    __slots__ = ()

    idname = 'frame_tile'
    description = 'Tile floating workspace frame back into the tiling workspace.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _FrameTile.Properties) -> str:
        return 'Tile'

    @staticmethod
    def poll(properties: _FrameTile.Properties) -> str | None:
        from ion.wm import context
        if context.frame is None:
            return 'No focused frame'
        if (workspace := context.workspace) is None:
            return 'No workspace under the pointer'
        if workspace.is_tiling:
            return 'Frame is in a tiling workspace'
        desktop = ion.wm.desktops.active
        output = ion.wm.outputs.active
        if output is None or not desktop.items_tiling.find_by_output(output):
            return 'No tiling workspace on output'
        return None

    @staticmethod
    def exec(properties: _FrameTile.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (frame := context.frame) is not None:
            frame.tile()
        return True


class _WorkspaceTileOnDesktop(_Operator):
    __slots__ = ()

    idname = 'workspace_tile_on_desktop'
    description = 'Convert floating workspace to a tiled workspace.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WorkspaceTileOnDesktop.Properties) -> str:
        return 'Workspace Tile'

    @staticmethod
    def poll(properties: _WorkspaceTileOnDesktop.Properties) -> str | None:
        from ion.wm import context
        if (workspace := context.workspace) is None:
            return 'No focused workspace'
        if workspace.is_tiling:
            return 'Workspace is already tiled'
        desktop = context.desktop
        if desktop.items_tiling.has_per_output:
            return 'Per-output workspaces exist'
        if desktop.items_tiling.has_all_output:
            return 'All-output workspaces exist'
        return None

    @staticmethod
    def exec(properties: _WorkspaceTileOnDesktop.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (workspace := context.workspace) is None:
            return False
        desktop = context.desktop
        # `context.workspace` is on the active desktop's floating layer (the
        # poll rejects tiled workspaces).
        desktop.items_tiling.add(workspace)
        return True


class _WorkspaceTileOnOutput(_Operator):
    __slots__ = ()

    idname = 'workspace_tile_on_output'
    description = 'Convert floating workspace to a per-output tiled workspace.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WorkspaceTileOnOutput.Properties) -> str:
        return 'Workspace Tile on Output'

    @staticmethod
    def poll(properties: _WorkspaceTileOnOutput.Properties) -> str | None:
        from ion.wm import context
        if (workspace := context.workspace) is None:
            return 'No focused workspace'
        if workspace.is_tiling:
            return 'Workspace is already tiled'
        desktop = context.desktop
        if desktop.items_tiling.has_all_output:
            return 'All-output workspaces exist'
        if (output := context.output) is None:
            return 'No output under the pointer'
        if desktop.items_tiling.find_by_output(output) is not None:
            return 'Output already has a workspace'
        return None

    @staticmethod
    def exec(properties: _WorkspaceTileOnOutput.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (workspace := context.workspace) is None:
            return False
        desktop = context.desktop
        if (output := context.output) is None:
            return False
        # `context.workspace` is on the active desktop's floating layer (the
        # poll rejects tiled workspaces).
        desktop.items_tiling.add(workspace, output)
        return True


def _workspace_ensure(name: str) -> ion.types.Workspace:
    """Get a workspace by name, creating it if it doesn't exist.

    When creating, center an 80% rect on the active output.
    """
    if (ws := ion.wm.workspaces.get(name)) is None:
        output = ion.wm.outputs.active_pointer
        assert output is not None
        r = output.rect
        w, h = int(r.size_x * 0.8), int(r.size_y * 0.8)
        x, y = r.center_floor_x() - w // 2, r.center_floor_y() - h // 2
        ws = ion.wm.workspaces.new(ion.types.Rect((x, y), (x + w, y + h)), name)
    return ws


def _workspace_reposition_to_output(
    ws: ion.types.Workspace, output: ion.types.Output,
) -> None:
    """Reposition a floating workspace to an output, preserving relative placement.

    The workspace keeps the same fractional offset and size ratio relative to
    the target output as it had on its previous output.
    """
    rect = ws.floating_rect

    # Find which output currently contains the workspace center.
    center = rect.center_floor()
    src_output = None
    for o in ion.wm.outputs:
        if o.rect.contains(center):
            src_output = o
            break

    if src_output is None or src_output == output:
        return

    # A workspace larger than a single output may span multiple outputs
    # intentionally. Repositioning it would shrink and confine it to one
    # output, destroying the user's layout. Skip when already visible on
    # the target.
    if rect.intersects(output.rect):
        return

    ws.floating_rect = _rect_remap(rect, src_output.rect, output.rect)


class _WorkspaceFloatingSet(_Operator):
    __slots__ = ()

    idname = 'workspace_floating_set'
    description = 'Set whether a named workspace floats.'

    class Properties(NamedTuple):
        name: Annotated[str, 'Workspace name.']
        mode: Annotated[_LiteralToggleOrSet, '-1 to toggle, 0 to hide, 1 to show.'] = -1
        use_active_output: Annotated[bool, 'Reposition the workspace to the active output when showing.'] = True

    @staticmethod
    def name(properties: _WorkspaceFloatingSet.Properties) -> str:
        if properties.mode > 0:
            return 'Show Floating'
        if properties.mode == 0:
            return 'Hide Floating'
        return 'Toggle Floating'

    @staticmethod
    def exec(properties: _WorkspaceFloatingSet.Properties, event: ion.types.Event) -> bool:
        ws = _workspace_ensure(properties.name)
        active_desktop = ion.wm.desktops.active
        on_active = active_desktop.items_floating.find_by_workspace(ws) is not None
        mode = properties.mode
        if mode < 0:
            # Toggle is anchored to the active desktop: if the workspace is
            # already floating here, hide it; otherwise show it here (relocating
            # from another desktop if needed).
            mode = 0 if on_active else 1
        if mode == 0 and ws.is_floating:
            # Hide wherever the workspace floats -- floating ownership is
            # exclusive (enforced in `workspace_floating_show_on_desktop`),
            # so the first match is the only match.
            for desktop in ion.wm.desktops:
                if (item := desktop.items_floating.find_by_workspace(ws)) is not None:
                    desktop.items_floating.remove(item)
                    break
        elif mode > 0 and not on_active:
            # Float the workspace on the active desktop. If it was tiled,
            # `items_floating.add` orphans it and fires the unmap-tiling
            # hook. If it was floating on another desktop, the
            # cross-desktop exclusivity rule relocates it here.
            active_desktop.items_floating.add(ws)
            if properties.use_active_output and (output := ion.wm.outputs.active_pointer) is not None:
                _workspace_reposition_to_output(ws, output)
        return True


class _WindowWorkspacePush(_Operator):
    __slots__ = ()

    idname = 'window_workspace_push'
    description = 'Send focused window to named workspace.'

    class Properties(NamedTuple):
        name: Annotated[str, 'Target workspace name.']

    @staticmethod
    def name(properties: _WindowWorkspacePush.Properties) -> str:
        return 'Send to Workspace'

    @staticmethod
    def poll(properties: _WindowWorkspacePush.Properties) -> str | None:
        from ion.wm import context
        if context.window is None:
            return 'No focused window'
        return None

    @staticmethod
    def exec(properties: _WindowWorkspacePush.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (window := context.window) is None:
            return False
        ws = _workspace_ensure(properties.name)
        if (target := next(iter(ws.frames), None)) is None:
            return False
        current = context.frame
        if not window.tag:
            window.tag = True
        target.attach_tagged()
        # The frame may have been removed if it was a floating frame
        # that became empty after attach_tagged moved its last window.
        if current is not None and current.is_valid:
            current.focus()
        return True


class _WindowWorkspacePop(_Operator):
    __slots__ = ()

    idname = 'window_workspace_pop'
    description = 'Move a window from a named workspace to the focused frame.'

    class Properties(NamedTuple):
        name: Annotated[str, 'Source workspace name.']
        window_index: Annotated[
            int,
            'Window index. -1 is the most recently added window, 0 is the oldest. '
            'Supports negative indexing, clamped to range.',
        ] = -1

    @staticmethod
    def name(properties: _WindowWorkspacePop.Properties) -> str:
        return 'Restore from Workspace'

    @staticmethod
    def poll(properties: _WindowWorkspacePop.Properties) -> str | None:
        from ion.wm import context
        if context.frame is None:
            return 'No focused frame'
        return None

    @staticmethod
    def exec(properties: _WindowWorkspacePop.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (ws := ion.wm.workspaces.get(properties.name)) is None:
            return False
        count = len(ws.windows)
        if count == 0:
            return False
        index = properties.window_index
        if index < 0:
            index += count
        index = max(0, min(count - 1, index))
        window = ws.windows[index]
        if (frame := context.frame) is None:
            return False
        if not window.tag:
            window.tag = True
        frame.attach_tagged()
        return True


# Map navigation direction to (axis, side). side=1 means towards-max (right/down).
_DirectionValue = tuple[Literal[0, 1], Literal[0, 1]]
_direction_map: dict[str, _DirectionValue] = {
    'LEFT': (0, 0),
    'RIGHT': (0, 1),
    'UP': (1, 0),
    'DOWN': (1, 1),
}


def _sibling_find_in_direction(node: SplitNode, direction: str) -> SplitNode | None:
    """Walk up the tree to find a sibling in the navigation direction.

    At each ancestor, check if the split axis aligns with the direction
    and we sit on the opposite side (so there is a sibling to cross to).
    """
    dir_axis, side = _direction_map[direction]
    current = node
    while True:
        if (parent := current.parent) is None:
            return None
        is_min_child = (parent.child_min == current)
        if parent.split_axis == dir_axis and side == is_min_child:
            return parent.child_max if side else parent.child_min
        current = parent


def _frame_find_in_subtree(node: SplitNode, direction: str) -> Frame:
    """Walk down a subtree to find the target frame.

    At each aligned split, pick the child closest to where we came from
    (e.g. navigating right enters from the left, so pick child_min).
    At perpendicular splits, follow last-active tracking.
    """
    dir_axis, side = _direction_map[direction]
    while not isinstance(node, SplitNodeLeaf):
        assert isinstance(node, SplitNodeContainer)
        if node.split_axis == dir_axis:
            node = node.child_min if side else node.child_max
        else:
            node = node.last_active
    return node.frame


def _best_by_rect_overlap[T](target: Rect, candidates: Iterable[tuple[T, Rect]]) -> T | None:
    """Find the candidate whose rect has the best overlap with target.

    Returns the item with the greatest intersection area. Ties are broken
    by penalizing candidates with large area outside the intersection.
    Returns None if no candidate intersects target.
    """
    item_best = None
    score_best = (0, 0)
    for item_test, rect_test in candidates:
        if (isect := target.intersection(rect_test)) is not None:
            area = isect.area()
            # Primary: largest overlap. Tie-breaker: penalize excess area.
            score_test = (area, -(rect_test.area() - area))
            if score_test > score_best:
                item_best = item_test
                score_best = score_test
    return item_best


def _output_for_rect(rect: Rect) -> Output | None:
    """Find the output with the most overlap for a rectangle."""
    return _best_by_rect_overlap(rect, ((o, o.rect) for o in ion.wm.outputs))


def _rect_remap(rect: Rect, src: Rect, dst: Rect) -> Rect:
    """Map a rectangle proportionally from one region to another."""
    if src.size == dst.size:
        # Same-size regions: translate by origin offset.
        offset = dst.min - src.min
        return ion.types.Rect(rect.min + offset, rect.max + offset)
    return src.rect_remap_floor(rect, dst)


def _frame_best_match(
    frame: Frame, src_output: Output, dst_output: Output, ws: Workspace,
) -> Frame | None:
    """Find the frame on the target output that best matches the source frame.

    Maps the frame rect proportionally from the source to the destination
    output, then picks the frame with the greatest intersection area.
    Ties are broken by penalizing candidates with large area outside
    the intersection.
    """
    if (node := frame.split_node) is None:
        return None
    mapped = _rect_remap(node.rect, src_output.rect, dst_output.rect)
    return _best_by_rect_overlap(mapped, (
        (f, n.rect) for f in ws.frames if (n := f.split_node) is not None
    ))


def _output_find_adjacent(output: Output, direction: str) -> Output | None:
    """Find the adjacent output in a direction (touching edge, max overlap)."""
    r = output.rect
    best = None
    best_overlap = 0
    for other in ion.wm.outputs:
        if other == output:
            continue
        o = other.rect
        match direction:
            case 'RIGHT':
                if o.min.x != r.max.x:
                    continue
                overlap = min(r.max.y, o.max.y) - max(r.min.y, o.min.y)
            case 'LEFT':
                if o.max.x != r.min.x:
                    continue
                overlap = min(r.max.y, o.max.y) - max(r.min.y, o.min.y)
            case 'DOWN':
                if o.min.y != r.max.y:
                    continue
                overlap = min(r.max.x, o.max.x) - max(r.min.x, o.min.x)
            case 'UP':
                if o.max.y != r.min.y:
                    continue
                overlap = min(r.max.x, o.max.x) - max(r.min.x, o.min.x)
            case _:
                continue
        if overlap > best_overlap:
            best = other
            best_overlap = overlap
    return best


def _interval_overlap(a_min: int, a_max: int, b_min: int, b_max: int) -> int:
    return min(a_max, b_max) - max(a_min, b_min)


def _rects_touch_corner(a: Rect, b: Rect) -> bool:
    return (
        (a.max.x == b.min.x or b.max.x == a.min.x)
        and (a.max.y == b.min.y or b.max.y == a.min.y)
    )


def _rect_edge_touch_overlap(a: Rect, b: Rect) -> int:
    best = 0
    for axis in (0, 1):
        cross_axis = 1 - axis
        if a.max[axis] == b.min[axis] or b.max[axis] == a.min[axis]:
            overlap = _interval_overlap(
                a.min[cross_axis], a.max[cross_axis],
                b.min[cross_axis], b.max[cross_axis],
            )
            best = max(best, overlap)
    return best


def _output_find_wrapped_diagonal(
    output: Output, dir_axis: Literal[0, 1], side: Literal[0, 1],
) -> Output | None:
    """Find a corner-touch diagonal output by translating the source rect.

    This is a fallback only after normal axis-sharing wrap fails. Move the
    source rect one output-width/height in the requested direction, wrap that
    translated rect around the output bounds, then accept a corner-touching
    output when the translated rect touches it by an edge.
    """
    r = output.rect
    bounds_min = r.min[dir_axis]
    bounds_max = r.max[dir_axis]
    for other in ion.wm.outputs:
        o = other.rect
        bounds_min = min(bounds_min, o.min[dir_axis])
        bounds_max = max(bounds_max, o.max[dir_axis])

    bounds_size = bounds_max - bounds_min
    offset = [0, 0]
    offset[dir_axis] = r.size[dir_axis] if side else -r.size[dir_axis]
    translated = r.copy()
    translated.translate((offset[0], offset[1]))
    if translated.min[dir_axis] < bounds_min:
        offset[dir_axis] = bounds_size
        translated.translate((offset[0], offset[1]))
    elif translated.max[dir_axis] > bounds_max:
        offset[dir_axis] = -bounds_size
        translated.translate((offset[0], offset[1]))

    best = None
    best_touch = 0
    for other in ion.wm.outputs:
        if other == output:
            continue
        o = other.rect
        if not _rects_touch_corner(r, o):
            continue
        if (touch := _rect_edge_touch_overlap(translated, o)) > best_touch:
            best = other
            best_touch = touch
    return best


def _output_find_wrapped(output: Output, direction: str) -> Output | None:
    """Find the output on the opposite edge when wrapping around.

    Only considers outputs that share a perpendicular overlap with *output*:
    ``RIGHT``/``LEFT`` require Y-axis overlap; ``DOWN``/``UP`` require X-axis
    overlap. This prevents wrapping DOWN in a side-by-side layout from jumping
    to a horizontally-adjacent output that is not in the same column.

    Wrapping ``RIGHT`` picks the leftmost qualifying output (min x), ``LEFT``
    picks the rightmost (max right edge), and likewise for ``DOWN``/``UP``.
    Ties prefer the output with the greatest perpendicular overlap. If no
    output qualifies, corner-touching diagonal outputs are considered by
    translating *output* in *direction* and wrapping it around the output
    bounds. Returns ``None`` when no qualifying output exists.
    """
    if (dir_value := _direction_map.get(direction)) is None:
        return None
    dir_axis, side = dir_value
    cross_axis = 1 - dir_axis
    r = output.rect
    best = None
    best_key = (0, 0)  # Only compared after the first iteration sets `best`.
    for other in ion.wm.outputs:
        if other == output:
            continue
        o = other.rect
        overlap = (
            _interval_overlap(
                r.min[cross_axis], r.max[cross_axis],
                o.min[cross_axis], o.max[cross_axis],
            )
        )
        if overlap <= 0:
            continue
        # `side == 1` (RIGHT/DOWN) wraps to the min edge; negation turns
        # the minimum search into a maximum.
        key = ((-(o.min[dir_axis]) if side else o.max[dir_axis]), overlap)
        if best is None or key > best_key:
            best = other
            best_key = key
    return best or _output_find_wrapped_diagonal(output, dir_axis, side)


def _output_step(output: Output, direction: str, wrap: bool) -> Output | None:
    """Find the next output in *direction*, optionally wrapping at the edge.

    When *wrap* is true and no other output shares the axis (e.g. moving DOWN
    in a side-by-side layout where no output is below), returns *output* itself
    so callers wrap focus to the opposite edge of the same output.
    """
    if (adj := _output_find_adjacent(output, direction)) is not None:
        return adj
    if wrap:
        return _output_find_wrapped(output, direction) or output
    return None


def _output_workspace_entry(output: Output, direction: str) -> Frame | None:
    """Find the entry frame within *output* when entering from *direction*.

    For per-output workspaces this is just the workspace tree's edge frame.
    For all-output (Unified) workspaces the split tree spans multiple
    outputs, so plain tree descent can land on a frame in a different
    output than *output*. When that happens, fall back to picking the
    frame within *output*'s geometry closest to the entering edge.
    """
    if (ws := ion.wm.workspaces.find_by_output(output)) is None:
        return None
    if (root := ws.root) is None:
        return None
    entry = _frame_find_in_subtree(root, direction)
    if entry is not None and ion.wm.outputs.find_by_frame(entry) == output:
        return entry
    return _workspace_entry_within_output(ws, output, direction)


def _workspace_entry_within_output(
    ws: Workspace, output: Output, direction: str,
) -> Frame | None:
    """Pick a frame in *ws* on *output* closest to the entering edge of *direction*."""
    dir_axis, side = _direction_map[direction]
    candidates = [
        (f, n.rect) for f in ws.frames
        if (n := f.split_node) is not None
        and ion.wm.outputs.find_by_frame(f) == output
    ]
    if not candidates:
        return None
    # `side == 1` (RIGHT/DOWN) enters from the min side - pick the frame
    # with the lowest `min[dir_axis]`. `side == 0` (LEFT/UP) enters from
    # the max side - pick the highest `max[dir_axis]`.
    if side:
        return min(candidates, key=lambda c: c[1].min[dir_axis])[0]
    return max(candidates, key=lambda c: c[1].max[dir_axis])[0]


def _frame_sibling_descend(frame: Frame, direction: str) -> Frame | None:
    """Walk to *frame*'s sibling in *direction*, then descend to a leaf.

    Returns ``None`` when *frame* has no sibling along the requested
    direction in any ancestor split.
    """
    if (node := frame.split_node) is None:
        return None
    if (sibling := _sibling_find_in_direction(node, direction)) is None:
        return None
    return _frame_find_in_subtree(sibling, direction)


def _frame_neighbor(frame: Frame, direction: str, wrap: bool = False) -> Frame | None:
    """Find the neighbor frame in a direction.

    Within-workspace: walk up tree for sibling, then down into subtree.
    Cross-output: find adjacent output, get its workspace, enter from direction.
    When *wrap* is true, wrap to the opposite output when at the edge.
    """
    if (sibling_frame := _frame_sibling_descend(frame, direction)) is not None:
        return sibling_frame
    if (output := ion.wm.outputs.find_by_frame(frame)) is None:
        return None
    if (adj_output := _output_step(output, direction, wrap)) is None:
        return None
    if (target := _output_workspace_entry(adj_output, direction)) == frame:
        return None
    return target


def _output_entry_target(output: Output, direction: str) -> Frame | ion.types.Window | None:
    """Return the focus target when entering *output* from *direction*.

    If the output has a fullscreen window, that window is the target
    (the output is treated as a single rectangle covering the whole
    output, hiding any underlying tiling). Otherwise descend into the
    workspace's split tree from the entering edge.
    """
    if (window := output.fullscreen_window) is not None:
        return window
    return _output_workspace_entry(output, direction)


def _frame_or_covering_fullscreen(
    target: Frame | ion.types.Window | None,
) -> Frame | ion.types.Window | None:
    """If *target* is a Frame on an output with a fullscreen window,
    substitute the fullscreen Window (which visually covers the frame).
    """
    if target is None or isinstance(target, ion.types.Window):
        return target
    target_output = ion.wm.outputs.find_by_frame(target)
    if target_output is not None and (fs := target_output.fullscreen_window) is not None:
        return fs
    return target


def _focus_target_directional(
    direction: str, wrap: bool,
) -> Frame | ion.types.Window | None:
    """Find the directional focus target, anchored to the cursor's output.

    The source is :attr:`ion.wm.outputs.active_pointer` (where the
    pointer is), falling back to :attr:`ion.wm.outputs.active` (the
    focused frame's output) for keyboard-only setups where the pointer
    has not moved. Anchoring to the cursor is what matters when focus
    and pointer are on different outputs - e.g. the focused frame `F`
    sits on output A but its window is fullscreen on output B (via
    :func:`fullscreen_move_to_output`) and the user is looking at the
    fullscreen on B; pressing a direction must navigate from B, not A.

    A within-workspace sibling walk runs first when the active frame's
    workspace is the one visible on ``src_output``, and is skipped
    when:

    - ``src_output`` is covered by a fullscreen surface (the
      underlying tiles are not the visible context), or
    - the active frame lives in a different workspace than the one
      shown on ``src_output`` (its split tree is off-screen).

    Cross-output stepping via :func:`_output_entry_target` then takes
    over, substituting a fullscreen window when the destination has
    one. If the cross-output entry lands on the source's own tile
    (which happens when the user is on a fullscreen output whose
    underlying window's tile lives on the target output), the entry
    is walked past to a sibling so focus actually moves.
    """
    from ion.wm import context
    src_output = ion.wm.outputs.active_pointer or ion.wm.outputs.active
    if src_output is None:
        return None
    src_frame = context.frame

    # Within-workspace sibling walk: only valid when the active frame's
    # split tree is the visible context on `src_output` - i.e. no
    # fullscreen surface covers it and the frame's workspace is the one
    # shown there.
    if (
        src_frame is not None
        and src_output.fullscreen_window is None
        and (src_ws := ion.wm.workspaces.find_by_output(src_output)) is not None
        and ion.wm.workspaces.find_by_frame(src_frame) == src_ws
        and (sibling_frame := _frame_sibling_descend(src_frame, direction)) is not None
    ):
        return _frame_or_covering_fullscreen(sibling_frame)

    # Cross-output step from the source output.
    if (adj_output := _output_step(src_output, direction, wrap)) is None:
        return None
    target = _output_entry_target(adj_output, direction)
    # Landing on the source's own tile is a no-op (same logical position
    # the user is already in - happens when crossing back to the output
    # that hosts a remote-fullscreened window's tile). Walk past it.
    # `target == src_frame` requires both to be Frames with the same id,
    # which implies `src_frame is not None`.
    if (
        isinstance(target, ion.types.Frame)
        and target == src_frame
        and (past := _frame_sibling_descend(target, direction)) is not None
    ):
        target = past
    if (
        isinstance(target, ion.types.Frame)
        and target == src_frame
        and adj_output == src_output
    ):
        return None
    return _frame_or_covering_fullscreen(target)


class _TilingFocusDirectional(_Operator):
    __slots__ = ()

    idname = 'tiling_focus_directional'
    description = 'Focus the frame in a direction.'

    class Properties(NamedTuple):
        direction: Annotated[_LiteralDirection, 'Direction to move.']
        wrap: Annotated[bool, 'Wrap to an aligned output, diagonal output, or this output.'] = True

    @staticmethod
    def name(properties: _TilingFocusDirectional.Properties) -> str:
        return 'Focus {:s}'.format(properties.direction.capitalize())

    @staticmethod
    def exec(properties: _TilingFocusDirectional.Properties, event: ion.types.Event) -> bool:
        from ion.app import preferences
        from ion.types import Frame
        target = _focus_target_directional(properties.direction, properties.wrap)
        if target is None:
            return False
        target.focus()
        if preferences.focus.pointer_warp:
            # A fullscreen Window covers the whole output, so warp to the
            # output (the visible rect) rather than the per-frame center,
            # which would be the rect of the hidden tile underneath.
            if isinstance(target, Frame):
                target.pointer_warp_if_needed()
            elif (output := target.output_fullscreen) is not None:
                output.pointer_warp_if_needed()
        return True


class _TilingOrientDirectional(_Operator):
    """
    Orient the active frame's parent split so the frame is in the given direction.

    Combines axis-set and child-swap as needed. Does nothing if the frame is
    already in the desired position or has no sibling.
    """

    __slots__ = ()

    idname = 'tiling_orient_directional'
    description = (
        'Orient the split so the active frame is located in a particular direction. '
        'This provides a convenient way to orient the active frame '
        'without having to perform separate axis-rotate and swap operation.'
    )

    class Properties(NamedTuple):
        direction: Annotated[_LiteralDirection, "Direction to place the active frame in relation to it's sibling."]

    @staticmethod
    def name(properties: _TilingOrientDirectional.Properties) -> str:
        return 'Orient {:s}'.format(properties.direction.capitalize())

    @staticmethod
    def poll(properties: _TilingOrientDirectional.Properties) -> str | None:
        if _split_container_at_depth(0) is None:
            return 'No target split node'
        return None

    @staticmethod
    def exec(properties: _TilingOrientDirectional.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (frame := context.frame) is None:
            return False
        if (node := frame.split_node) is None:
            return False
        if (parent := node.parent) is None:
            return False

        dir_axis, side = _direction_map[properties.direction]
        # side=0 means the active frame should be child_min.
        want_min = (side == 0)
        is_min = (parent.child_min == node)

        need_axis = (parent.split_axis != dir_axis)
        need_swap = (is_min != want_min)

        if need_axis or need_swap:
            # Focus first so the rotate's warp measures the cursor against this
            # frame's rect from before the restructure. A frame that can't take
            # focus would aim that warp at another, so bail.
            if not frame.focus():
                return False
            parent.axis_rotate(flip_axis=need_axis, swap_children=need_swap)

        return True


class _WindowTilingMoveDirectional(_Operator):
    __slots__ = ()

    idname = 'window_tiling_move_directional'
    description = 'Move the focused window to a frame in a direction.'

    class Properties(NamedTuple):
        direction: Annotated[_LiteralDirection, 'Direction to move.']
        wrap: Annotated[bool, 'Wrap to an aligned output, diagonal output, or this output.'] = True

    @staticmethod
    def name(properties: _WindowTilingMoveDirectional.Properties) -> str:
        return 'Move {:s}'.format(properties.direction.capitalize())

    @staticmethod
    def poll(properties: _WindowTilingMoveDirectional.Properties) -> str | None:
        from ion.wm import context
        if context.window is None:
            return 'No focused window'
        return None

    @staticmethod
    def exec(properties: _WindowTilingMoveDirectional.Properties, event: ion.types.Event) -> bool:
        from ion.app import preferences
        from ion.wm import context
        if (window := context.window) is None:
            return False
        if (active := context.frame) is None:
            return False
        if (target := _frame_neighbor(active, properties.direction, wrap=properties.wrap)) is not None:
            window.move_to_frame(target)
            target.focus()
            if preferences.focus.pointer_warp:
                target.pointer_warp_if_needed()
        return True


def _pointer_warp_or_refocus(target: Frame | Output | None, pointer_warp: bool) -> None:
    """Warp the pointer to ``target``, which the caller just focused.

    Without ``pointer_warp`` the pointer stays, and with sloppy focus, focus
    returns to whatever is under it.
    """
    if pointer_warp:
        if target is not None:
            target.pointer_warp_if_needed()
    else:
        ion._internal.sloppy_focus_update()


class _TilingSplit(_Operator):
    __slots__ = ()

    idname = 'tiling_split'
    description = 'Split the current frame in a direction.'

    class Properties(NamedTuple):
        direction: Annotated[_LiteralDirection, 'Direction to place the new frame.']

    @staticmethod
    def name(properties: _TilingSplit.Properties) -> str:
        label = {
            'RIGHT': 'Split Vertical',
            'DOWN': 'Split Horizontal',
            'LEFT': 'Split Vertical',
            'UP': 'Split Horizontal',
        }
        return label.get(properties.direction, 'Split {:s}'.format(properties.direction.capitalize()))

    @staticmethod
    def poll(properties: _TilingSplit.Properties) -> str | None:
        from ion.wm import context
        if context.frame is None:
            return 'No focused frame'
        return None

    @staticmethod
    def exec(properties: _TilingSplit.Properties, event: ion.types.Event) -> bool:
        from ion.app import preferences
        from ion.wm import context
        if (frame := context.frame) is not None:
            if (node := frame.split_node) is None:
                return False
            axis, side = _direction_map[properties.direction]
            node.split(axis, side)
            _pointer_warp_or_refocus(ion.wm.frames.active, preferences.focus.pointer_warp)
        return True


# ---------------------------------------------------------------------------
# Window operators (continued)
# ---------------------------------------------------------------------------


class _WindowFocusLast(_Operator):
    __slots__ = ()

    idname = 'window_focus_last'
    description = 'Focus the previously focused window.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WindowFocusLast.Properties) -> str:
        return 'Focus Last'

    @staticmethod
    def exec(properties: _WindowFocusLast.Properties, event: ion.types.Event) -> bool:
        ion.wm.windows.focus_last()
        return True


# ---------------------------------------------------------------------------
# Workspace operators
# ---------------------------------------------------------------------------


class _WorkspaceNewFloating(_Operator):
    __slots__ = ()

    idname = 'workspace_new_floating'
    description = 'Create a new floating workspace.'

    class Properties(NamedTuple):
        name: Annotated[str, 'Workspace name. Empty string uses a default name.'] = ''

    @staticmethod
    def name(properties: _WorkspaceNewFloating.Properties) -> str:
        return 'New Floating Workspace'

    @staticmethod
    def poll(properties: _WorkspaceNewFloating.Properties) -> str | None:
        if not ion.wm.outputs.active:
            return 'No active output'
        return None

    @staticmethod
    def exec(properties: _WorkspaceNewFloating.Properties, event: ion.types.Event) -> bool:
        if (output := ion.wm.outputs.active) is None:
            return False
        r = output.rect
        # Center an 800x600 workspace on the output.
        w, h = 800, 600
        x, y = r.center_floor_x() - w // 2, r.center_floor_y() - h // 2
        rect = ion.types.Rect((x, y), (x + w, y + h))
        ws = ion.wm.workspaces.new(rect, properties.name)
        ion.wm.desktops.active.items_floating.add(ws)
        return True


class _WorkspaceDelete(_Operator):
    __slots__ = ()

    idname = 'delete_empty_workspace'
    description = 'Delete the current workspace.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WorkspaceDelete.Properties) -> str:
        return 'Delete Workspace'

    @staticmethod
    def poll(properties: _WorkspaceDelete.Properties) -> str | None:
        from ion.wm import context
        if context.workspace is None:
            return 'No focused workspace'
        return None

    @staticmethod
    def exec(properties: _WorkspaceDelete.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (workspace := context.workspace) is not None:
            ion.wm.workspaces.remove(workspace)
        return True


class _WorkspaceNewTilingOnDesktop(_Operator):
    __slots__ = ()

    idname = 'workspace_new_tiling_on_desktop'
    description = 'Create a new tiling workspace.'

    class Properties(NamedTuple):
        name: Annotated[str, 'Workspace name. Empty string uses a default name.'] = ''

    @staticmethod
    def name(properties: _WorkspaceNewTilingOnDesktop.Properties) -> str:
        return 'New Tiled Workspace'

    @staticmethod
    def exec(properties: _WorkspaceNewTilingOnDesktop.Properties, event: ion.types.Event) -> bool:
        ws = ion.wm.workspaces.new(ion.types.Rect((0, 0), (800, 600)), properties.name)
        try:
            ion.wm.desktops.active.items_tiling.add(ws)
        except RuntimeError:
            ion.wm.workspaces.remove(ws)
            return False
        return True


class _WorkspaceNewTilingOnOutput(_Operator):
    __slots__ = ()

    idname = 'workspace_new_tiling_on_output'
    description = 'Create a new tiling workspace confined to the output under the cursor.'

    class Properties(NamedTuple):
        name: Annotated[str, 'Workspace name. Empty string uses a default name.'] = ''

    @staticmethod
    def name(properties: _WorkspaceNewTilingOnOutput.Properties) -> str:
        return 'New Workspace on Output'

    @staticmethod
    def poll(properties: _WorkspaceNewTilingOnOutput.Properties) -> str | None:
        from ion.wm import context
        desktop = context.desktop
        if desktop.items_tiling.has_all_output:
            return 'All-output workspaces exist'
        if (output := context.output) is None:
            return 'No output under the pointer'
        if desktop.items_tiling.find_by_output(output) is not None:
            return 'Output already has a workspace'
        return None

    @staticmethod
    def exec(properties: _WorkspaceNewTilingOnOutput.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        desktop = context.desktop
        if (output := context.output) is None:
            return False
        ws = ion.wm.workspaces.new(ion.types.Rect((0, 0), (800, 600)), properties.name)
        desktop.items_tiling.add(ws, output)
        return True


# ---------------------------------------------------------------------------
# Desktop operators
# ---------------------------------------------------------------------------


class _DesktopNew(_Operator):
    __slots__ = ()

    idname = 'desktop_new'
    description = 'Create a new empty desktop.'

    class Properties(NamedTuple):
        name: Annotated[str, 'Desktop name. Empty string uses a default name.'] = ''

    @staticmethod
    def name(properties: _DesktopNew.Properties) -> str:
        return 'New Desktop'

    @staticmethod
    def exec(properties: _DesktopNew.Properties, event: ion.types.Event) -> bool:
        desktop = ion.wm.desktops.new(properties.name)
        desktop.focus()
        return True


class _DesktopDelete(_Operator):
    __slots__ = ()

    idname = 'desktop_delete'
    description = 'Delete the current desktop.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _DesktopDelete.Properties) -> str:
        return 'Delete Desktop'

    @staticmethod
    def poll(properties: _DesktopDelete.Properties) -> str | None:
        desktops = ion.wm.desktops
        if len(desktops) <= 1:
            return 'Only one desktop'
        desktop = desktops.active
        if not desktop.is_empty:
            return 'Desktop has windows'
        return None

    @staticmethod
    def exec(properties: _DesktopDelete.Properties, event: ion.types.Event) -> bool:
        desktops = ion.wm.desktops
        desktop = desktops.active
        desktops.remove(desktop)
        return True


# ---------------------------------------------------------------------------
# Cycle operators
# ---------------------------------------------------------------------------


def _cycle_next(
    indices: list[int], current: int, direction: int, wrap: bool,
) -> int | None:
    """Return the next index from *indices* relative to *current*.

    *indices* is a sorted list of valid positions. *current* is the
    active position (may not be in *indices*). Returns the next index,
    or None when not wrapping and at the boundary.
    """
    count = len(indices)
    if count == 0:
        return None
    step = 1 if direction > 0 else -1
    try:
        pos = indices.index(current)
    except ValueError:
        # Current position is not in the candidate list.
        # Pick the nearest candidate in the requested direction.
        pos = -1 if step > 0 else count
    target = pos + step
    if wrap:
        target %= count
    elif not 0 <= target < count:
        return None
    return indices[target]


class _FrameFocusCycle(_Operator):
    __slots__ = ()

    idname = 'frame_focus_cycle'
    description = 'Cycle frame focus in the workspace, wrapping around.'

    class Properties(NamedTuple):
        direction: Annotated[int, 'Positive for next, negative for previous.']

    @staticmethod
    def name(properties: _FrameFocusCycle.Properties) -> str:
        return 'Focus Next Frame' if properties.direction > 0 else 'Focus Previous Frame'

    @staticmethod
    def exec(properties: _FrameFocusCycle.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        ws = context.workspace
        if not ws:
            return False
        frames = ws.frames
        indices = list(range(len(frames)))
        current = next((i for i in indices if frames[i].is_focused), -1)
        if (index := _cycle_next(indices, current, properties.direction, wrap=True)) is not None:
            frames[index].focus()
        return True


class _FrameTabIndexMove(_Operator):
    __slots__ = ()

    idname = 'frame_tab_index_move'
    description = 'Move the current tab to the next/previous position.'

    class Properties(NamedTuple):
        direction: Annotated[int, 'Positive for next, negative for previous.']

    @staticmethod
    def name(properties: _FrameTabIndexMove.Properties) -> str:
        return 'Move Tab Next' if properties.direction > 0 else 'Move Tab Previous'

    @staticmethod
    def poll(properties: _FrameTabIndexMove.Properties) -> str | None:
        from ion.wm import context
        if context.window is None:
            return 'No focused window'
        return None

    @staticmethod
    def exec(properties: _FrameTabIndexMove.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        frame = context.frame
        if not frame:
            return False
        frame.tab_move_cycle(properties.direction)
        return True


class _FrameTabCycle(_Operator):
    __slots__ = ()

    idname = 'frame_tab_cycle'
    description = 'Cycle tabs in the current frame.'

    class Properties(NamedTuple):
        direction: Annotated[int, 'Positive for next, negative for previous.']

    @staticmethod
    def name(properties: _FrameTabCycle.Properties) -> str:
        return 'Next Tab' if properties.direction > 0 else 'Previous Tab'

    @staticmethod
    def poll(properties: _FrameTabCycle.Properties) -> str | None:
        from ion.wm import context
        if context.frame is None:
            return 'No focused frame'
        return None

    @staticmethod
    def exec(properties: _FrameTabCycle.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (frame := context.frame) is not None:
            indices = list(range(len(frame.windows)))
            if (index := _cycle_next(indices, frame.active_index, properties.direction, wrap=True)) is not None:
                frame.windows.active = frame.windows[index]
        return True


class _FrameTabNth(_Operator):
    __slots__ = ()

    idname = 'frame_tab_nth'
    description = 'Switch to tab N in the current frame.'

    class Properties(NamedTuple):
        tab_index: Annotated[int, 'Zero-based tab index.']

    @staticmethod
    def name(properties: _FrameTabNth.Properties) -> str:
        return 'Tab {:d}'.format(properties.tab_index + 1)

    @staticmethod
    def poll(properties: _FrameTabNth.Properties) -> str | None:
        from ion.wm import context
        if context.frame is None:
            return 'No focused frame'
        return None

    @staticmethod
    def exec(properties: _FrameTabNth.Properties, event: ion.types.Event) -> bool:
        from ion.wm import context
        if (frame := context.frame) is not None:
            i = properties.tab_index
            if 0 <= i < len(frame.windows):
                frame.windows.active = frame.windows[i]
        return True


class _OutputFocusDirectional(_Operator):
    __slots__ = ()

    idname = 'output_focus_directional'
    description = 'Focus the adjacent output (monitor) in a direction.'

    class Properties(NamedTuple):
        direction: Annotated[_LiteralDirection, 'Direction to move.']
        wrap: Annotated[bool, 'Wrap to an aligned or diagonal corner-touch output.'] = True

    @staticmethod
    def name(properties: _OutputFocusDirectional.Properties) -> str:
        return 'Focus Output {:s}'.format(properties.direction.capitalize())

    @staticmethod
    def poll(properties: _OutputFocusDirectional.Properties) -> str | None:
        if (active := ion.wm.outputs.active) is None:
            return 'No active output'
        output = _output_find_adjacent(active, properties.direction)
        if output is None and properties.wrap:
            output = _output_find_wrapped(active, properties.direction)
        if output is None:
            return 'No output in that direction'
        return None

    @staticmethod
    def exec(properties: _OutputFocusDirectional.Properties, event: ion.types.Event) -> bool:
        if (active := ion.wm.outputs.active) is None:
            return False
        output = _output_find_adjacent(active, properties.direction)
        if output is None and properties.wrap:
            output = _output_find_wrapped(active, properties.direction)
        if output is not None:
            output.focus()
        return True


def _floating_item_resolve() -> DesktopItemFloating | None:
    """Resolve the active floating item.

    Checks ``items_floating.active`` first (floating frames). Falls back to
    ``find_by_workspace`` for floating workspaces whose focus entry
    is tiled.
    """
    desktop = ion.wm.desktops.active
    if (floating_active := desktop.items_floating.active) is not None:
        return floating_active
    # Floating workspace: focus entry is tiled but the workspace
    # lives in the floating layer.
    if (ws := ion.wm.workspaces.active) is not None:
        return desktop.items_floating.find_by_workspace(ws)
    return None


class _OutputMoveDirectional(_Operator):
    __slots__ = ()

    idname = 'output_move_directional'
    description = 'Move the focused item (floating, tiled, or fullscreen) to the output in a direction.'

    class Properties(NamedTuple):
        direction: Annotated[_LiteralDirection, 'Direction to move.']
        pointer_warp: Annotated[bool, 'Warp pointer to follow the moved item.'] = True
        wrap: Annotated[bool, 'Wrap to an aligned or diagonal corner-touch output.'] = True

    @staticmethod
    def name(properties: _OutputMoveDirectional.Properties) -> str:
        return 'Move to Output {:s}'.format(properties.direction.capitalize())

    @staticmethod
    def _src_output() -> Output | str:
        """Resolve the source output for the focused item.

        Returns the output on success, or an error string on failure.
        """
        window = ion.wm.windows.active
        if window is not None and window.fullscreen:
            output = window.output_fullscreen
            return output if output is not None else 'No fullscreen output'
        if (floating_item := _floating_item_resolve()) is not None:
            output = _output_for_rect(floating_item.rect)
            return output if output is not None else 'No output for floating item'
        if (frame := ion.wm.frames.active) is None or window is None:
            return 'No focused item'
        output = ion.wm.outputs.find_by_frame(frame)
        return output if output is not None else 'No active output'

    @staticmethod
    def poll(properties: _OutputMoveDirectional.Properties) -> str | None:
        src = _OutputMoveDirectional._src_output()
        if isinstance(src, str):
            return src
        output = _output_find_adjacent(src, properties.direction)
        if output is None and properties.wrap:
            output = _output_find_wrapped(src, properties.direction)
        if output is None:
            return 'No output in that direction'
        return None

    @staticmethod
    def exec(properties: _OutputMoveDirectional.Properties, event: ion.types.Event) -> bool:
        from ion.app import preferences
        src = _OutputMoveDirectional._src_output()
        if isinstance(src, str):
            return False
        output = _output_find_adjacent(src, properties.direction)
        if output is None and properties.wrap:
            output = _output_find_wrapped(src, properties.direction)
        if output is None:
            return False
        # The property can only opt out of the preference.
        pointer_warp = properties.pointer_warp and preferences.focus.pointer_warp

        # Fullscreen window: move to the target output.
        window = ion.wm.windows.active
        if window is not None and window.fullscreen:
            window.fullscreen_move_to_output(output)
            # Best-effort: follow the tile to the target output so that
            # exiting fullscreen later lands the window where the user
            # just moved it, instead of snapping back to the original
            # output (an awkward "remote fullscreen" state: tile on A,
            # fullscreen surface on B).
            #
            # A no-op here is NOT a bug - remote fullscreen is a valid
            # state that direct callers of `fullscreen_move_to_output`
            # may rely on, and the target output may legitimately have
            # no workspace or no compatible frame to receive the tile.
            # In that case the fullscreen surface still moved (the
            # operator's primary effect); only the tile follow-up is
            # skipped.
            frame = ion.wm.frames.active
            target = None
            if frame is not None:
                tile_src = ion.wm.outputs.find_by_frame(frame)
                if (
                    tile_src is not None
                    and tile_src != output
                    and (ws := ion.wm.workspaces.find_by_output(output)) is not None
                    and ws.frames
                    and (best := _frame_best_match(frame, tile_src, output, ws)) is not None
                ):
                    window.move_to_frame(best)
                    target = best
            # Fall back to the output rect when the tile didn't follow
            # (remote-fullscreen case).
            _pointer_warp_or_refocus(target or output, pointer_warp)
            return False

        # Floating item: remap position to the target output.
        if (floating_item := _floating_item_resolve()) is not None:
            floating_item.move_to_output(output, pointer_warp=pointer_warp)
            return False

        # Tiled window: map frame rect proportionally to target output,
        # then move into the frame with the greatest overlap.
        if window is None:
            return False
        if (frame := ion.wm.frames.active) is None:
            return False
        if (ws := ion.wm.workspaces.find_by_output(output)) is None or not ws.frames:
            return False
        if (target := _frame_best_match(frame, src, output, ws)) is None:
            return False
        window.move_to_frame(target)
        _pointer_warp_or_refocus(target, pointer_warp)
        return True


class _DesktopFocusDirectional(_Operator):
    __slots__ = ()

    idname = 'desktop_focus_directional'
    description = 'Focus the adjacent desktop in a direction.'

    class Properties(NamedTuple):
        direction: Annotated[EdgeDirection, 'Direction to move, a diagonal for the desktop at the corner.']
        wrap: Annotated[bool, 'Wrap to the opposite desktop when at the edge.'] = True
        animate: Annotated[bool, 'Use zoom animation.'] = False

    @staticmethod
    def name(properties: _DesktopFocusDirectional.Properties) -> str:
        suffix = ' (Animated)' if properties.animate else ''
        return 'Focus Desktop {:s}{:s}'.format(
            properties.direction.replace('_', ' ').title(), suffix,
        )

    @staticmethod
    def poll(properties: _DesktopFocusDirectional.Properties) -> str | None:
        if desktop_adjacent(properties.direction, properties.wrap) is None:
            return 'No desktop in that direction'
        return None

    @staticmethod
    def exec(properties: _DesktopFocusDirectional.Properties, event: ion.types.Event) -> bool:
        target = desktop_adjacent(properties.direction, properties.wrap)
        if target is not None:
            desktop_focus(target, properties.animate)
        return True


class _DesktopFocusCycle(_Operator):
    __slots__ = ()

    idname = 'desktop_focus_cycle'
    description = 'Cycle through desktops.'

    class Properties(NamedTuple):
        direction: Annotated[int, 'Positive for next, negative for previous.']
        wrap: Annotated[bool, 'Wrap around at the ends.'] = True
        animate: Annotated[bool, 'Use zoom animation.'] = False

    @staticmethod
    def name(properties: _DesktopFocusCycle.Properties) -> str:
        suffix = ' (Animated)' if properties.animate else ''
        if properties.direction > 0:
            return 'Cycle Next Desktop' + suffix
        return 'Cycle Previous Desktop' + suffix

    @staticmethod
    def exec(properties: _DesktopFocusCycle.Properties, event: ion.types.Event) -> bool:
        desktops = ion.wm.desktops
        indices = list(range(len(desktops)))
        current = desktops.index(desktops.active)
        if (index := _cycle_next(indices, current, properties.direction, properties.wrap)) is not None:
            desktop_focus(desktops[index], properties.animate)
        return True


class _DesktopOverview(_Operator):
    __slots__ = ()

    idname = 'desktop_overview'
    description = 'Zoom out to show all desktops, click one to switch.'

    class Properties(NamedTuple):
        keymap: Annotated[str, 'Keymap name for input handling.']
        trim_empty: Annotated[bool, 'Trim empty desktops from end-points (active desktop always included).'] = False

    @staticmethod
    def name(properties: _DesktopOverview.Properties) -> str:
        return 'Desktop Overview'

    @staticmethod
    def exec(properties: _DesktopOverview.Properties, event: ion.types.Event) -> bool:
        from ion_utils._internal.operators.desktop_overview_impl import exec_generator
        keymap = modal_keymap_get(properties.keymap)
        ion.utils.exec_generator(
            exec_generator(
                keymap=keymap,
                event=event,
                trim_empty=properties.trim_empty))
        return True


class _DesktopOverviewConfirm(_Operator):
    __slots__ = ()

    idname = 'desktop_overview_confirm'
    description = 'Confirm selection in desktop overview.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _DesktopOverviewConfirm.Properties) -> str:
        return 'Desktop Overview Confirm'

    @staticmethod
    def exec(properties: _DesktopOverviewConfirm.Properties, event: ion.types.Event) -> bool:
        return True


class _DesktopOverviewCancel(_Operator):
    __slots__ = ()

    idname = 'desktop_overview_cancel'
    description = 'Cancel desktop overview.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _DesktopOverviewCancel.Properties) -> str:
        return 'Desktop Overview Cancel'

    @staticmethod
    def exec(properties: _DesktopOverviewCancel.Properties, event: ion.types.Event) -> bool:
        return True


class _DesktopOverviewNavigate(_Operator):
    __slots__ = ()

    idname = 'desktop_overview_navigate'
    description = 'Navigate selection in desktop overview.'

    class Properties(NamedTuple):
        direction: Annotated[_LiteralDirection, 'Direction to move.']

    @staticmethod
    def name(properties: _DesktopOverviewNavigate.Properties) -> str:
        return 'Desktop Overview Navigate'

    @staticmethod
    def exec(properties: _DesktopOverviewNavigate.Properties, event: ion.types.Event) -> bool:
        return True


class _DesktopOverviewSelect(_Operator):
    __slots__ = ()

    idname = 'desktop_overview_select'
    description = 'Select desktop at pointer position in desktop overview.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _DesktopOverviewSelect.Properties) -> str:
        return 'Desktop Overview Select'

    @staticmethod
    def exec(properties: _DesktopOverviewSelect.Properties, event: ion.types.Event) -> bool:
        return True


class _WindowOverview(_Operator):
    __slots__ = ()

    idname = 'window_overview'
    description = 'Zoom out to show all windows across desktops in a grid.'

    class Properties(NamedTuple):
        keymap: Annotated[str, 'Keymap name for input handling.']

    @staticmethod
    def name(properties: _WindowOverview.Properties) -> str:
        return 'Window Overview'

    @staticmethod
    def exec(properties: _WindowOverview.Properties, event: ion.types.Event) -> bool:
        from ion_utils._internal.operators.window_overview_impl import exec_generator
        keymap = modal_keymap_get(properties.keymap)
        ion.utils.exec_generator(
            exec_generator(
                keymap=keymap,
                event=event))
        return True


class _WindowOverviewConfirm(_Operator):
    __slots__ = ()

    idname = 'window_overview_confirm'
    description = 'Confirm selection in window overview.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WindowOverviewConfirm.Properties) -> str:
        return 'Window Overview Confirm'

    @staticmethod
    def exec(properties: _WindowOverviewConfirm.Properties, event: ion.types.Event) -> bool:
        return True


class _WindowOverviewCancel(_Operator):
    __slots__ = ()

    idname = 'window_overview_cancel'
    description = 'Cancel window overview.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WindowOverviewCancel.Properties) -> str:
        return 'Window Overview Cancel'

    @staticmethod
    def exec(properties: _WindowOverviewCancel.Properties, event: ion.types.Event) -> bool:
        return True


class _WindowOverviewNavigate(_Operator):
    __slots__ = ()

    idname = 'window_overview_navigate'
    description = 'Navigate selection in window overview.'

    class Properties(NamedTuple):
        direction: Annotated[_LiteralDirection, 'Direction to move.']

    @staticmethod
    def name(properties: _WindowOverviewNavigate.Properties) -> str:
        return 'Window Overview Navigate'

    @staticmethod
    def exec(properties: _WindowOverviewNavigate.Properties, event: ion.types.Event) -> bool:
        return True


class _WindowOverviewSelect(_Operator):
    __slots__ = ()

    idname = 'window_overview_select'
    description = 'Select window at pointer position in window overview.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WindowOverviewSelect.Properties) -> str:
        return 'Window Overview Select'

    @staticmethod
    def exec(properties: _WindowOverviewSelect.Properties, event: ion.types.Event) -> bool:
        return True


class _WindowCycleCarousel(_Operator):
    __slots__ = ()

    idname = 'window_cycle_carousel'
    description = 'Show all windows on a 3D carousel, select one to focus.'

    class Properties(NamedTuple):
        keymap: Annotated[str, 'Keymap name for input handling.']

    @staticmethod
    def name(properties: _WindowCycleCarousel.Properties) -> str:
        return 'Window Carousel'

    @staticmethod
    def exec(properties: _WindowCycleCarousel.Properties, event: ion.types.Event) -> bool:
        from ion_utils._internal.operators.window_cycle_carousel_impl import exec_generator
        keymap = modal_keymap_get(properties.keymap)
        ion.utils.exec_generator(exec_generator(keymap=keymap, event=event))
        return True


class _WindowCarouselConfirm(_Operator):
    __slots__ = ()

    idname = 'window_carousel_confirm'
    description = 'Confirm selection in window carousel.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WindowCarouselConfirm.Properties) -> str:
        return 'Window Carousel Confirm'

    @staticmethod
    def exec(properties: _WindowCarouselConfirm.Properties, event: ion.types.Event) -> bool:
        return True


class _WindowCarouselCancel(_Operator):
    __slots__ = ()

    idname = 'window_carousel_cancel'
    description = 'Cancel window carousel.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WindowCarouselCancel.Properties) -> str:
        return 'Window Carousel Cancel'

    @staticmethod
    def exec(properties: _WindowCarouselCancel.Properties, event: ion.types.Event) -> bool:
        return True


class _DesktopItemCycleCarousel(_Operator):
    __slots__ = ()

    idname = 'desktop_item_cycle_carousel'
    description = 'Show all desktop items on a 3D carousel, select one to focus.'

    class Properties(NamedTuple):
        keymap: Annotated[str, 'Keymap name for input handling.']

    @staticmethod
    def name(properties: _DesktopItemCycleCarousel.Properties) -> str:
        return 'Desktop Item Carousel'

    @staticmethod
    def exec(properties: _DesktopItemCycleCarousel.Properties, event: ion.types.Event) -> bool:
        from ion_utils._internal.operators.desktop_item_cycle_carousel_impl import exec_generator
        keymap = modal_keymap_get(properties.keymap)
        ion.utils.exec_generator(exec_generator(keymap=keymap, event=event))
        return True


class _DesktopItemCarouselConfirm(_Operator):
    __slots__ = ()

    idname = 'desktop_item_carousel_confirm'
    description = 'Confirm selection in desktop item carousel.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _DesktopItemCarouselConfirm.Properties) -> str:
        return 'Desktop Item Carousel Confirm'

    @staticmethod
    def exec(properties: _DesktopItemCarouselConfirm.Properties, event: ion.types.Event) -> bool:
        return True


class _DesktopItemCarouselCancel(_Operator):
    __slots__ = ()

    idname = 'desktop_item_carousel_cancel'
    description = 'Cancel desktop item carousel.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _DesktopItemCarouselCancel.Properties) -> str:
        return 'Desktop Item Carousel Cancel'

    @staticmethod
    def exec(properties: _DesktopItemCarouselCancel.Properties, event: ion.types.Event) -> bool:
        return True


class _WindowSwitcher(_Operator):
    __slots__ = ()

    idname = 'window_switcher'
    description = 'Alt-Tab style switcher for windows on the current desktop.'

    class Properties(NamedTuple):
        keymap: Annotated[str, 'Keymap name for input handling.']
        direction: Annotated[
            int,
            'Initial step applied on invocation: `1` keeps the active window selected (forward shortcut), '
            '`-1` steps one backwards (reverse shortcut).',
        ] = 1

    @staticmethod
    def name(properties: _WindowSwitcher.Properties) -> str:
        return 'Window Switcher' if properties.direction >= 0 else 'Window Switcher (Reverse)'

    @staticmethod
    def exec(properties: _WindowSwitcher.Properties, event: ion.types.Event) -> bool:
        from ion_utils._internal.operators.window_switcher_impl import exec_generator
        keymap = modal_keymap_get(properties.keymap)
        ion.utils.exec_generator(exec_generator(
            keymap=keymap,
            direction=properties.direction,
            event=event,
        ))
        return True


class _WindowSwitcherNext(_Operator):
    __slots__ = ()

    idname = 'window_switcher_next'
    description = 'Advance the window switcher selection.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WindowSwitcherNext.Properties) -> str:
        return 'Window Switcher Next'

    @staticmethod
    def exec(properties: _WindowSwitcherNext.Properties, event: ion.types.Event) -> bool:
        return True


class _WindowSwitcherPrev(_Operator):
    __slots__ = ()

    idname = 'window_switcher_prev'
    description = 'Retreat the window switcher selection.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WindowSwitcherPrev.Properties) -> str:
        return 'Window Switcher Previous'

    @staticmethod
    def exec(properties: _WindowSwitcherPrev.Properties, event: ion.types.Event) -> bool:
        return True


class _WindowSwitcherCancel(_Operator):
    __slots__ = ()

    idname = 'window_switcher_cancel'
    description = 'Cancel the window switcher without activating a window.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _WindowSwitcherCancel.Properties) -> str:
        return 'Window Switcher Cancel'

    @staticmethod
    def exec(properties: _WindowSwitcherCancel.Properties, event: ion.types.Event) -> bool:
        return True


class _DesktopFocusOccupiedCycle(_Operator):
    __slots__ = ()

    idname = 'desktop_focus_occupied_cycle'
    description = 'Cycle through occupied desktops.'

    class Properties(NamedTuple):
        direction: Annotated[int, 'Positive for next, negative for previous.']
        wrap: Annotated[bool, 'Wrap around at the ends.'] = True
        animate: Annotated[bool, 'Use zoom animation.'] = False

    @staticmethod
    def name(properties: _DesktopFocusOccupiedCycle.Properties) -> str:
        suffix = ' (Animated)' if properties.animate else ''
        if properties.direction > 0:
            return 'Cycle Next Occupied Desktop' + suffix
        return 'Cycle Previous Occupied Desktop' + suffix

    @staticmethod
    def exec(properties: _DesktopFocusOccupiedCycle.Properties, event: ion.types.Event) -> bool:
        desktops = ion.wm.desktops
        indices = [i for i, d in enumerate(desktops) if not d.is_empty]
        current = desktops.index(desktops.active)
        if (index := _cycle_next(indices, current, properties.direction, properties.wrap)) is not None:
            desktop_focus(desktops[index], properties.animate)
        return True


class _DesktopFocusEmptyCycle(_Operator):
    __slots__ = ()

    idname = 'desktop_focus_empty_cycle'
    description = 'Cycle through empty desktops, creating one if none exist.'

    class Properties(NamedTuple):
        direction: Annotated[int, 'Positive for next, negative for previous.']
        wrap: Annotated[bool, 'Wrap around at the ends.'] = True
        name: Annotated[str, 'Name for the new desktop if one is created.'] = ''
        animate: Annotated[bool, 'Use zoom animation.'] = False

    @staticmethod
    def name(properties: _DesktopFocusEmptyCycle.Properties) -> str:
        suffix = ' (Animated)' if properties.animate else ''
        if properties.direction > 0:
            return 'Cycle Next Empty Desktop' + suffix
        return 'Cycle Previous Empty Desktop' + suffix

    @staticmethod
    def exec(properties: _DesktopFocusEmptyCycle.Properties, event: ion.types.Event) -> bool:
        desktops = ion.wm.desktops
        indices = [i for i, d in enumerate(desktops) if d.is_empty]
        current = desktops.index(desktops.active)
        if (index := _cycle_next(indices, current, properties.direction, properties.wrap)) is not None:
            desktop_focus(desktops[index], properties.animate)
        else:
            # No empty desktop found: create one.
            desktop = desktops.new(properties.name)
            desktop_focus(desktop, properties.animate)
        return True


# ---------------------------------------------------------------------------
# Menu operators
# ---------------------------------------------------------------------------


class _MenuShow(_Operator):
    __slots__ = ()

    idname = 'menu_show'
    description = 'Show a named context menu.'

    class Properties(NamedTuple):
        idname: Annotated[str, 'The menu identifier.']

    @staticmethod
    def name(properties: _MenuShow.Properties) -> str:
        return 'Show Menu'

    @staticmethod
    def exec(properties: _MenuShow.Properties, event: ion.types.Event) -> bool:
        ion.app.menus.show(properties.idname)
        return True


# ---------------------------------------------------------------------------
# System operators
# ---------------------------------------------------------------------------


class _SystemShell(_Operator):
    __slots__ = ()

    idname = 'system_shell'
    description = 'Execute a shell command.'

    class Properties(NamedTuple):
        command: Annotated[str, 'Shell command to execute.']

    @staticmethod
    def name(properties: _SystemShell.Properties) -> str:
        return 'Execute'

    @staticmethod
    def exec(properties: _SystemShell.Properties, event: ion.types.Event) -> bool:
        ion.utils.shell(properties.command)
        return True


class _SystemExec(_Operator):
    __slots__ = ()

    idname = 'system_exec'
    description = 'Execute a command directly (no shell).'

    class Properties(NamedTuple):
        command: Annotated[tuple[str, ...], 'Program and arguments.']

    @staticmethod
    def name(properties: _SystemExec.Properties) -> str:
        return 'Execute'

    @staticmethod
    def exec(properties: _SystemExec.Properties, event: ion.types.Event) -> bool:
        ion.utils.exec(properties.command)
        return True


class _SystemNoop(_Operator):
    __slots__ = ()

    idname = 'system_noop'
    description = 'Do nothing. Useful for overriding bindings in higher-priority keymaps.'

    class Properties(NamedTuple):
        pass

    @staticmethod
    def name(properties: _SystemNoop.Properties) -> str:
        return 'No-op'

    @staticmethod
    def exec(properties: _SystemNoop.Properties, event: ion.types.Event) -> bool:
        return True


class _PythonExec(_Operator):
    __slots__ = ()

    idname = 'python_exec'
    description = 'Execute a Python script.'

    class Properties(NamedTuple):
        filepath: Annotated[str, 'Path to the Python file.']

    @staticmethod
    def name(properties: _PythonExec.Properties) -> str:
        import os
        return os.path.splitext(os.path.basename(properties.filepath))[0]

    @staticmethod
    def exec(properties: _PythonExec.Properties, event: ion.types.Event) -> bool:
        path = properties.filepath
        with open(path) as fh:
            code = compile(fh.read(), path, 'exec')
        exec(code, {'__file__': path, '__name__': '__main__'})  # noqa: S102
        return True


class _KeymapPrompt(_Operator):
    __slots__ = ()

    idname = 'keymap_prompt'
    description = 'Activate a keymap for the next key press (leader key).'

    class Properties(NamedTuple):
        name: Annotated[str, 'The keymap name.']

    @staticmethod
    def name(properties: _KeymapPrompt.Properties) -> str:
        return 'Keymap Prompt'

    @staticmethod
    def exec(properties: _KeymapPrompt.Properties, event: ion.types.Event) -> bool:
        ion.app.keymaps.prompt(properties.name)
        return True


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

# Every _Operator subclass defined above MUST be listed here.
# If you add a new operator class, add it to this list or it will not be registered.
#
# NOTE: this list could be collected by `_Operator.__init_subclass__`,
# however registration is kept explicit, so leave as-is.
_operators: list[type[_Operator]] = [
    _CompositorQuit,
    _CompositorLogout,
    _CompositorReload,
    _TagSet,
    _TagClear,
    _TagAttach,
    _WindowClose,
    _WindowKill,
    _FloatingDepthToFront,
    _FloatingDepthToBack,
    _FloatingRaise,
    _FloatingLower,
    _WindowFloatingSet,
    _WindowFullscreenSet,
    _WindowFullscreenAllSet,
    _FloatingMove,
    _FloatingResize,
    _FrameDelete,
    _FrameJoin,
    _TilingSplitAxisSet,
    _TilingSplitAxisRotate,
    _TilingSwap,
    _TilingDividerGaplessSet,
    _TilingResize,
    _FrameUntile,
    _TilingFloatingSplit,
    _FrameTile,
    _WorkspaceTileOnDesktop,
    _WorkspaceTileOnOutput,
    _WorkspaceUntile,
    _WorkspaceFloatingSet,
    _WindowWorkspacePush,
    _WindowWorkspacePop,
    _TilingFocusDirectional,
    _TilingOrientDirectional,
    _WindowTilingMoveDirectional,
    _TilingSplit,
    _WindowFocusLast,
    _WorkspaceNewFloating,
    _WorkspaceDelete,
    _WorkspaceNewTilingOnDesktop,
    _WorkspaceNewTilingOnOutput,
    _DesktopNew,
    _DesktopDelete,
    _FrameFocusCycle,
    _FrameTabIndexMove,
    _FrameTabCycle,
    _FrameTabNth,
    _OutputFocusDirectional,
    _OutputMoveDirectional,
    _DesktopFocusDirectional,
    _DesktopFocusCycle,
    _DesktopOverview,
    _DesktopOverviewConfirm,
    _DesktopOverviewCancel,
    _DesktopOverviewNavigate,
    _DesktopOverviewSelect,
    _WindowOverview,
    _WindowOverviewConfirm,
    _WindowOverviewCancel,
    _WindowOverviewNavigate,
    _WindowOverviewSelect,
    _WindowCycleCarousel,
    _WindowCarouselConfirm,
    _WindowCarouselCancel,
    _DesktopItemCycleCarousel,
    _DesktopItemCarouselConfirm,
    _DesktopItemCarouselCancel,
    _WindowSwitcher,
    _WindowSwitcherNext,
    _WindowSwitcherPrev,
    _WindowSwitcherCancel,
    _DesktopFocusOccupiedCycle,
    _DesktopFocusEmptyCycle,
    _MenuShow,
    _SystemShell,
    _SystemExec,
    _SystemNoop,
    _PythonExec,
    _KeymapPrompt,
    _FrameTabDrag,
    _FrameTabActivate,
    _TilingDividerResize,
]

# Keymaps for the modal operators above, which match the keymap their `keymap`
# property names. Created at startup and by `reset_defaults`, apart from
# operator registration.
keymap_names: tuple[str, ...] = (
    'window_switcher',
    'window_carousel',
    'desktop_item_carousel',
    'desktop_overview',
    'window_overview',
)


def register() -> None:
    """Register all built-in operators with `ion.ops`."""
    for cls in _operators:
        _class_register(cls)
