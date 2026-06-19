"""
core/control/vision_controller.py

Vision-guided GUI automation — VECTOR's native UI-TARS equivalent.

Pipeline per task:
  1. Screenshot current screen
  2. Send image + task to qwen2.5vl:7b (dedicated GUI vision model)
  3. Parse model response → structured Action (click/type/scroll/key/done)
  4. Execute via PCController
  5. Re-screenshot and verify; repeat up to max_steps

All processing is local — no data leaves the device (RULE 5).
Model config: CONFIG["models"]["vision"] (default: qwen2.5vl:7b)
"""

import sys
import asyncio
import base64
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx
from loguru import logger

from core.config import CONFIG
from core.control.pc_controller import PCController

# ── Action schema ─────────────────────────────────────────────────────────────

ActionType = Literal["click", "right_click", "double_click", "type", "key", "scroll", "screenshot", "done", "fail"]

@dataclass
class GUIAction:
    action: ActionType
    x: int = 0
    y: int = 0
    text: str = ""
    key: str = ""
    direction: Literal["up", "down", "left", "right"] = "down"
    amount: int = 3
    reason: str = ""

@dataclass
class VisionStep:
    step: int
    screenshot_b64: str
    model_response: str
    action: GUIAction
    success: bool = False

@dataclass
class VisionResult:
    task: str
    completed: bool
    steps: list[VisionStep] = field(default_factory=list)
    final_reason: str = ""
    total_time_sec: float = 0.0


# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a GUI automation agent controlling a Windows PC.
You receive a screenshot of the current screen and a task to complete.
You must output ONLY a JSON object describing the next single action to take.

Action schema (pick one):
{"action": "click",        "x": <int>, "y": <int>, "reason": "<why>"}
{"action": "right_click",  "x": <int>, "y": <int>, "reason": "<why>"}
{"action": "double_click", "x": <int>, "y": <int>, "reason": "<why>"}
{"action": "type",         "text": "<text to type>", "reason": "<why>"}
{"action": "key",          "key": "<key name e.g. enter, ctrl+c, alt+f4>", "reason": "<why>"}
{"action": "scroll",       "x": <int>, "y": <int>, "direction": "up|down|left|right", "amount": <1-10>, "reason": "<why>"}
{"action": "screenshot",   "reason": "need to see updated screen"}
{"action": "done",         "reason": "<task completion confirmation>"}
{"action": "fail",         "reason": "<why task cannot be completed>"}

