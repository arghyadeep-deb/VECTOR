"""
VECTOR GUIAutomationAgent — District 03: coding
VLM-powered GUI automation — complete any desktop or browser task
described in natural language.

Governor routes: gui_task, click_screen, browser_task, vision_control

Usage:
    agent = GUIAutomationAgent()
    result = asyncio.run(agent.run({
        "params": {"action": "gui_task",
                   "instruction": "Open Chrome and search for AI news"}
    }))
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from core.vision_control.gui_agent import GUIAgent, GUIStatus
from core.vision_control.vision_operator import VisionOperator
from core.vision_control.browser_controller import BrowserController
from core.vision_control.action_parser import action_parser
from loguru import logger


class GUIAutomationAgent(AgentBase):
    """
    VECTOR's vision-based GUI automation agent.
    Uses a VLM agent loop to complete desktop and browser tasks
    described in plain English — no hardcoded coordinates needed.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="GUIAutomationAgent",
            district="coding",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory  = EpisodicMemory()
        self._context = ContextEngine()
        cfg = CONFIG.get("vision_control", {})
        self._max_loop = int(cfg.get("max_loop", 25))
        self._factors  = cfg.get("factors", [1000, 1000])
        logger.info("[VECTOR][gui_agent] ready gen={} hp={}", generation, self.health_points)

    # ── Desktop GUI task ──────────────────────────────────────────────────────

    async def run_gui_task(
        self,
        instruction: str,
        max_loop: int | None = None,
        on_step=None,
    ) -> dict:
        """Run a natural-language GUI automation task on the desktop."""
        logger.info("[VECTOR][gui_agent] gui_task: {!r:.80}", instruction)
        operator = VisionOperator()
        agent = GUIAgent(
            operator=operator,
            max_loop=max_loop or self._max_loop,
            factors=self._factors,
            on_step=on_step,
        )
        result = await agent.run(instruction)
        self._store_result("gui_task", instruction, result)
        if result.get("status") == GUIStatus.END.value:
            self.award_points(40, f"gui_task: {instruction[:40]}")
        else:
            self.deduct_points(10, f"gui_task incomplete: {result.get('status')}")
        return result

    # ── Browser task ──────────────────────────────────────────────────────────

    async def run_browser_task(
        self,
        instruction: str,
        url: str | None = None,
        max_loop: int | None = None,
        headless: bool = False,
    ) -> dict:
        """Run a natural-language automation task in a browser."""
        logger.info("[VECTOR][gui_agent] browser_task: {!r:.80}", instruction)
        ctrl = BrowserController(
            max_loop=max_loop or self._max_loop,
            factors=self._factors,
            headless=headless,
        )
        result = await ctrl.run_browser_task(instruction, url=url)
        self._store_result("browser_task", instruction, result)
        if result.get("status") == GUIStatus.END.value:
            self.award_points(40, f"browser: {instruction[:40]}")
        return result

    # ── Single vision click ───────────────────────────────────────────────────

    async def click_screen(self, description: str) -> dict:
        """
        Take a screenshot, ask VLM where the described element is, and click it.
        Quick single-shot click without the full agent loop.
        """
        operator = VisionOperator()
        shot = await operator.screenshot()
        screen_ctx = {"width": shot["width"], "height": shot["height"]}

        try:
            from core.inference.vectorcode_llm import chat
            prompt = (
                f"Find the element described as: '{description}'\n"
                f"Respond with ONLY an action like: click(start_box='<point>X Y</point>')\n"
                f"Use coordinates 0-1000 normalized to screen size."
            )
            messages = [
                {"role": "system", "content": "You are a GUI element locator. Respond with only an action string."},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{shot['base64']}"}},
                ]},
            ]
            prediction = chat(model=CONFIG.get("models", {}).get("focus", "vector-focus"),
                              messages=messages, timeout=30.0)
            parsed = action_parser(prediction or "", factors=self._factors, screen_ctx=screen_ctx)
            if parsed and parsed[0].get("start_coords"):
                result = await operator.execute(parsed[0])
                self.award_points(10, f"click: {description[:30]}")
                return {"status": "ok", "clicked": parsed[0]["start_coords"], "description": description}
            return {"status": "error", "error": "VLM could not locate element"}
        except Exception as e:
            logger.error("[VECTOR][gui_agent] click_screen failed: {}", e)
            return {"status": "error", "error": str(e)}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _store_result(self, event_type: str, instruction: str, result: dict) -> None:
        status = result.get("status", "unknown")
        loops  = result.get("loop_count", 0)
        self._memory.store(
            event_type=event_type,
            content=f"GUIAutomationAgent {event_type}: {instruction[:60]} → {status} ({loops} loops)",
            tags=["gui", "automation", event_type],
            source="gui_automation_agent",
        )

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", task)
        action = p.get("action", "gui_task")

        if action in ("gui_task", "vision_control", "desktop_task"):
            return await self.run_gui_task(
                instruction=p.get("instruction", p.get("task", "")),
                max_loop=p.get("max_loop"),
            )
        elif action in ("browser_task", "web_task", "browser"):
            return await self.run_browser_task(
                instruction=p.get("instruction", p.get("task", "")),
                url=p.get("url"),
                max_loop=p.get("max_loop"),
                headless=p.get("headless", False),
            )
        elif action == "click_screen":
            return await self.click_screen(
                description=p.get("description", p.get("element", ""))
            )
        return {"status": "error", "error": f"unknown action: {action}"}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][gui_agent] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][gui_agent] died — HP=0")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = GUIAutomationAgent()
        assert agent.health_points == 500
        assert agent.name == "GUIAutomationAgent"
        assert agent.district == "coding"
        assert agent._max_loop == 25

        # Verify action routing without running the full loop
        assert hasattr(agent, "_max_loop")
        assert hasattr(agent, "_factors")

        print(f"OK gui_automation_agent.py HP={agent.health_points}")
        print(f"  max_loop={agent._max_loop} factors={agent._factors}")

    asyncio.run(_smoke())
