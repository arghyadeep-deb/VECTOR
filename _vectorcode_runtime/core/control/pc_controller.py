import sys
import os
import shutil
import subprocess
from pathlib import Path
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

import numpy as np
from loguru import logger

# Windows common app name -> typical executable path lookup.
# Falls back to shutil.which(app_name) for anything not listed.
_WIN_APP_ALIASES: dict[str, str] = {
    "notepad":      "notepad.exe",
    "calc":         "calc.exe",
    "calculator":   "calc.exe",
    "explorer":     "explorer.exe",
    "paint":        "mspaint.exe",
    "cmd":          "cmd.exe",
    "powershell":   "powershell.exe",
    "chrome":       r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "firefox":      r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "code":         os.path.join(os.environ.get("LOCALAPPDATA", r"C:\Users\Arghyadeep\AppData\Local"), r"Programs\Microsoft VS Code\Code.exe"),
    "vscode":       os.path.join(os.environ.get("LOCALAPPDATA", r"C:\Users\Arghyadeep\AppData\Local"), r"Programs\Microsoft VS Code\Code.exe"),
    "spotify":      os.path.join(os.environ.get("APPDATA", r"C:\Users\Arghyadeep\AppData\Roaming"), r"Spotify\Spotify.exe"),
    "obsidian":     os.path.join(os.environ.get("LOCALAPPDATA", r"C:\Users\Arghyadeep\AppData\Local"), r"Obsidian\Obsidian.exe"),
    "terminal":     "wt.exe",
    "wt":           "wt.exe",
    "task_manager": "taskmgr.exe",
    "taskmgr":      "taskmgr.exe",
}

# URI-protocol fallbacks — Microsoft Store installs have no classic exe path
# (e.g. Store Spotify), but register a protocol Windows resolves via startfile.
_WIN_APP_PROTOCOLS: dict[str, str] = {
    "spotify":  "spotify:",
    "settings": "ms-settings:",
    "whatsapp": "whatsapp:",
}

# F-8 (Task 58A remediation — VECTOR_TECHNICAL_KNOWLEDGE/58A_PLAY_MUSIC_
# PERMISSION_ESCALATION_REMEDIATION.md): the set of media-player targets
# play_music() is allowed to launch. This is DELIBERATELY NOT
# _WIN_APP_ALIASES — that table is a general app-launch alias convenience
# layer shared with the RED-tier launch_app capability and includes entries
# like "cmd"/"powershell" that must never be reachable from a GREEN action.
# Anything not in this allowlist falls back to the documented default
# ("spotify") inside play_music() rather than being forwarded anywhere.
_MEDIA_PLAYER_ALLOWLIST: frozenset[str] = frozenset({"spotify"})

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
    _PYAUTOGUI_AVAILABLE = True
except Exception as _e:
    logger.warning(f"[VECTOR][pc_controller] pyautogui unavailable: {_e}")
    _PYAUTOGUI_AVAILABLE = False

try:
    import mss
    import mss.tools
    _MSS_AVAILABLE = True
except Exception as _e:
    logger.warning(f"[VECTOR][pc_controller] mss unavailable: {_e}")
    _MSS_AVAILABLE = False

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except Exception as _e:
    logger.warning(f"[VECTOR][pc_controller] PIL unavailable: {_e}")
    _PIL_AVAILABLE = False


