import sys
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

    def move_cursor(self, x: int, y: int, duration: float = 0.3) -> bool:
        """Move cursor to absolute screen coordinates."""
        try:
            if not _PYAUTOGUI_AVAILABLE:
                raise RuntimeError("pyautogui not available")
            pyautogui.moveTo(x, y, duration=duration)
            logger.debug(f"[VECTOR][pc_controller] cursor moved to ({x}, {y})")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] move_cursor error: {e}")
            return False

    def click(self, x: int, y: int, button: str = "left") -> bool:
        """Click at absolute screen coordinates."""
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

    def type_text(self, text: str, interval: float = 0.05) -> bool:
        """Type a string character by character."""
        try:
            if not _PYAUTOGUI_AVAILABLE:
                raise RuntimeError("pyautogui not available")
            pyautogui.typewrite(text, interval=interval)
            logger.debug(f"[VECTOR][pc_controller] typed {len(text)} chars")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][pc_controller] type_text error: {e}")
            return False

    def hotkey(self, *keys: str) -> bool:
        """Press a keyboard shortcut (e.g. 'ctrl', 'c')."""
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

    def launch_app(self, app_name: str, args: list[str] | None = None) -> dict:
        """Launch an application without waiting for it to finish.

        Resolves common Windows app aliases before falling back to shutil.which.
        Returns a dict with launched/pid/app or launched/error.
        This is a YELLOW-tier action — go through permission_gateway in production.
        """
        try:
            args = args or []
            name_lower = app_name.strip().lower()

            # 1. Check alias table first
            exe = _WIN_APP_ALIASES.get(name_lower)

            # 2. If no alias, try shutil.which (finds anything on PATH)
            if exe is None:
                exe = shutil.which(app_name) or app_name

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
    # Shell command (YELLOW-tier)
    # ------------------------------------------------------------------

    def run_shell_command(self, command: str, timeout: int = 30) -> dict:
        """Run a shell command and return exit code + stdout + stderr.

        WARNING: YELLOW-tier action — must go through permission_gateway in production.
        Never call this directly from untrusted input.
        """
        try:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
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

    # launch_app smoke test (notepad — safe, closes immediately in CI)
    launch_result = ctrl.launch_app("notepad")
    if not isinstance(launch_result, dict) or "launched" not in launch_result:
        logger.error("[VECTOR][pc_controller] launch_app returned wrong type")
        ok = False
    else:
        logger.info(f"[VECTOR][pc_controller] launch_app result: {launch_result}")

    # run_shell_command smoke test
    shell_result = ctrl.run_shell_command("echo VECTOR_OK")
    if shell_result.get("exit_code") != 0:
        logger.error(f"[VECTOR][pc_controller] run_shell_command failed: {shell_result}")
        ok = False
    else:
        logger.info(f"[VECTOR][pc_controller] shell result: {shell_result}")

    print("OK pc_controller OK" if ok else "FAILED")
