import sys

import numpy as np
from loguru import logger

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
                monitor = sct.monitors[1]  # 1 = primary monitor (consistent with screen_observer)
                raw = sct.grab(monitor)
                # mss returns BGRA; convert to RGB numpy array
                frame = np.frombuffer(raw.bgra, dtype=np.uint8).reshape(
                    raw.height, raw.width, 4
                )
                frame_rgb = frame[:, :, :3]  # drop alpha

            if save_path and _PIL_AVAILABLE:
                try:
                    img = Image.fromarray(frame_rgb)
                    img.save(save_path)
                    logger.info(f"[VECTOR][pc_controller] screenshot saved → {save_path}")
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

    print("✅ pc_controller OK" if ok else "❌ FAILED")