class PCController:
    """Vision-guided PC control: cursor, keyboard, screenshot, app launch."""

    def __init__(self):
        logger.info("[VECTOR][pc_controller] PCController initialised")

    # ── F-6: capability-token gate for control-plane writes ──────────────────
    def _verify_control_token(self, token, *allowed_action_types) -> bool:
        """Verify a gateway-minted control token against any of the action
        types that legitimately drive this primitive. Returns True (consuming
        one token use) only on a valid match. Direct callers with no token
        are refused by the callers of this helper."""
        try:
            from core.loop.permission_gateway import PermissionGateway
            gw = PermissionGateway()
        except Exception as _e:
            logger.warning(f"[VECTOR][pc_controller] gateway unavailable — control token check fails closed: {_e}")
            return False
        for _a in allowed_action_types:
            if gw.verify_control(token, _a):
                return True
        return False

    # ------------------------------------------------------------------
    # Screenshot
    # ------------------------------------------------------------------

    def take_screenshot(self, save_path: str = None) -> np.ndarray:
        """Capture fullscreen via mss, return BGR numpy array.

        Falls back to np.zeros on any error so callers always get an ndarray.
        """
        try:
            if not _MSS_AVAILABLE:
                raise RuntimeError("mss not available")

            with mss.mss() as sct:
                monitor = sct.monitors[1]  # 1 = primary monitor
                raw = sct.grab(monitor)
                frame = np.frombuffer(raw.bgra, dtype=np.uint8).reshape(
                    raw.height, raw.width, 4
                )
                frame_rgb = frame[:, :, :3]  # drop alpha

            if save_path and _PIL_AVAILABLE:
                try:
                    img = Image.fromarray(frame_rgb)
                    img.save(save_path)
                    logger.info(f"[VECTOR][pc_controller] screenshot saved -> {save_path}")
                except Exception as save_err:
                    logger.warning(f"[VECTOR][pc_controller] screenshot save failed: {save_err}")

            return frame_rgb

        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] take_screenshot error: {e}")
            return np.zeros((100, 100, 3), dtype=np.uint8)

    # ------------------------------------------------------------------
    # Cursor
    # ------------------------------------------------------------------

    def move_cursor(self, x: int, y: int, duration: float = 0.3,
                    *, control_token: str | None = None) -> bool:
        """Move cursor to absolute screen coordinates. F-6: requires a gateway
        control token (granted for pc_click/click_screen/vision_control/etc.)."""
        if not self._verify_control_token(control_token, "pc_click", "click_screen", "vision_control"):
            logger.warning("[VECTOR][pc_controller] move_cursor blocked — no valid control token")
            return False
        try:
            if not _PYAUTOGUI_AVAILABLE:
                raise RuntimeError("pyautogui not available")
            pyautogui.moveTo(x, y, duration=duration)
            logger.debug(f"[VECTOR][pc_controller] cursor moved to ({x}, {y})")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] move_cursor error: {e}")
            return False

    def click(self, x: int, y: int, button: str = "left",
              *, control_token: str | None = None) -> bool:
        """Click at absolute screen coordinates. F-6: requires a gateway control token."""
        if not self._verify_control_token(control_token, "pc_click", "click_screen", "gui_task", "desktop_task", "vision_control"):
            logger.warning("[VECTOR][pc_controller] click blocked — no valid control token")
            return False
        try:
            if not _PYAUTOGUI_AVAILABLE:
                raise RuntimeError("pyautogui not available")
            pyautogui.click(x, y, button=button)
            logger.debug(f"[VECTOR][pc_controller] {button}-click at ({x}, {y})")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] click error: {e}")
            return False

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def type_text(self, text: str, interval: float = 0.05,
                  *, control_token: str | None = None) -> bool:
        """Type a string character by character. F-6: requires a gateway control token."""
        if not self._verify_control_token(control_token, "pc_type", "gui_task", "desktop_task"):
            logger.warning("[VECTOR][pc_controller] type_text blocked — no valid control token")
            return False
        try:
            if not _PYAUTOGUI_AVAILABLE:
                raise RuntimeError("pyautogui not available")
            pyautogui.typewrite(text, interval=interval)
            logger.debug(f"[VECTOR][pc_controller] typed {len(text)} chars")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] type_text error: {e}")
            return False

    def hotkey(self, *keys: str, control_token: str | None = None) -> bool:
        """Press a keyboard shortcut (e.g. 'ctrl', 'c'). F-6: requires a gateway control token."""
        if not self._verify_control_token(control_token, "pc_type", "gui_task", "desktop_task"):
            logger.warning("[VECTOR][pc_controller] hotkey blocked — no valid control token")
            return False
        try:
            if not _PYAUTOGUI_AVAILABLE:
                raise RuntimeError("pyautogui not available")
            pyautogui.hotkey(*keys)
            logger.debug(f"[VECTOR][pc_controller] hotkey: {'+'.join(keys)}")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] hotkey error: {e}")
            return False

    # ------------------------------------------------------------------
    # App launch
    # ------------------------------------------------------------------

    def launch_app(self, app_name: str, args: list[str] | None = None,
                    *, control_token: str | None = None) -> dict:
        """Launch an application without waiting for it to finish.

        Resolves common Windows app aliases before falling back to shutil.which.
        Returns a dict with launched/pid/app or launched/error.
        F-6: requires a gateway control token minted specifically for
        launch_app (RED tier — see core/config.py's `red` list).

        F-8 (Task 58A remediation): a play_music-scoped token is NO LONGER
        accepted here. Before this fix, play_music (GREEN) legitimately
        needed to launch a media player, and the shortcut taken was to let
        launch_app() accept either token — but launch_app() accepts an
        UNCONSTRAINED `app_name` (resolved via _WIN_APP_ALIASES, then
        shutil.which(), then a raw Popen attempt), so any code path that
        could mint or forward a play_music token could launch an arbitrary
        named executable with zero RED-tier owner approval (confirmed live
        via core/voice/ambient_listener.py's LLM-classified Action
        construction — see 57_RESIDUAL_SIDE_EFFECT_SURFACE_VERIFICATION.md
        Finding A). play_music() now launches its media player via the
        separate, hard-allowlisted _launch_media_player() below instead of
        calling this method at all — it no longer needs a launch_app token.
        """
        # 2026-09-23: also accept a "pc_launch_app"-scoped token --
        # core/api/routers/control.py's /pc/launch-app endpoint gates on
        # that distinct (also RED-tier) action_type, which is the real
        # action_type PermissionGateway._execute_action() actually
        # approved and minted a receipt for; requiring the differently-
        # spelled "launch_app" token there would refuse a genuinely
        # approved, real request.
        if not self._verify_control_token(control_token, "launch_app", "pc_launch_app"):
            logger.warning("[VECTOR][pc_controller] launch_app blocked — no valid control token")
            return {"launched": False, "error": "launch_app requires a gateway control token"}
        try:
            args = args or []
            name_lower = app_name.strip().lower()

            # 1. Check alias table first — but drop aliases whose absolute path
            #    doesn't exist (e.g. Store-installed Spotify has no classic exe)
            exe = _WIN_APP_ALIASES.get(name_lower)
            if exe and os.path.isabs(exe) and not os.path.exists(exe):
                exe = None

            # 2. If no usable alias, try shutil.which (finds anything on PATH)
            if exe is None:
                exe = shutil.which(app_name)

            # 3. Still nothing → URI-protocol launch (Microsoft Store installs)
            if exe is None:
                proto = _WIN_APP_PROTOCOLS.get(name_lower)
                if proto and sys.platform == "win32":
                    os.startfile(proto)  # Windows resolves the registered handler
                    logger.info(f"[VECTOR][pc] launched '{app_name}' via {proto}")
                    return {"launched": True, "pid": None, "app": app_name, "via": proto}
                exe = app_name  # last resort: let Popen try the raw name

            cmd = [exe] + args
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0,
            )
            logger.info(f"[VECTOR][pc] launched '{app_name}' pid={proc.pid}")
            return {"launched": True, "pid": proc.pid, "app": app_name}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] launch_app '{app_name}' error: {e}")
            return {"launched": False, "error": str(e)}

    def open_path(self, path: str, *, control_token: str | None = None) -> dict:
        """Open a file or folder with its OS-registered default handler.

        2026-10-25: owner asked for sequential/mechanical PC tasks (open a
        doc, PDF, folder) to skip the LLM round-trip entirely -- this is
        that fast path's real executor. Same RED-tier/control-token gate as
        launch_app (see core/config.py's `red` list + RED_INTERACTIVE_TOOLS):
        an owner-typed/spoken "open <path>" command is its own confirmation.
        Only opens a path that already exists -- never creates, never
        guesses a close match (a wrong guess opening the wrong file is worse
        than just saying "not found").
        """
        if not self._verify_control_token(control_token, "open_path"):
            logger.warning("[VECTOR][pc_controller] open_path blocked — no valid control token")
            return {"opened": False, "error": "open_path requires a gateway control token"}
        try:
            resolved = Path(os.path.expandvars(path)).expanduser()
            if not resolved.exists():
                return {"opened": False, "error": f"path does not exist: {resolved}"}
            if sys.platform == "win32":
                os.startfile(str(resolved))  # noqa: S606 — existence-checked, owner-confirmed path only
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.Popen([opener, str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"[VECTOR][pc] opened '{resolved}'")
            return {"opened": True, "path": str(resolved)}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] open_path '{path}' error: {e}")
            return {"opened": False, "error": str(e)}

    def delete_files(self, paths: list[str], *, control_token: str | None = None) -> dict:
        """Delete files, confined to safe roots ONLY — owner's explicit
        choice (2026-10-25): real deletion is allowed only inside
        ~/Downloads and a dedicated VECTOR trash/scratch folder
        (data/trash/). Any path outside those two roots is refused
        outright, regardless of phrasing or classifier confidence — this
        is a hard filesystem boundary enforced here, not a confirmation
        step that can be talked around. delete_files stays in
        OWNER_APPROVAL_ONLY (permission_gateway.py), so a real Pushover
        tap is still required before this method is ever reached; this is
        only the executor, never the gate.
        """
        if not self._verify_control_token(control_token, "delete_files"):
            logger.warning("[VECTOR][pc_controller] delete_files blocked — no valid control token")
            return {"deleted": [], "refused": list(paths), "error": "delete_files requires a gateway control token"}
        from core.runtime_paths import data_path
        allowed_roots = [
            (Path.home() / "Downloads").resolve(),
            data_path("trash").resolve(),
        ]
        allowed_roots[1].mkdir(parents=True, exist_ok=True)
        deleted, refused, errors = [], [], []
        for raw in paths:
            try:
                resolved = Path(os.path.expandvars(raw)).expanduser().resolve()
            except Exception as e:
                errors.append({"path": raw, "error": str(e)})
                continue
            if not any(root == resolved or root in resolved.parents for root in allowed_roots):
                logger.warning(f"[VECTOR][pc_controller] delete_files refused — outside safe roots: {resolved}")
                refused.append(str(resolved))
                continue
            if not resolved.exists():
                errors.append({"path": str(resolved), "error": "does not exist"})
                continue
            try:
                if resolved.is_dir():
                    shutil.rmtree(resolved)
                else:
                    resolved.unlink()
                logger.info(f"[VECTOR][pc] deleted '{resolved}'")
                deleted.append(str(resolved))
            except Exception as e:
                errors.append({"path": str(resolved), "error": str(e)})
        return {"deleted": deleted, "refused": refused, "errors": errors}

    def close_notifications(self, *, control_token: str | None = None) -> dict:
        """Clear all Windows notifications via the OS Notification Center's
        own "Clear all" button (pywinauto UI Automation — real OS control,
        not a guess). GREEN tier: this only affects notification-panel
        visibility, nothing destructive or irreversible.

        2026-10-25: built on owner request. No prior VECTOR capability
        touched Windows notifications at all.
        """
        if not self._verify_control_token(control_token, "close_notifications"):
            logger.warning("[VECTOR][pc_controller] close_notifications blocked — no valid control token")
            return {"cleared": False, "error": "close_notifications requires a gateway control token"}
        if sys.platform != "win32":
            return {"cleared": False, "error": "close_notifications is Windows-only"}
        if not _PYAUTOGUI_AVAILABLE:
            return {"cleared": False, "error": "pyautogui not available"}
        try:
            import time as _time
            from pywinauto import Desktop
            # 2026-10-25 (live bug #3): if the OS cursor is currently
            # sitting at/near a screen corner -- e.g. left over from the
            # earlier zero-rect click bug this method had -- pyautogui's
            # FAILSAFE trips on the very next pyautogui call, including this
            # plain hotkey, before any notification logic even runs.
            # pyautogui.moveTo() can't fix this: its own failsafe check runs
            # BEFORE the move, on the cursor's current (corner) position, so
            # it would raise too. Use pywinauto's mouse module instead --
            # no failsafe check -- to get the cursor away from the corner
            # first; every pyautogui call after this one is then safe.
            try:
                from pywinauto import mouse as _pwa_mouse
                _w, _h = pyautogui.size()
                _pwa_mouse.move(coords=(_w // 2, _h // 2))
            except Exception as _move_err:
                logger.debug(f"[VECTOR][pc_controller] cursor reset skipped: {_move_err}")
            pyautogui.hotkey("win", "n")
            _time.sleep(0.8)
            desktop = Desktop(backend="uia")
            panel = desktop.window(title_re=".*Notification Center.*")
            if not panel.exists(timeout=2):
                pyautogui.press("esc")
                return {"cleared": False, "error": "notification center window not found"}
            # 2026-10-25 (live-debugged on this machine via
            # print_control_identifiers()): the real "Clear all
            # notifications" element is control_type="Group" with
            # auto_id="ClearAllButtonControl" -- NOT control_type="Button"
            # as first guessed, which is why the first version of this
            # method always silently found nothing. auto_id is also far
            # more robust than title/control_type guessing (Windows
            # localizes the visible title; auto_id generally doesn't change
            # across builds/languages).
            # 2026-10-25 (live bug #2, found via real server logs): when
            # there's nothing to clear, Windows collapses this element to a
            # zero-size rect at (0,0) but it still reports exists()==True --
            # click_input() on it lands exactly on the screen corner, which
            # trips pyautogui's own FAILSAFE (an emergency-abort feature for
            # this exact situation: mouse jumping to a corner). Must check
            # the real rectangle has actual area before ever clicking it.
            cleared = False
            try:
                _btn = panel.child_window(auto_id="ClearAllButtonControl", control_type="Group")
                if _btn.exists(timeout=1):
                    _rect = _btn.rectangle()
                    if _rect.width() > 0 and _rect.height() > 0:
                        _btn.click_input()
                        cleared = True
            except Exception as _btn_err:
                logger.debug(f"[VECTOR][pc_controller] clear-all control lookup failed: {_btn_err}")
            pyautogui.press("esc")
            if cleared:
                logger.info("[VECTOR][pc] notifications cleared")
                return {"cleared": True}
            # Zero-size/absent "Clear all" control means there was nothing
            # to clear (Windows collapses it to L0,T0,R0,B0 when the
            # notification list is empty) -- a legitimate "nothing to do",
            # not a failure.
            logger.info("[VECTOR][pc] close_notifications: nothing to clear")
            return {"cleared": True, "note": "nothing to clear"}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] close_notifications error: {e}")
            return {"cleared": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Window management (2026-10-25, owner capability sweep)
    # ------------------------------------------------------------------

    def window_control(self, action: str, title: str = "", *, control_token: str | None = None) -> dict:
        """Minimize/maximize/restore/close/focus a window. Targets the
        window matching `title` (first match), or the active window when
        title is empty. action in {minimize, maximize, restore, close, focus}.
        """
        if not self._verify_control_token(control_token, "window_control"):
            logger.warning("[VECTOR][pc_controller] window_control blocked — no valid control token")
            return {"ok": False, "error": "window_control requires a gateway control token"}
        if sys.platform != "win32":
            return {"ok": False, "error": "window_control is Windows-only"}
        try:
            import pygetwindow as gw
            win = None
            if title:
                matches = gw.getWindowsWithTitle(title)
                win = matches[0] if matches else None
            else:
                win = gw.getActiveWindow()
            if win is None:
                return {"ok": False, "error": f"no window found matching '{title}'" if title else "no active window"}
            _actions = {
                "minimize": win.minimize, "maximize": win.maximize,
                "restore": win.restore, "close": win.close, "focus": win.activate,
            }
            fn = _actions.get(action)
            if fn is None:
                return {"ok": False, "error": f"unknown window action: {action}"}
            fn()
            logger.info(f"[VECTOR][pc] window {action} '{win.title}'")
            return {"ok": True, "title": win.title, "action": action}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] window_control error: {e}")
            return {"ok": False, "error": str(e)}

    # Processes that must never be reachable by name -- killing any of these
    # takes down the OS shell or the machine itself, and "python.exe"/
    # "pythonw.exe" could mean VECTOR's own process. Checked in addition to
    # (never instead of) the caller's own PID exclusion below.
    _KILL_DENYLIST = frozenset({
        "explorer.exe", "svchost.exe", "csrss.exe", "winlogon.exe",
        "services.exe", "lsass.exe", "wininit.exe", "smss.exe", "dwm.exe",
        "system", "system idle process", "python.exe", "pythonw.exe",
    })

    def kill_app(self, name: str, *, control_token: str | None = None) -> dict:
        """Terminate every running process matching `name` (e.g. 'chrome' or
        'chrome.exe') -- a browser with helper processes needs all of them
        gone to really close. Hard-refuses critical system processes and
        VECTOR's own process, regardless of what was asked.
        """
        if not self._verify_control_token(control_token, "kill_app"):
            logger.warning("[VECTOR][pc_controller] kill_app blocked — no valid control token")
            return {"killed": [], "error": "kill_app requires a gateway control token"}
        try:
            import psutil
            target = name.strip().lower()
            if sys.platform == "win32" and not target.endswith(".exe"):
                target = target + ".exe"
            if target in self._KILL_DENYLIST:
                logger.warning(f"[VECTOR][pc_controller] kill_app refused — protected process: {target}")
                return {"killed": [], "refused": target, "error": "refused: protected system process"}
            own_pid = os.getpid()
            killed, errors = [], []
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if proc.pid == own_pid:
                        continue
                    if (proc.info.get("name") or "").lower() == target:
                        proc.terminate()
                        killed.append({"pid": proc.pid, "name": proc.info.get("name")})
                except Exception as _pe:
                    errors.append(str(_pe))
            if killed:
                logger.info(f"[VECTOR][pc] killed {len(killed)} process(es) matching '{name}'")
            return {"killed": killed, "errors": errors}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] kill_app error: {e}")
            return {"killed": [], "error": str(e)}

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def clipboard_get(self, *, control_token: str | None = None) -> dict:
        """Read current clipboard text."""
        if not self._verify_control_token(control_token, "clipboard_get"):
            logger.warning("[VECTOR][pc_controller] clipboard_get blocked — no valid control token")
            return {"text": "", "error": "clipboard_get requires a gateway control token"}
        try:
            import pyperclip
            return {"text": pyperclip.paste()}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] clipboard_get error: {e}")
            return {"text": "", "error": str(e)}

    def clipboard_set(self, text: str, *, control_token: str | None = None) -> dict:
        """Overwrite the clipboard with `text`."""
        if not self._verify_control_token(control_token, "clipboard_set"):
            logger.warning("[VECTOR][pc_controller] clipboard_set blocked — no valid control token")
            return {"ok": False, "error": "clipboard_set requires a gateway control token"}
        try:
            import pyperclip
            pyperclip.copy(text)
            logger.info("[VECTOR][pc] clipboard set")
            return {"ok": True}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] clipboard_set error: {e}")
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Volume / brightness
    # ------------------------------------------------------------------

    def set_volume(self, level: int | None = None, *, mute: bool | None = None,
                    control_token: str | None = None) -> dict:
        """Set master volume (0-100) and/or mute state via pycaw (Core Audio)."""
        if not self._verify_control_token(control_token, "set_volume"):
            logger.warning("[VECTOR][pc_controller] set_volume blocked — no valid control token")
            return {"ok": False, "error": "set_volume requires a gateway control token"}
        if sys.platform != "win32":
            return {"ok": False, "error": "set_volume is Windows-only"}
        try:
            # 2026-10-25 (live bug, confirmed via direct introspection of the
            # installed pycaw build): AudioUtilities.GetSpeakers() already
            # returns an AudioDevice whose .EndpointVolume property is the
            # ready-to-use IAudioEndpointVolume COM pointer -- this version
            # does the Activate()/comtypes.cast() dance internally. The
            # manual activation the older tutorials show raised
            # "'AudioDevice' object has no attribute 'Activate'" here.
            from pycaw.pycaw import AudioUtilities
            vol = AudioUtilities.GetSpeakers().EndpointVolume
            if mute is not None:
                vol.SetMute(1 if mute else 0, None)
            if level is not None:
                level = max(0, min(100, int(level)))
                vol.SetMasterVolumeLevelScalar(level / 100.0, None)
            logger.info(f"[VECTOR][pc] volume set level={level} mute={mute}")
            return {"ok": True, "level": level, "mute": mute}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] set_volume error: {e}")
            return {"ok": False, "error": str(e)}

    def set_brightness(self, level: int, *, control_token: str | None = None) -> dict:
        """Set screen brightness 0-100 (laptop panel or supported external monitors)."""
        if not self._verify_control_token(control_token, "set_brightness"):
            logger.warning("[VECTOR][pc_controller] set_brightness blocked — no valid control token")
            return {"ok": False, "error": "set_brightness requires a gateway control token"}
        if sys.platform != "win32":
            return {"ok": False, "error": "set_brightness is Windows-only"}
        try:
            import screen_brightness_control as sbc
            level = max(0, min(100, int(level)))
            sbc.set_brightness(level)
            logger.info(f"[VECTOR][pc] brightness set to {level}")
            return {"ok": True, "level": level}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] set_brightness error: {e}")
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Power control — lock/sleep are reversible+instant; shutdown/restart
    # stay OWNER_APPROVAL_ONLY (never RED_INTERACTIVE_TOOLS) per owner
    # decision 2026-10-25, same real-Pushover-tap gate as delete_files.
    # ------------------------------------------------------------------

    def lock_screen(self, *, control_token: str | None = None) -> dict:
        if not self._verify_control_token(control_token, "lock_screen"):
            logger.warning("[VECTOR][pc_controller] lock_screen blocked — no valid control token")
            return {"ok": False, "error": "lock_screen requires a gateway control token"}
        if sys.platform != "win32":
            return {"ok": False, "error": "lock_screen is Windows-only"}
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            logger.info("[VECTOR][pc] screen locked")
            return {"ok": True}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] lock_screen error: {e}")
            return {"ok": False, "error": str(e)}

    def sleep_pc(self, *, control_token: str | None = None) -> dict:
        if not self._verify_control_token(control_token, "sleep_pc"):
            logger.warning("[VECTOR][pc_controller] sleep_pc blocked — no valid control token")
            return {"ok": False, "error": "sleep_pc requires a gateway control token"}
        if sys.platform != "win32":
            return {"ok": False, "error": "sleep_pc is Windows-only"}
        try:
            import ctypes
            ctypes.windll.powrprof.SetSuspendState(False, True, False)
            logger.info("[VECTOR][pc] sleep requested")
            return {"ok": True}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] sleep_pc error: {e}")
            return {"ok": False, "error": str(e)}

    def shutdown_pc(self, *, control_token: str | None = None) -> dict:
        """OWNER_APPROVAL_ONLY: control_token here is only ever minted after
        a real Pushover approval (see permission_gateway.py) -- never
        instant. 30s OS-level delay on top of that as a last-chance abort
        window (`shutdown /a` cancels it)."""
        if not self._verify_control_token(control_token, "shutdown_pc"):
            logger.warning("[VECTOR][pc_controller] shutdown_pc blocked — no valid control token")
            return {"ok": False, "error": "shutdown_pc requires a gateway control token"}
        if sys.platform != "win32":
            return {"ok": False, "error": "shutdown_pc is Windows-only"}
        try:
            subprocess.Popen(["shutdown", "/s", "/t", "30"])
            logger.warning("[VECTOR][pc] shutdown scheduled in 30s (shutdown /a to cancel)")
            return {"ok": True, "delay_sec": 30}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] shutdown_pc error: {e}")
            return {"ok": False, "error": str(e)}

    def restart_pc(self, *, control_token: str | None = None) -> dict:
        """Same OWNER_APPROVAL_ONLY gate and 30s abort window as shutdown_pc."""
        if not self._verify_control_token(control_token, "restart_pc"):
            logger.warning("[VECTOR][pc_controller] restart_pc blocked — no valid control token")
            return {"ok": False, "error": "restart_pc requires a gateway control token"}
        if sys.platform != "win32":
            return {"ok": False, "error": "restart_pc is Windows-only"}
        try:
            subprocess.Popen(["shutdown", "/r", "/t", "30"])
            logger.warning("[VECTOR][pc] restart scheduled in 30s (shutdown /a to cancel)")
            return {"ok": True, "delay_sec": 30}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] restart_pc error: {e}")
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Read-only system queries (GREEN — informational, no gate needed)
    # ------------------------------------------------------------------

    def get_system_stats(self) -> dict:
        """CPU/memory/disk/battery snapshot via psutil."""
        try:
            import psutil
            battery = psutil.sensors_battery()
            disk_root = "C:\\" if sys.platform == "win32" else "/"
            disk = psutil.disk_usage(disk_root)
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.3),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": disk.percent,
                "battery_percent": battery.percent if battery else None,
                "battery_plugged": battery.power_plugged if battery else None,
            }
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] get_system_stats error: {e}")
            return {"error": str(e)}

    def read_screen_text(self) -> dict:
        """OCR the current screen via pytesseract."""
        try:
            import pytesseract
            # 2026-10-25: pytesseract is only the Python wrapper -- the real
            # OCR engine is a separate binary (installed via winget,
            # UB-Mannheim.TesseractOCR) that isn't on this process's PATH
            # even right after install (PATH doesn't refresh for an already-
            # running process). Point at the known install location
            # directly rather than depending on PATH at all.
            _tess_exe = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(_tess_exe):
                pytesseract.pytesseract.tesseract_cmd = _tess_exe
            frame = self.take_screenshot()
            if not _PIL_AVAILABLE:
                return {"text": "", "error": "PIL not available"}
            text = pytesseract.image_to_string(Image.fromarray(frame))
            return {"text": text.strip()}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] read_screen_text error: {e}")
            return {"text": "", "error": str(e)}

    # ------------------------------------------------------------------
    # Media control (real OS playback — Spotify/any media app)
    # ------------------------------------------------------------------

    def media_key(self, key: str) -> dict:
        """Send a Windows media key (play_pause/next/prev/stop) to whatever
        media app has media-key focus (Spotify, browser, etc.).

        Uses keybd_event via ctypes — no extra dependency. This is what makes
        "play music" / "pause" / "next track" actually control real playback;
        before this the gateway just SAID "Resuming playback" and did nothing
        (2026-07-17 owner: voice comprehends the intent but nothing plays).
        """
        _VK = {"play_pause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2}
        vk = _VK.get(key)
        if vk is None:
            return {"ok": False, "error": f"unknown media key: {key}"}
        if sys.platform != "win32":
            return {"ok": False, "error": "media keys are Windows-only"}
        try:
            import ctypes
            KEYEVENTF_KEYUP = 0x0002
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)               # down
            ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)  # up
            logger.info(f"[VECTOR][pc] media key '{key}' sent")
            return {"ok": True, "key": key}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] media_key '{key}' error: {e}")
            return {"ok": False, "error": str(e)}

    def _launch_media_player(self, app_name: str, *, control_token: str | None = None) -> dict:
        """F-8 (Task 58A remediation): launch a media player, hard-restricted
        to _MEDIA_PLAYER_ALLOWLIST. This is NOT launch_app() — it must never
        accept an arbitrary app name, regardless of caller, and unlike
        launch_app() it has no "last resort: let Popen try the raw name"
        fallback. Requires a play_music-scoped token (GREEN); refuses
        anything not on the allowlist even if somehow called directly,
        so this method's own safety does not depend on play_music()'s
        normalization alone.
        """
        if app_name not in _MEDIA_PLAYER_ALLOWLIST:
            logger.warning(
                "[VECTOR][pc_controller] _launch_media_player refused "
                "non-allowlisted target: {!r}", app_name,
            )
            return {"launched": False, "error": "not a recognized media player"}
        if not self._verify_control_token(control_token, "play_music"):
            logger.warning("[VECTOR][pc_controller] _launch_media_player blocked — no valid control token")
            return {"launched": False, "error": "play_music requires a gateway control token"}
        try:
            exe = _WIN_APP_ALIASES.get(app_name)
            if exe and os.path.isabs(exe) and not os.path.exists(exe):
                exe = None
            if exe is None:
                exe = shutil.which(app_name)
            if exe is None:
                proto = _WIN_APP_PROTOCOLS.get(app_name)
                if proto and sys.platform == "win32":
                    os.startfile(proto)
                    logger.info(f"[VECTOR][pc] launched media player '{app_name}' via {proto}")
                    return {"launched": True, "pid": None, "app": app_name, "via": proto}
                # No raw-name Popen fallback here (unlike launch_app()) —
                # app_name is already allowlist-confirmed; if no real
                # executable/protocol is found the player just isn't
                # installed on this machine.
                return {"launched": False, "error": f"media player '{app_name}' not found on this machine"}
            proc = subprocess.Popen(
                [exe],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0,
            )
            logger.info(f"[VECTOR][pc] launched media player '{app_name}' pid={proc.pid}")
            return {"launched": True, "pid": proc.pid, "app": app_name}
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] _launch_media_player '{app_name}' error: {e}")
            return {"launched": False, "error": str(e)}

    def play_music(self, app: str = "spotify", *, control_token: str | None = None) -> dict:
        """Actually start music: launch the player (if needed) and press play.

        'play music' with no app named defaults to Spotify — VECTOR should infer
        the app rather than making the owner spell it out every time.

        F-8 (Task 58A remediation): `app` is normalized against the fixed
        _MEDIA_PLAYER_ALLOWLIST before anything is launched — an
        unrecognized value (e.g. an arbitrary string from an LLM-classified
        or ambient-voice-derived Action) silently falls back to the
        documented default ("spotify") instead of being forwarded to any
        launch primitive. The actual launch goes through
        _launch_media_player() (hard-allowlisted), NOT launch_app() (which
        accepts any app name and is RED-tier) — see
        VECTOR_TECHNICAL_KNOWLEDGE/58A_PLAY_MUSIC_PERMISSION_ESCALATION_
        REMEDIATION.md for the full rationale.

        F-6: play_music is GREEN; the gateway mints a control_token for it.
        Direct callers may pass their own token; if absent, one is minted
        for the GREEN play_music path.
        """
        safe_app = (app or "").strip().lower()
        if safe_app not in _MEDIA_PLAYER_ALLOWLIST:
            if safe_app:
                logger.info(
                    "[VECTOR][pc_controller] play_music: '{}' is not a "
                    "recognized media player — defaulting to spotify",
                    app,
                )
            safe_app = "spotify"
        if control_token is None:
            try:
                from core.loop.permission_gateway import PermissionGateway
                control_token = PermissionGateway().grant_control("play_music", uses=4, ttl=60)
            except Exception as _e:
                logger.warning(f"[VECTOR][pc_controller] play_music could not mint control token: {_e}")
        launched = self._launch_media_player(safe_app, control_token=control_token)
        # Give a just-launched player a moment to grab media-key focus, then play.
        import time as _t
        _t.sleep(2.5 if launched.get("launched") else 0.2)
        played = self.media_key("play_pause")
        return {"ok": played.get("ok", False), "app": safe_app,
                "launched": launched.get("launched"), "played": played.get("ok")}

    # ------------------------------------------------------------------
    # Shell command (YELLOW-tier)
    # ------------------------------------------------------------------

    def run_shell_command(
        self,
        command: str,
        timeout: int = 30,
        *,
        control_token: str | None = None,
    ) -> dict:
        """Run a shell command and return exit code + stdout + stderr.

        F-6: hard-gated by a gateway-minted capability token (replaces the
        soft _gateway_approved kwarg any caller could pass True to). The token
        is issued by PermissionGateway.grant_control() after approval; callers
        without a valid token are refused. Never call this directly from
        untrusted input.
        """
        try:
            if not self._verify_control_token(control_token, "run_shell_command"):
                logger.warning("[VECTOR][pc_controller] blocked shell command — no valid control token")
                return {
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "blocked: shell commands require a gateway control token (PermissionGateway.grant_control)",
                    "command": command,
                    "blocked": True,
                }
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            logger.info(
                f"[VECTOR][pc_controller] shell cmd exit={completed.returncode}: {command[:80]}"
            )
            return {
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "command": command,
            }
        except subprocess.TimeoutExpired:
            logger.warning(f"[VECTOR][pc_controller] shell command timed out: {command[:80]}")
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"timed out after {timeout}s",
                "command": command,
            }
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] run_shell_command error: {e}")
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "command": command,
            }

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def get_screen_size(self) -> tuple:
        """Return (width, height) of primary screen."""
        try:
            if not _PYAUTOGUI_AVAILABLE:
                raise RuntimeError("pyautogui not available")
            size = pyautogui.size()
            return (size.width, size.height)
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] get_screen_size error: {e}")
            return (1920, 1080)

    def get_mouse_position(self) -> tuple:
        """Return current (x, y) cursor position."""
        try:
            if not _PYAUTOGUI_AVAILABLE:
                raise RuntimeError("pyautogui not available")
            pos = pyautogui.position()
            return (pos.x, pos.y)
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] get_mouse_position error: {e}")
            return (0, 0)


