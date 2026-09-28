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

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

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
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["gui_task", "vision_control", "desktop_task", "browser_task", "web_task", "click_screen"]
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
        # Same rule as the browser task: the model saying "finished" is a self-report with nothing checked, so it earns
        # a fraction of the old +40; anything else still costs HP.
        if result.get("status") == GUIStatus.END.value:
            self.award_points(10, f"gui_task self-reported finish: {instruction[:40]}")
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
        expect: dict | None = None,
    ) -> dict:
        """Run a natural-language automation task in a browser. `expect` (see BrowserController.check_expectation)
        makes the final page independently checked; without it a "finished" is only ever a self-report."""
        logger.info("[VECTOR][gui_agent] browser_task: {!r:.80}", instruction)
        ctrl = BrowserController(
            max_loop=max_loop or self._max_loop,
            factors=self._factors,
            headless=headless,
        )
        result = await ctrl.run_browser_task(instruction, url=url, expect=expect)
        self._store_result("browser_task", instruction, result)
        # The model saying "finished" used to earn the full +40 with nothing checked and failures earned nothing at all.
        # Reward now follows the evidence: verified against the caller's expectation -> +40; a bare self-report -> +10;
        # anything else (blocked/aborted/unverified/max-loop) costs HP.
        if result.get("status") == GUIStatus.END.value and result.get("verified") is True:
            self.award_points(40, f"browser verified: {instruction[:40]}")
        elif result.get("status") == GUIStatus.END.value:
            self.award_points(10, f"browser self-reported finish: {instruction[:40]}")
        else:
            self.deduct_points(10, f"browser task not completed ({result.get('status')}): {instruction[:40]}")
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
            prediction = chat(model=CONFIG.get("models", {}).get("vision", "qwen2.5vl:7b"),
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

    # ── Permission gating ────────────────────────────────────────────────────

    async def _gate(self, action_type: str, summary: str, source: str) -> bool:
        """gui_task/browser_task/click_screen are YELLOW-tier in
        core/config.py (real mouse/keyboard/browser control on the owner's
        actual desktop) but this agent never called PermissionGateway at
        all before executing — flagged in the 2026-07-29 coding district
        audit as a separate gap from that pass's fix (which only stopped a
        stray chat message from firing an EMPTY instruction, not from
        firing a real, fully-specified one with zero owner sign-off).
        Matches the same owner-command bypass every other YELLOW action
        already gets system-wide (permission_gateway.py's own execute():
        "the command itself IS the confirmation" when proposed_by is
        api_command/voice) — only autonomous/non-owner-initiated triggers
        actually wait for approval, so a routine owner-typed GUI command
        stays frictionless like it always has."""
        if source in ("api_command", "voice"):
            return True
        try:
            from core.loop.permission_gateway import PermissionGateway
            return await PermissionGateway.get_shared().request_approval(action_type, summary)
        except Exception as e:
            logger.error("[VECTOR][gui_agent] permission gate error, failing closed: {}", e)
            return False

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

    async def _answer_query(self, query: str) -> dict:
        """Answer a free-text question directly instead of driving real
        mouse/keyboard/browser control. Grounded in this agent's actual
        capabilities so the answer is relevant, not generic."""
        try:
            from core.inference.vectorcode_llm import chat
            sys_prompt = (
                "You are GUIAutomationAgent, VECTOR's vision-based desktop and "
                "browser automation agent. You use a VLM agent loop to complete "
                "natural-language desktop tasks (gui_task), browser tasks "
                "(browser_task), and single-shot element clicks (click_screen). "
                "Answer the user's question directly and concisely; do not take "
                "any GUI action."
            )
            answer = chat(
                model=CONFIG.get("models", {}).get("reasoning", "vector-reasoning"),
                messages=[{"role": "system", "content": sys_prompt},
                          {"role": "user", "content": query}],
                timeout=30.0,
            )
            return {"status": "ok", "response": answer or "", "agent": self.name}
        except Exception as e:
            logger.error("[VECTOR][gui_agent] _answer_query error: {}", e)
            return {"status": "error", "error": str(e)}

    async def run(self, task: dict) -> dict:
        p = task.get("params", task)
        # 2026-09-24 (independent review finding -- HIGH): reading
        # p.get("action") unconditionally let a caller reach real GUI
        # automation (gui_task/click_screen/browser_task/vision_control --
        # all RED) via an UNCLASSIFIED outer type routed here by
        # CodingSwarm's keyword-score selection, with params.action set to
        # the real RED action the outer type was never authorized for.
        # Fixed to prefer the real, authorized outer type the same way
        # code_conductor_agent.py/mlops_agent.py were fixed the same day --
        # params.action remains the fallback for internal/smoke-test
        # callers with no "type" key.
        action = task.get("type") or p.get("action")
        instruction = p.get("instruction", p.get("task", ""))

        # 2026-07-29 (HIGH SEVERITY fix): `action` used to default to
        # "gui_task" whenever no explicit action was given, and run_gui_task()
        # ran unconditionally even with an empty instruction. gui_task /
        # browser_task drive a REAL VLM agent loop that clicks, types, and
        # controls the browser on the owner's actual desktop. Real chat
        # dispatch (governor._dispatch_to_district -> agent.run(task)) can
        # land here with only task["params"]["query"] set and no
        # "action"/"instruction" at all -- that used to silently fire a real
        # GUI automation loop with an empty instruction. Same bug class as
        # karpathy_lab's autoresearch_runner (a real subprocess triggered by a
        # stray chat message). Now: GUI/browser actions only fire on an
        # EXPLICIT action match AND a non-empty instruction/description;
        # everything else gets a safe grounded answer instead.
        source = p.get("source", task.get("source", ""))
        if action in ("gui_task", "vision_control", "desktop_task") and instruction.strip():
            if not await self._gate("gui_task", f"Desktop GUI action: {instruction[:120]}", source):
                return {"status": "error", "error": "GUI action not approved by owner"}
            return await self.run_gui_task(
                instruction=instruction,
                max_loop=p.get("max_loop"),
            )
        elif action in ("browser_task", "web_task", "browser") and instruction.strip():
            if not await self._gate("browser_task", f"Browser automation: {instruction[:120]}", source):
                return {"status": "error", "error": "Browser action not approved by owner"}
            return await self.run_browser_task(
                instruction=instruction,
                url=p.get("url"),
                max_loop=p.get("max_loop"),
                headless=p.get("headless", False),
                expect=p.get("expect") if isinstance(p.get("expect"), dict) else None,
            )
        elif action == "click_screen" and p.get("description", p.get("element", "")).strip():
            _desc = p.get("description", p.get("element", ""))
            if not await self._gate("click_screen", f"Screen click: {_desc[:120]}", source):
                return {"status": "error", "error": "Click action not approved by owner"}
            return await self.click_screen(description=_desc)

        query = (
            p.get("query") or p.get("content") or task.get("query")
            or task.get("prompt") or instruction or ""
        )
        if query.strip():
            return await self._answer_query(query)
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
