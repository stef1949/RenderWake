bl_info = {
    "name": "Keep Awake While Rendering",
    "author": "Richies3D Ltd",
    "version": (1, 2, 10),
    "blender": (4, 2, 0),
    "location": "Preferences > Add-ons > Keep Awake While Rendering",
    "description": "Prevents system sleep while Blender is rendering; allows sleep when not rendering.",
    "category": "System",
}

import bpy
import sys
import subprocess
import atexit


def _addon_idname() -> str:
    pkg = __package__ or __name__
    if pkg.endswith(".addon"):
        return pkg[:-len(".addon")]
    return pkg.split(".")[0]


# -----------------------------------------------------------------------------
# Platform wake lock implementations
# -----------------------------------------------------------------------------

class WakeLockBase:
    def acquire(self): ...
    def release(self): ...
    def is_active(self) -> bool: return False

class WakeLockWindows(WakeLockBase):
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    def __init__(self):
        self._active = False
        self._kernel32 = None
        try:
            import ctypes
            self._kernel32 = ctypes.windll.kernel32
        except Exception:
            self._kernel32 = None

    def acquire(self):
        if not self._kernel32:
            return
        self._kernel32.SetThreadExecutionState(self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED)
        self._active = True

    def release(self):
        if not self._kernel32:
            return
        self._kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
        self._active = False

    def is_active(self) -> bool:
        return self._active

