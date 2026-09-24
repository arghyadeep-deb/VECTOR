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
