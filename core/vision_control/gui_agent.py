"""
VECTOR Vision Control — GUI Agent
Python port of UI-TARS-desktop/packages/ui-tars/sdk/src/GUIAgent.ts

The main VLM-driven GUI automation loop:
  screenshot → VLM predicts action → parse → execute → repeat

Supports pause/resume/stop by the owner (human-in-the-loop).
Uses VECTOR's inference stack (Ollama vision model → Gemini → GPT-4o fallback).

Usage:
    agent = GUIAgent()
    result = asyncio.run(agent.run("Open Notepad and type Hello VECTOR"))
    logger.info(result["status"])

"""
from __future__ import annotations

__all__ = [
    "GUIAgent",
    "GUIStatus",
]


import asyncio
import base64
import sys
import time
import uuid
from enum import Enum
from typing import Callable, Optional

from core.config import CONFIG
from core.vision_control.action_parser import action_parser
from core.vision_control.vision_operator import VisionOperator
from loguru import logger

# â”€â”€ Status enum (mirrors StatusEnum from shared/types/agent.ts) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class GUIStatus(str, Enum):
    INIT         = "init"
    RUNNING      = "running"
    PAUSE        = "pause"
    END          = "end"
    CALL_USER    = "call_user"
    USER_STOPPED = "user_stopped"
    MAX_LOOP     = "max_loop"
    ERROR        = "error"


# â”€â”€ VLM system prompt â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_SYSTEM_PROMPT_TEMPLATE = """You are VECTOR's GUI automation agent. You control the computer to complete tasks.

{action_space}

Rules:
1. Always output Thought: (your reasoning) then Action: (the action to take)
2. Look at the screenshot carefully before deciding
3. Use finished() when the task is complete
4. Use call_user() if you're stuck and need human help
5. One action per response