class WakeLockMac(WakeLockBase):
    def __init__(self):
        self._proc = None

    def acquire(self):
        if self._proc and self._proc.poll() is None:
            return
        # -d prevents display sleep too; switch to -i if you only want system sleep prevention.
        self._proc = subprocess.Popen(["caffeinate", "-d"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def release(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._proc = None

    def is_active(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

class WakeLockLinux(WakeLockBase):
    def __init__(self):
        self._proc = None

    def _has_cmd(self, cmd: str) -> bool:
        from shutil import which
        return which(cmd) is not None

    def acquire(self):
        if self._proc and self._proc.poll() is None:
            return

        if self._has_cmd("systemd-inhibit"):
            self._proc = subprocess.Popen(
                ["systemd-inhibit", "--what=idle:sleep", "--why=Blender is rendering", "sleep", "infinity"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            self._proc = None

    def release(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._proc = None

    def is_active(self) -> bool:
        return self._proc is not None and self._proc.poll() is None


def make_wakelock() -> WakeLockBase:
    if sys.platform.startswith("win"):
        return WakeLockWindows()
    if sys.platform == "darwin":
        return WakeLockMac()
    return WakeLockLinux()

_wakelock = make_wakelock()

def _safe_get_prefs():
    try:
        addon = bpy.context.preferences.addons.get(_addon_idname())
        return addon.preferences if addon else None
    except Exception:
        return None

def _safe_has_statusbar_header() -> bool:
    # Blender versions may differ; guard the attribute.
    return hasattr(bpy.types, "STATUSBAR_HT_header")

def _safe_tag_redraw_statusbar():
    # Avoid crashes in headless/background render or during shutdown.
    try:
        wm = bpy.context.window_manager
        if wm is None:
            return
        for win in wm.windows:
            screen = getattr(win, "screen", None)
            if not screen:
                continue
            for area in screen.areas:
                if area.type == "STATUSBAR":
                    area.tag_redraw()
    except Exception:
        pass

def _safe_append_statusbar(draw_fn):
    if not _safe_has_statusbar_header():
        return
    try:
        bpy.types.STATUSBAR_HT_header.append(draw_fn)
    except Exception:
        pass

def _safe_remove_statusbar(draw_fn):
    if not _safe_has_statusbar_header():
        return
    try:
        bpy.types.STATUSBAR_HT_header.remove(draw_fn)
    except Exception:
        pass

def _safe_add_handler(handler_list, fn):
    try:
        if fn not in handler_list:
            handler_list.append(fn)
    except Exception:
        pass

def _safe_remove_handler(handler_list, fn):
    try:
        if fn in handler_list:
            handler_list.remove(fn)
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

def _prefs():
    return _safe_get_prefs()

def _log(msg: str):
    prefs = _prefs()
    if prefs and prefs.verbose:
        print(f"[KeepAwake] {msg}")

# -----------------------------------------------------------------------------
# Render handlers
# -----------------------------------------------------------------------------

def _acquire_if_enabled():
    prefs = _safe_get_prefs()
    if not prefs or not getattr(prefs, "enabled", False):
        return
    if not _wakelock.is_active():
        _wakelock.acquire()
        _log("Wake lock ACQUIRED (render started).")
    _safe_tag_redraw_statusbar()

def _release():
    if _wakelock.is_active():
        _wakelock.release()
        _log("Wake lock RELEASED (render ended).")
    _safe_tag_redraw_statusbar()


def on_render_pre(_scene, _depsgraph=None):
    _acquire_if_enabled()

def on_render_post(_scene, _depsgraph=None):
    _release()

def on_render_cancel(_scene, _depsgraph=None):
    _release()

# -----------------------------------------------------------------------------
# Status bar indicator
# -----------------------------------------------------------------------------

def draw_status_indicator(self, context):
    prefs = _safe_get_prefs()
    if not prefs or not getattr(prefs, "enabled", False) or not getattr(prefs, "show_indicator", True):
        return

    active = _wakelock.is_active()

    row = self.layout.row(align=True)
    row.separator(factor=0.8)

    # Uses Blender theme "alert" styling (often orange) when active
    row.alert = active

    icon = "LOCKED" if active else "UNLOCKED"
    text = "Awake: ON" if active else "Awake: OFF"
    row.label(text=text, icon=icon)


# -----------------------------------------------------------------------------
# Preferences UI
# -----------------------------------------------------------------------------

class KeepAwakePreferences(bpy.types.AddonPreferences):
    bl_idname = _addon_idname()

    enabled: bpy.props.BoolProperty = bpy.props.BoolProperty(
        name="Enable",
        default=True,
        description="Keep the device awake while rendering",
        update=lambda self, ctx: _safe_tag_redraw_statusbar(),
    )

    show_indicator: bpy.props.BoolProperty = bpy.props.BoolProperty(
        name="Show status indicator",
        default=True,
        description="Show Awake ON/OFF in Blender's status bar",
        update=lambda self, ctx: _safe_tag_redraw_statusbar(),
    )

    verbose: bpy.props.BoolProperty = bpy.props.BoolProperty(
        name="Verbose logging",
        default=False,
        description="Print acquire/release messages to the console",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "enabled")
        layout.prop(self, "show_indicator")
        layout.prop(self, "verbose")

        box = layout.box()
        box.label(text="Notes:")
        box.label(text="• Wake lock activates on render start and releases on render end/cancel.")
        if sys.platform == "darwin":
            box.label(text="• macOS uses 'caffeinate -d' (prevents display sleep too).")
        elif sys.platform.startswith("win"):
            box.label(text="• Windows uses SetThreadExecutionState.")
        else:
            box.label(text="• Linux tries 'systemd-inhibit' if available.")

# -----------------------------------------------------------------------------
# Register / Unregister
# -----------------------------------------------------------------------------

_classes = (
    KeepAwakePreferences,
)

def register():
    for c in _classes:
        bpy.utils.register_class(c)

    _safe_add_handler(bpy.app.handlers.render_pre, on_render_pre)
    _safe_add_handler(bpy.app.handlers.render_post, on_render_post)
    _safe_add_handler(bpy.app.handlers.render_cancel, on_render_cancel)

    _safe_append_statusbar(draw_status_indicator)

    atexit.register(_release)
    _safe_tag_redraw_statusbar()
    _log("Registered.")

def unregister():
    _release()

    _safe_remove_handler(bpy.app.handlers.render_pre, on_render_pre)
    _safe_remove_handler(bpy.app.handlers.render_post, on_render_post)
    _safe_remove_handler(bpy.app.handlers.render_cancel, on_render_cancel)

    _safe_remove_statusbar(draw_status_indicator)

    for c in reversed(_classes):
        bpy.utils.unregister_class(c)

    _safe_tag_redraw_statusbar()
    _log("Unregistered.")
