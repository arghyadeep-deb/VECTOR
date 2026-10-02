"""
VECTOR Vision Control — Vision Operator
Python port of UI-TARS-desktop/packages/ui-tars/operators/nut-js/src/index.ts

Wraps VECTOR's existing core/control/pc_controller.py and core/sensing/screen_observer.py
with the Operator interface expected by GUIAgent.

Screenshot returns base64 PNG + screen dimensions.
Execute dispatches typed actions (click, type, hotkey, scroll, drag, wait, …).

Usage:
    op = VisionOperator()
    shot = asyncio.run(op.screenshot())
    logger.info(shot["width"], shot["height"])

"""
from __future__ import annotations

__all__ = [
    "ACTION_SPACE",
    "CLICK_ACTIONS",
    "DCLICK_ACTIONS",
    "DRAG_ACTIONS",
    "HOTKEY_ACTIONS",
    "KEY_MAP",
    "RCLICK_ACTIONS",
    "SCROLL_ACTIONS",
    "SCROLL_MAP",
    "TERMINAL_ACTIONS",
    "TYPE_ACTIONS",
    "VisionOperator",
]


import asyncio
import base64
import io
import platform
import subprocess
import sys
import time
from typing import Optional

from loguru import logger

# â”€â”€ Action type constants (mirrors shared/types/agent.ts ActionType) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TERMINAL_ACTIONS = {"finished", "call_user", "error_env"}
CLICK_ACTIONS    = {"click", "left_click", "left_single"}
DCLICK_ACTIONS   = {"left_double", "double_click"}
RCLICK_ACTIONS   = {"right_click", "right_single"}
SCROLL_ACTIONS   = {"scroll"}
DRAG_ACTIONS     = {"drag", "select"}
TYPE_ACTIONS     = {"type", "input_text"}
HOTKEY_ACTIONS   = {"hotkey", "key_press", "press"}

# Direction → scroll amount mapping
SCROLL_MAP = {"up": -3, "down": 3, "left": -3, "right": 3}

# VECTOR hotkey name → pyautogui key name
KEY_MAP = {
    "ctrl": "ctrl", "control": "ctrl",
    "shift": "shift", "alt": "alt",
    "cmd": "command", "command": "command", "win": "winleft",
    "enter": "enter", "return": "return",
    "backspace": "backspace", "delete": "delete",
    "tab": "tab", "esc": "escape", "escape": "escape",
    "space": "space", "pageup": "pageup", "pagedown": "pagedown",
    "home": "home", "end": "end",
    "left": "left", "right": "right", "up": "up", "down": "down",
    "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
    "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
    "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
    "a": "a", "b": "b", "c": "c", "v": "v", "x": "x", "z": "z",
}

ACTION_SPACE = """You are a GUI automation agent. Control the computer using these actions:

click(start_box='<point>x y</point>')          — left-click at coordinate
double_click(start_box='<point>x y</point>')   — double-click
right_click(start_box='<point>x y</point>')    — right-click
drag(start_box='<point>x1 y1</point>', end_box='<point>x2 y2</point>') — drag
type(content='text to type')                   — type text
hotkey(key='ctrl c')                           — keyboard shortcut
scroll(start_box='<point>x y</point>', direction='down') — scroll up/down/left/right
wait()                                         — wait 5 seconds
finished()                                     — task complete
call_user()                                    — need human help

Coordinates x,y are in range 0-1000 (normalized to screen size).
Always output Thought: then Action: on separate lines."""