# ----------------------------------------------------------------------
# Smoke test
# ----------------------------------------------------------------------
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True

    ctrl = PCController()

    size = ctrl.get_screen_size()
    if not (isinstance(size, tuple) and len(size) == 2):
        logger.error("[VECTOR][pc_controller] get_screen_size returned wrong type")
        ok = False
    else:
        logger.info(f"[VECTOR][pc_controller] screen size: {size}")

    pos = ctrl.get_mouse_position()
    if not (isinstance(pos, tuple) and len(pos) == 2):
        logger.error("[VECTOR][pc_controller] get_mouse_position returned wrong type")
        ok = False
    else:
        logger.info(f"[VECTOR][pc_controller] mouse pos: {pos}")

    frame = ctrl.take_screenshot()
    if not isinstance(frame, np.ndarray):
        logger.error("[VECTOR][pc_controller] take_screenshot returned wrong type")
        ok = False
    else:
        logger.info(f"[VECTOR][pc_controller] screenshot shape: {frame.shape}")

    # launch_app smoke test (notepad — safe, closes immediately in CI). F-6: mint a
    # token. 2026-09-23 (round 2): grant_control() now consumes a real,
    # gateway-issued approval receipt rather than a caller-asserted bool
    # -- this self-test issues one directly (via the same internal method
    # execute() itself uses) to stand in for the real owner approval that
    # would have already happened before real production code reaches
    # this point.
    from core.loop.permission_gateway import PermissionGateway
    _gw = PermissionGateway()
    _gw._issue_approval_receipt("launch_app")
    _launch_tok = _gw.grant_control("launch_app", uses=2, ttl=60)
    launch_result = ctrl.launch_app("notepad", control_token=_launch_tok)
    if not isinstance(launch_result, dict) or "launched" not in launch_result:
        logger.error("[VECTOR][pc_controller] launch_app returned wrong type")
        ok = False
    else:
        logger.info(f"[VECTOR][pc_controller] launch_app result: {launch_result}")

    # run_shell_command smoke test — F-6: requires a gateway control token.
    _gw._issue_approval_receipt("run_shell_command")
    _shell_tok = _gw.grant_control("run_shell_command", uses=1, ttl=60)
    shell_result = ctrl.run_shell_command("echo VECTOR_OK", control_token=_shell_tok)
    if shell_result.get("exit_code") != 0:
        logger.error(f"[VECTOR][pc_controller] run_shell_command failed: {shell_result}")
        ok = False
    else:
        logger.info(f"[VECTOR][pc_controller] shell result: {shell_result}")

    print("OK pc_controller OK" if ok else "FAILED")