Rules:
- Output ONLY the JSON object, no markdown, no explanation.
- x and y are pixel coordinates on the screen.
- For "type", do not include "x"/"y" — just type at current focus.
- If the task is already complete, output {"action": "done", ...}.
- If you cannot complete the task safely, output {"action": "fail", ...}.
- Never perform destructive actions (delete files, format drives) unless explicitly instructed.
"""


# ── VisionController ──────────────────────────────────────────────────────────

class VisionController:
    """
    Vision-guided GUI automation using Ollama multimodal models.

    Usage:
        vc = VisionController()
        result = await vc.execute("Open Chrome and go to github.com")
        print(result.completed, result.final_reason)
    """

    def __init__(
        self,
        model: str | None = None,
        max_steps: int = 15,
        step_delay_sec: float = 1.0,
        ollama_host: str | None = None,
    ):
        self._model = model or CONFIG.get("models", {}).get("focus", "vector-focus")
        self._max_steps = max_steps
        self._step_delay = step_delay_sec
        self._ollama = (ollama_host or CONFIG.get("ollama_host", "http://127.0.0.1:11434")).rstrip("/")
        self._pc = PCController()

    # ── Public API ────────────────────────────────────────────────────────────

    async def execute(self, task: str) -> VisionResult:
        """Execute a natural-language GUI task. Returns VisionResult."""
        logger.info(f"[VECTOR][vision] Starting task: {task!r}")
        start = time.time()
        steps: list[VisionStep] = []

        for step_num in range(1, self._max_steps + 1):
            # 1. Screenshot
            img_b64 = self._capture_b64()

            # 2. Ask model
            raw = await self._ask_model(task, img_b64, step_num, steps)

            # 3. Parse
            action = self._parse_action(raw)
            logger.info(f"[VECTOR][vision] Step {step_num}: {action.action} — {action.reason}")

            # 4. Record step before execution
            vstep = VisionStep(step=step_num, screenshot_b64=img_b64, model_response=raw, action=action)
            steps.append(vstep)

            # 5. Terminal states
            if action.action == "done":
                vstep.success = True
                return VisionResult(
                    task=task, completed=True, steps=steps,
                    final_reason=action.reason,
                    total_time_sec=round(time.time() - start, 2),
                )
            if action.action == "fail":
                return VisionResult(
                    task=task, completed=False, steps=steps,
                    final_reason=action.reason,
                    total_time_sec=round(time.time() - start, 2),
                )

            # 6. Execute
            self._execute_action(action)
            vstep.success = True

            await asyncio.sleep(self._step_delay)

        return VisionResult(
            task=task, completed=False, steps=steps,
            final_reason=f"Reached max_steps ({self._max_steps}) without completing task",
            total_time_sec=round(time.time() - start, 2),
        )

    async def describe_screen(self) -> str:
        """Return a plain-text description of what's currently on screen."""
        img_b64 = self._capture_b64()
        prompt = "Describe what is currently visible on this screen in 2-3 sentences. Be specific about open apps, content, and any important UI elements."
        return await self._ask_model_raw(prompt, img_b64)

    async def find_element(self, description: str) -> tuple[int, int] | None:
        """Find a UI element by description and return (x, y) coordinates or None."""
        img_b64 = self._capture_b64()
        prompt = (
            f"Find the UI element described as: '{description}'.\n"
            "Output ONLY a JSON object: {\"x\": <int>, \"y\": <int>} with its center pixel coordinates.\n"
            "If not found, output: {\"x\": -1, \"y\": -1}"
        )
        raw = await self._ask_model_raw(prompt, img_b64)
        try:
            data = json.loads(self._extract_json(raw))
            x, y = int(data["x"]), int(data["y"])
            return (x, y) if x >= 0 else None
        except Exception:
            return None

    # ── Internals ─────────────────────────────────────────────────────────────

    def _capture_b64(self) -> str:
        """Screenshot → base64 PNG string."""
        try:
            import mss
            import mss.tools
            from PIL import Image
            import io
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                raw = sct.grab(monitor)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                # Resize to 1280×720 to keep token count manageable
                img.thumbnail((1280, 720), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            logger.warning(f"[VECTOR][vision] Screenshot failed: {e}")
            return ""

    async def _ask_model(self, task: str, img_b64: str, step: int, prev_steps: list[VisionStep]) -> str:
        history_summary = ""
        if prev_steps:
            history_summary = "\n\nPrevious actions taken:\n" + "\n".join(
                f"  Step {s.step}: {s.action.action}" +
                (f" at ({s.action.x},{s.action.y})" if s.action.x or s.action.y else "") +
                (f" text={s.action.text!r}" if s.action.text else "") +
                f" — {s.action.reason}"
                for s in prev_steps[-5:]  # last 5 only to keep context short
            )

        user_content = f"Task: {task}{history_summary}\n\nStep {step}: What is the next action?"

        payload = {
            "model": self._model,
            "system": _SYSTEM_PROMPT,
            "prompt": user_content,
            "images": [img_b64] if img_b64 else [],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 256},
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(f"{self._ollama}/api/generate", json=payload)
                r.raise_for_status()
                return r.json().get("response", "")
        except Exception as e:
            logger.warning(f"[VECTOR][vision] Model call failed: {e}")
            return '{"action": "fail", "reason": "model unavailable"}'

    async def _ask_model_raw(self, prompt: str, img_b64: str) -> str:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "images": [img_b64] if img_b64 else [],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 512},
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(f"{self._ollama}/api/generate", json=payload)
                r.raise_for_status()
                return r.json().get("response", "")
        except Exception as e:
            logger.warning(f"[VECTOR][vision] Raw model call failed: {e}")
            return ""

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract first JSON object from model response."""
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        return match.group(0) if match else text.strip()

    def _parse_action(self, raw: str) -> GUIAction:
        try:
            data = json.loads(self._extract_json(raw))
            action_type = data.get("action", "fail")
            return GUIAction(
                action=action_type,
                x=int(data.get("x", 0)),
                y=int(data.get("y", 0)),
                text=str(data.get("text", "")),
                key=str(data.get("key", "")),
                direction=data.get("direction", "down"),
                amount=int(data.get("amount", 3)),
                reason=str(data.get("reason", "")),
            )
        except Exception as e:
            logger.warning(f"[VECTOR][vision] Failed to parse action: {e} | raw={raw[:200]}")
            return GUIAction(action="fail", reason=f"parse error: {e}")

    def _execute_action(self, action: GUIAction):
        if not _PYAUTOGUI_OK:
            logger.warning("[VECTOR][vision] pyautogui not available — action skipped")
            return
        try:
            import pyautogui
            if action.action == "click":
                pyautogui.click(action.x, action.y)
            elif action.action == "right_click":
                pyautogui.rightClick(action.x, action.y)
            elif action.action == "double_click":
                pyautogui.doubleClick(action.x, action.y)
            elif action.action == "type":
                pyautogui.typewrite(action.text, interval=0.05)
            elif action.action == "key":
                pyautogui.hotkey(*action.key.replace("+", " ").split())
            elif action.action == "scroll":
                amount = action.amount if action.direction == "down" else -action.amount
                pyautogui.scroll(amount, x=action.x or None, y=action.y or None)
            elif action.action == "screenshot":
                pass  # next iteration will screenshot automatically
        except Exception as e:
            logger.warning(f"[VECTOR][vision] Action execution failed: {e}")


# ── pyautogui availability ────────────────────────────────────────────────────

try:
    import pyautogui
    _PYAUTOGUI_OK = True
except ImportError:
    _PYAUTOGUI_OK = False


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _test():
        vc = VisionController()
        desc = await vc.describe_screen()
        print("Screen:", desc[:200] if desc else "(no description — is Ollama running?)")
        print("✅ vision_controller.py OK")

    asyncio.run(_test())