Current task: {instruction}"""


# â”€â”€ GUI Agent â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class GUIAgent:
    """
    VECTOR's VLM-driven GUI automation agent.
    Runs a continuous loop: screenshot → VLM → parse action → execute → repeat.
    Supports pause/resume/stop for human-in-the-loop control.
    """

    def __init__(
        self,
        operator: VisionOperator | None = None,
        model: str | None = None,
        max_loop: int = 25,
        loop_interval: float = 0.5,
        factors: list[int] | None = None,
        on_step: Callable[[dict], None] | None = None,
    ) -> None:
        self._operator      = operator or VisionOperator()
        self._model         = model or CONFIG.get("models", {}).get("vision", "qwen2.5vl:7b")
        self._max_loop      = max_loop
        self._loop_interval = loop_interval
        self._factors       = factors or [1000, 1000]
        self._on_step       = on_step      # callback after each step

        self._status        = GUIStatus.INIT
        self._session_id    = str(uuid.uuid4())
        self._paused        = False
        self._stop_signal   = False
        self._resume_event  = asyncio.Event()
        self._resume_event.set()  # not paused initially

    # â”€â”€ Lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def pause(self) -> None:
        if self._status == GUIStatus.RUNNING:
            self._paused = True
            self._resume_event.clear()
            self._status = GUIStatus.PAUSE
            logger.info("[VECTOR][gui_agent] paused")

    def resume(self) -> None:
        if self._status == GUIStatus.PAUSE:
            self._paused = False
            self._status = GUIStatus.RUNNING
            self._resume_event.set()
            logger.info("[VECTOR][gui_agent] resumed")

    def stop(self) -> None:
        self._stop_signal = True
        self._resume_event.set()  # unblock if paused
        logger.info("[VECTOR][gui_agent] stop signal sent")

    @property
    def status(self) -> GUIStatus:
        return self._status

    # â”€â”€ Main loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def run(self, instruction: str) -> dict:
        """
        Run the GUI agent loop to complete a natural-language instruction.
        Returns a dict with status, session_id, loop_count, and conversation history.
        """
        self._status     = GUIStatus.RUNNING
        self._stop_signal = False
        self._paused      = False
        self._resume_event.set()

        session_id  = self._session_id
        loop_count  = 0
        conversations: list[dict] = []
        err_msg: str = ""

        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            action_space=self._operator.get_action_space(),
            instruction=instruction,
        )

        logger.info("[VECTOR][gui_agent] session={} instruction={!r:.80}", session_id, instruction)

        try:
            while loop_count < self._max_loop:
                # â”€â”€ Pause/stop check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                await self._resume_event.wait()
                if self._stop_signal:
                    self._status = GUIStatus.USER_STOPPED
                    break

                loop_count += 1
                step_start = time.time()

                # â”€â”€ 1. Screenshot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                shot = await self._screenshot_with_retry()
                if shot is None:
                    self._status = GUIStatus.ERROR
                    err_msg = "Screenshot failed after retries"
                    break

                screen_ctx = {"width": shot["width"], "height": shot["height"]}

                # â”€â”€ 2. VLM prediction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                prediction = await self._predict_with_retry(
                    system_prompt, shot["base64"], conversations
                )
                if prediction is None:
                    self._status = GUIStatus.ERROR
                    err_msg = "VLM call failed after retries"
                    break

                # â”€â”€ 3. Parse actions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                parsed = action_parser(
                    prediction,
                    factors=self._factors,
                    screen_ctx=screen_ctx,
                )

                step_data = {
                    "loop":        loop_count,
                    "prediction":  prediction,
                    "parsed":      parsed,
                    "screen":      screen_ctx,
                    "elapsed_ms":  round((time.time() - step_start) * 1000),
                }

                # â”€â”€ 4. Execute actions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                terminal = False
                terminal_type = ""
                for action in parsed:
                    result = await self._execute_with_retry(action)
                    if result.get("status") == "terminal":
                        terminal = True
                        terminal_type = result.get("type", "finished")
                        break
                    if result.get("status") == "error":
                        logger.warning("[VECTOR][gui_agent] execute error: {}", result.get("error"))

                conversations.append(step_data)
                if self._on_step:
                    try:
                        self._on_step(step_data)
                    except Exception:
                        logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

                if terminal:
                    if terminal_type == "finished":
                        self._status = GUIStatus.END
                    elif terminal_type == "call_user":
                        self._status = GUIStatus.CALL_USER
                    else:
                        self._status = GUIStatus.ERROR
                    break

                await asyncio.sleep(self._loop_interval)

            else:
                # Reached max loops
                self._status = GUIStatus.MAX_LOOP
                err_msg = f"Reached max loops ({self._max_loop})"
                logger.warning("[VECTOR][gui_agent] {}", err_msg)

        except asyncio.CancelledError:
            self._status = GUIStatus.USER_STOPPED
        except Exception as e:
            self._status = GUIStatus.ERROR
            err_msg = str(e)
            logger.error("[VECTOR][gui_agent] error: {}", e)

        result = {
            "session_id":    session_id,
            "instruction":   instruction,
            "status":        self._status.value,
            "loop_count":    loop_count,
            "conversations": conversations,
        }
        # `finished()` is the model's own claim: nothing here checks the screen. Flag it so callers do not treat it as
        # verified (the desktop has no independent, offline way to confirm an arbitrary instruction was achieved).
        result["self_reported_finish"] = self._status == GUIStatus.END
        if err_msg:
            result["error"] = err_msg

        logger.info("[VECTOR][gui_agent] done status={} loops={}", self._status.value, loop_count)
        return result

    # â”€â”€ Retry wrappers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _screenshot_with_retry(self, max_retries: int = 5) -> dict | None:
        for attempt in range(1, max_retries + 1):
            try:
                shot = await self._operator.screenshot()
                if shot.get("width", 0) > 0 and shot.get("height", 0) > 0:
                    return shot
            except Exception as e:
                logger.warning("[VECTOR][gui_agent] screenshot attempt {}/{}: {}", attempt, max_retries, e)
            if attempt < max_retries:
                await asyncio.sleep(1.0)
        return None

    async def _predict_with_retry(
        self,
        system_prompt: str,
        screenshot_b64: str,
        history: list[dict],
        max_retries: int = 3,
    ) -> str | None:
        for attempt in range(1, max_retries + 1):
            try:
                return await self._call_vlm(system_prompt, screenshot_b64, history)
            except Exception as e:
                logger.warning("[VECTOR][gui_agent] VLM attempt {}/{}: {}", attempt, max_retries, e)
                if attempt < max_retries:
                    await asyncio.sleep(min(2 ** attempt, 30))
        return None

    async def _execute_with_retry(self, action: dict, max_retries: int = 3) -> dict:
        for attempt in range(1, max_retries + 1):
            try:
                return await self._operator.execute(action)
            except Exception as e:
                logger.warning("[VECTOR][gui_agent] execute attempt {}/{}: {}", attempt, max_retries, e)
                if attempt < max_retries:
                    await asyncio.sleep(0.5)
        return {"status": "error", "error": "execute failed after retries"}

    # â”€â”€ VLM call â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _call_vlm(
        self,
        system_prompt: str,
        screenshot_b64: str,
        history: list[dict],
    ) -> str:
        """
        Call VECTOR's multimodal VLM with the current screenshot.
        Uses provider_client for Ollama → Gemini → GPT-4o fallback chain.
        """
        # Build conversation context (last 3 steps to avoid context overflow)
        ctx_parts = []
        for step in history[-3:]:
            if step.get("prediction"):
                ctx_parts.append(f"[Step {step['loop']}] {step['prediction'][:200]}")
        context = "\n".join(ctx_parts) if ctx_parts else ""

        user_content = "Look at the current screen and determine the next action."
        if context:
            user_content = f"Previous steps:\n{context}\n\n{user_content}"

        try:
            from core.inference.vectorcode_llm import chat
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_content},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{screenshot_b64}"
                        }},
                    ],
                },
            ]
            response = chat(
                model=self._model,
                messages=messages,
                timeout=60.0,
            )
            return response or ""
        except Exception as e:
            logger.debug("[VECTOR][gui_agent] VLM call error: {}", e)
            raise


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = GUIAgent(max_loop=1)
        assert agent.status == GUIStatus.INIT
        assert agent._session_id is not None

        # Test pause/resume/stop
        agent._status = GUIStatus.RUNNING
        agent.pause()
        assert agent.status == GUIStatus.PAUSE
        agent.resume()
        assert agent.status == GUIStatus.RUNNING
        agent.stop()
        assert agent._stop_signal is True

        print(f"OK gui_agent.py — GUIAgent init, pause/resume/stop OK")
        print(f"  model={agent._model} max_loop={agent._max_loop}")
        print(f"  session_id={agent._session_id[:8]}…")

    asyncio.run(_smoke())