class VisionOperator:
    """
    VECTOR's local computer operator.
    Wraps pc_controller + screen_observer with the VLM agent interface.
    """

    def __init__(self) -> None:
        self._pc   = None   # lazy-load PCController
        self._mss  = None   # lazy-load mss
        self._is_windows = platform.system() == "Windows"

    def _get_pc(self):
        if self._pc is None:
            from core.control.pc_controller import PCController
            self._pc = PCController()
        return self._pc

    # â”€â”€ Screenshot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def screenshot(self) -> dict:
        """
        Capture the full screen.
        Returns: {base64: str, width: int, height: int, scale_factor: float}
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._capture)

    def _capture(self) -> dict:
        try:
            import mss, mss.tools
            with mss.mss() as sct:
                monitor = sct.monitors[0]  # full virtual screen
                shot = sct.grab(monitor)
                # Convert to PNG bytes
                png_bytes = mss.tools.to_png(shot.rgb, shot.size)
                b64 = base64.b64encode(png_bytes).decode()
                return {
                    "base64": b64,
                    "width":  shot.width,
                    "height": shot.height,
                    "scale_factor": 1.0,
                }
        except ImportError:
            # Fallback: pyautogui screenshot
            import pyautogui
            img = pyautogui.screenshot()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            return {
                "base64": b64,
                "width":  img.width,
                "height": img.height,
                "scale_factor": 1.0,
            }

    # â”€â”€ Execute â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def execute(self, parsed_action: dict) -> dict:
        """
        Execute a parsed action dict from action_parser.
        Returns {"status": "ok"} or {"status": "terminal", "type": action_type}.
        """
        action_type = (parsed_action.get("action_type") or "").lower()
        inputs      = parsed_action.get("action_inputs", {})
        s_coords    = parsed_action.get("start_coords")
        e_coords    = parsed_action.get("end_coords")

        if action_type in TERMINAL_ACTIONS:
            logger.info("[VECTOR][vision_op] terminal action: {}", action_type)
            return {"status": "terminal", "type": action_type}

        loop = asyncio.get_event_loop()

        try:
            if action_type in CLICK_ACTIONS:
                if s_coords:
                    await loop.run_in_executor(None, self._click, s_coords[0], s_coords[1])

            elif action_type in DCLICK_ACTIONS:
                if s_coords:
                    await loop.run_in_executor(None, self._dclick, s_coords[0], s_coords[1])

            elif action_type in RCLICK_ACTIONS:
                if s_coords:
                    await loop.run_in_executor(None, self._rclick, s_coords[0], s_coords[1])

            elif action_type in DRAG_ACTIONS:
                if s_coords and e_coords:
                    await loop.run_in_executor(None, self._drag,
                                               s_coords[0], s_coords[1],
                                               e_coords[0], e_coords[1])

            elif action_type in TYPE_ACTIONS:
                content = inputs.get("content", "")
                await loop.run_in_executor(None, self._type_text, content)

            elif action_type in HOTKEY_ACTIONS:
                key_str = inputs.get("key") or inputs.get("hotkey", "")
                await loop.run_in_executor(None, self._hotkey, key_str)

            elif action_type in SCROLL_ACTIONS:
                direction = inputs.get("direction", "down")
                if s_coords:
                    await loop.run_in_executor(None, self._scroll,
                                               s_coords[0], s_coords[1], direction)

            elif action_type == "wait":
                await asyncio.sleep(5.0)

            elif action_type == "middle_click":
                if s_coords:
                    import pyautogui
                    pyautogui.click(s_coords[0], s_coords[1], button="middle")

            else:
                logger.debug("[VECTOR][vision_op] unknown action_type: {}", action_type)

        except Exception as e:
            logger.error("[VECTOR][vision_op] execute {} failed: {}", action_type, e)
            return {"status": "error", "error": str(e)}

        return {"status": "ok", "action_type": action_type}

    # â”€â”€ Low-level actions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _click(self, x: int, y: int) -> None:
        import pyautogui
        pyautogui.click(x, y)
        logger.debug("[VECTOR][vision_op] click ({}, {})", x, y)

    def _dclick(self, x: int, y: int) -> None:
        import pyautogui
        pyautogui.doubleClick(x, y)

    def _rclick(self, x: int, y: int) -> None:
        import pyautogui
        pyautogui.rightClick(x, y)

    def _drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        import pyautogui
        pyautogui.moveTo(x1, y1, duration=0.1)
        pyautogui.dragTo(x2, y2, duration=0.3, button="left")

    def _type_text(self, content: str) -> None:
        import pyautogui
        if self._is_windows:
            # Windows: use clipboard to preserve unicode
            import subprocess
            original = ""
            try:
                result = subprocess.run(
                    ["powershell", "-command", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=3
                )
                original = result.stdout.rstrip("\r\n")
            except Exception as e:
                logger.warning("[VECTOR][vision_op] clipboard read failed: {}", e)

            # Set new content via powershell. A single quote is the only
            # character with special meaning inside a PowerShell single-
            # quoted string (ends the literal) -- the correct escape is to
            # double it ('' inside '...'), not substitute a different
            # character, which silently corrupted every real apostrophe in
            # typed text (e.g. "don't" -> "don"t").
            text_no_newline = content.rstrip("\n")
            subprocess.run(
                ["powershell", "-command", f"Set-Clipboard '{text_no_newline.replace(chr(39), chr(39) * 2)}'"],
                timeout=3
            )
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.05)

            # Restore clipboard
            if original:
                subprocess.run(
                    ["powershell", "-command", f"Set-Clipboard '{original.replace(chr(39), chr(39) * 2)}'"],
                    timeout=3
                )

            # Handle trailing newline
            if content.endswith("\n"):
                pyautogui.press("enter")
        else:
            # Unix: type directly
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line:
                    pyautogui.typewrite(line, interval=0.02)
                if i < len(lines) - 1:
                    pyautogui.press("enter")

    def _hotkey(self, key_str: str) -> None:
        import pyautogui
        keys = [KEY_MAP.get(k.lower(), k.lower()) for k in key_str.split()]
        pyautogui.hotkey(*keys)
        logger.debug("[VECTOR][vision_op] hotkey {}", keys)

    def _scroll(self, x: int, y: int, direction: str) -> None:
        import pyautogui
        pyautogui.moveTo(x, y)
        clicks = SCROLL_MAP.get(direction.lower(), 3)
        if direction.lower() in ("left", "right"):
            pyautogui.hscroll(clicks)
        else:
            pyautogui.scroll(clicks)

    # â”€â”€ System prompt â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def get_action_space(self) -> str:
        return ACTION_SPACE


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        op = VisionOperator()
        shot = await op.screenshot()
        assert "base64" in shot
        assert shot["width"] > 0
        assert shot["height"] > 0
        print(f"OK vision_operator.py — screen {shot['width']}x{shot['height']}")
        print(f"  action_space: {len(op.get_action_space())} chars")
        # Test terminal action handling
        result = await op.execute({"action_type": "finished", "action_inputs": {}})
        assert result["status"] == "terminal"
        print(f"  terminal action: OK")

    asyncio.run(_smoke())
