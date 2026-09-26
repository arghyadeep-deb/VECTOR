"""
VECTOR Vision Control — Browser Controller
VLM-driven Playwright browser automation.

Instead of hardcoded CSS selectors, the VLM looks at a browser screenshot,
understands what's on the page, and decides where to click/type.

VECTOR already uses Playwright in time_calendar/kiit_scraper.py.
This extends it with the VLM agent loop pattern from GUIAgent.

Usage:
    ctrl = BrowserController()
    result = asyncio.run(ctrl.run_browser_task(
        "Go to google.com and search for AI news",
        url="https://www.google.com"
    ))
    logger.info(result["status"])

"""
from __future__ import annotations

import asyncio
import base64
import sys
from typing import Optional

from core.config import CONFIG
from core.vision_control.action_parser import action_parser
from core.vision_control.vision_operator import ACTION_SPACE
from core.vision_control.gui_agent import GUIStatus
from core.browser.governance import get_browser_governance
from core.loop.permission_gateway import PermissionGateway
from loguru import logger

_BROWSER_SYSTEM_PROMPT = """You are VECTOR's browser automation agent. You control a web browser to complete tasks.

You can use these actions (coordinates are 0-1000 normalized to browser window size):

click(start_box='<point>x y</point>')          — click at position
double_click(start_box='<point>x y</point>')   — double-click
type(content='text to type')                   — type text at focused element
hotkey(key='ctrl a')                           — keyboard shortcut
scroll(start_box='<point>x y</point>', direction='down') — scroll
wait()                                         — wait 2 seconds
navigate(url='https://example.com')           — go to URL
finished()                                     — task complete
call_user()                                    — need human help

Always output Thought: then Action: on separate lines.
Current task: {instruction}"""


class BrowserController:
    """
    VECTOR's VLM-driven browser automation.
    Uses Playwright for rendering, VLM for visual understanding.
    """

    def __init__(
        self,
        model: str | None = None,
        max_loop: int = 20,
        loop_interval: float = 1.0,
        headless: bool = False,
        factors: list[int] | None = None,
    ) -> None:
        self._model         = model or CONFIG.get("models", {}).get("vision", "qwen2.5vl:7b")
        self._max_loop      = max_loop
        self._loop_interval = loop_interval
        self._headless      = headless
        self._factors       = factors or [1000, 1000]

    async def screenshot_page(self, page) -> dict:
        """Take a screenshot of the current browser page."""
        png = await page.screenshot(type="png", full_page=False)
        b64 = base64.b64encode(png).decode()
        viewport = page.viewport_size or {"width": 1280, "height": 800}
        return {
            "base64": b64,
            "width":  viewport["width"],
            "height": viewport["height"],
        }

    async def execute_browser_action(self, page, action: dict) -> dict:
        """Execute a parsed action in the browser."""
        action_type = (action.get("action_type") or "").lower()
        inputs      = action.get("action_inputs", {})
        s_coords    = action.get("start_coords")

        if action_type in ("finished", "call_user", "error_env"):
            return {"status": "terminal", "type": action_type}

        try:
            governance = get_browser_governance()
            current_url = ""
            try:
                current_url = page.url
            except Exception:
                current_url = ""
            decision = governance.classify(
                action_type,
                url=current_url,
                inputs=inputs,
            )
            if not decision.allowed:
                approved = False
                if decision.requires_owner:
                    summary = f"{action_type} on {current_url or '(unknown page)'}"
                    try:
                        approved = await PermissionGateway().request_approval(
                            decision.permission_action, summary,
                        )
                    except Exception as exc:
                        logger.warning(
                            "[VECTOR][browser_ctrl] request_approval failed, staying blocked: {}", exc,
                        )
                        approved = False

                if not approved:
                    logger.warning(
                        "[VECTOR][browser_ctrl] blocked {}: {}",
                        action_type,
                        decision.reason,
                    )
                    return {
                        "status": "blocked",
                        "action_type": action_type,
                        "level": decision.level,
                        "reason": decision.reason,
                        "requires_owner": decision.requires_owner,
                    }
                logger.info(
                    "[VECTOR][browser_ctrl] owner approved {} — proceeding", action_type,
                )

            if action_type in ("click", "left_click", "left_single"):
                if s_coords:
                    await page.mouse.click(s_coords[0], s_coords[1])

            elif action_type in ("double_click", "left_double"):
                if s_coords:
                    await page.mouse.dblclick(s_coords[0], s_coords[1])

            elif action_type in ("type", "input_text"):
                content = inputs.get("content", "")
                await page.keyboard.type(content)

            elif action_type in ("hotkey", "key_press"):
                key_str = inputs.get("key") or inputs.get("hotkey", "")
                keys = key_str.split()
                if len(keys) == 1:
                    await page.keyboard.press(keys[0].capitalize())
                else:
                    mods = "+".join(k.capitalize() for k in keys[:-1])
                    await page.keyboard.press(f"{mods}+{keys[-1].capitalize()}")

            elif action_type == "scroll":
                direction = inputs.get("direction", "down")
                x, y = (s_coords or (640, 400))
                delta = -300 if direction == "up" else 300
                if direction in ("up", "down"):
                    await page.mouse.wheel(0, delta)
                else:
                    await page.mouse.wheel(delta, 0)

            elif action_type == "navigate":
                url = inputs.get("url", "")
                if url:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            elif action_type == "wait":
                await asyncio.sleep(2.0)

        except Exception as e:
            logger.warning("[VECTOR][browser_ctrl] execute {} error: {}", action_type, e)
            return {"status": "error", "error": str(e)}

        return {"status": "ok", "action_type": action_type}

    async def _call_vlm(self, system_prompt: str, screenshot_b64: str, history: list[dict]) -> str:
        ctx_parts = [f"[Step {s['loop']}] {s['prediction'][:200]}" for s in history[-3:] if s.get("prediction")]
        context = "\n".join(ctx_parts)
        user_text = "What do you see in the browser and what should be done next?"
        if context:
            user_text = f"Previous actions:\n{context}\n\n{user_text}"
        try:
            from core.inference.vectorcode_llm import chat
            response = chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}},
                    ]},
                ],
                timeout=60.0,
            )
            return response or ""
        except Exception as e:
            logger.debug("[VECTOR][browser_ctrl] VLM error: {}", e)
            raise

    @staticmethod
    async def _collect_evidence(page) -> dict:
        """What the browser actually shows when the task ends: final URL, title and a short text excerpt. Never raises."""
        evidence: dict = {"final_url": "", "final_title": "", "final_text_excerpt": ""}
        try:
            evidence["final_url"] = page.url
        except Exception:
            pass
        try:
            evidence["final_title"] = (await page.title())[:300]
        except Exception:
            pass
        try:
            evidence["final_text_excerpt"] = " ".join((await page.inner_text("body", timeout=3000)).split())[:1500]
        except Exception:
            pass
        return evidence

    @staticmethod
    def check_expectation(expect: dict | None, evidence: dict) -> tuple[bool, list[str]]:
        """Independent check of the final page against criteria the caller declared up front (the model's own
        `finished()` is a claim, not evidence). Supported keys: url_equals, url_contains, title_contains,
        text_contains (str or list). Every given key must hold; an empty/unknown expectation is not a pass."""
        if not isinstance(expect, dict) or not expect:
            return False, ["no expectation given"]
        failures: list[str] = []
        known = False
        url, title, text = evidence.get("final_url", ""), evidence.get("final_title", ""), evidence.get("final_text_excerpt", "")
        if "url_equals" in expect:
            known = True
            if url != expect["url_equals"]:
                failures.append(f"url {url!r} != {expect['url_equals']!r}")
        if "url_contains" in expect:
            known = True
            if str(expect["url_contains"]) not in url:
                failures.append(f"url does not contain {expect['url_contains']!r}")
        if "title_contains" in expect:
            known = True
            if str(expect["title_contains"]) not in title:
                failures.append(f"title does not contain {expect['title_contains']!r}")
        if "text_contains" in expect:
            known = True
            wanted = expect["text_contains"] if isinstance(expect["text_contains"], list) else [expect["text_contains"]]
            for w in wanted:
                if str(w) not in text:
                    failures.append(f"page text does not contain {w!r}")
        if not known:
            return False, ["expectation has no recognised keys"]
        return not failures, failures

    async def run_browser_task(
        self,
        instruction: str,
        url: str | None = None,
        browser_context=None,   # pass existing Playwright context if available
        expect: dict | None = None,
    ) -> dict:
        """
        Open a browser and complete the instruction using VLM-guided automation.
        Returns {status, loop_count, conversations, action_log, evidence, self_reported_finish[, verified, error]}.

        `finished()` from the model is a self-report. Without `expect` the result says so (`self_reported_finish`) and
        carries the final page as `evidence` for the caller to verify (e.g. a plan's result_field check). With `expect`
        the final page is checked here: a mismatch turns END into ERROR (`verified: False`), a match sets `verified: True`.
        Blocked/failed actions are recorded, and three in a row abort the run instead of burning the remaining loops.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return {"status": "error", "error": "playwright not installed — run: pip install playwright && playwright install"}

        system_prompt = _BROWSER_SYSTEM_PROMPT.format(instruction=instruction)
        conversations: list[dict] = []
        action_log: list[dict] = []
        consecutive_failures = 0
        loop_count = 0
        final_status = GUIStatus.ERROR
        error_msg: str | None = None
        evidence: dict = {}

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self._headless)
            context = browser_context or await browser.new_context(
                viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()

            if url:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                except Exception as e:
                    logger.warning("[VECTOR][browser_ctrl] initial navigation failed: {}", e)

            try:
                while loop_count < self._max_loop:
                    loop_count += 1

                    # Screenshot
                    try:
                        shot = await self.screenshot_page(page)
                    except Exception as e:
                        logger.error("[VECTOR][browser_ctrl] screenshot failed: {}", e)
                        break

                    screen_ctx = {"width": shot["width"], "height": shot["height"]}

                    # VLM
                    try:
                        prediction = await self._call_vlm(system_prompt, shot["base64"], conversations)
                    except Exception as e:
                        logger.error("[VECTOR][browser_ctrl] VLM failed: {}", e)
                        break

                    # Parse
                    parsed = action_parser(prediction, factors=self._factors, screen_ctx=screen_ctx)

                    step = {"loop": loop_count, "prediction": prediction, "parsed": parsed}
                    conversations.append(step)

                    # Execute
                    terminal = False
                    for action in parsed:
                        result = await self.execute_browser_action(page, action)
                        if result.get("status") == "terminal":
                            terminal = True
                            t = result.get("type", "finished")
                            final_status = GUIStatus.END if t == "finished" else GUIStatus.CALL_USER
                            break
                        action_log.append({"loop": loop_count, "action": result.get("action_type") or action.get("action_type"),
                                           "status": result.get("status"), "reason": result.get("reason") or result.get("error")})
                        if result.get("status") in ("blocked", "error"):
                            consecutive_failures += 1
                        else:
                            consecutive_failures = 0

                    if terminal:
                        break
                    if consecutive_failures >= 3:
                        final_status = GUIStatus.ERROR
                        error_msg = "3 consecutive browser actions were blocked or failed; aborting"
                        break

                    await asyncio.sleep(self._loop_interval)

                else:
                    final_status = GUIStatus.MAX_LOOP

            finally:
                evidence = await self._collect_evidence(page)
                await browser.close()

        out: dict = {
            "instruction":   instruction,
            "loop_count":    loop_count,
            "conversations": conversations,
            "action_log":    action_log,
            "evidence":      evidence,
            "self_reported_finish": final_status == GUIStatus.END,
        }
        if expect is not None and final_status == GUIStatus.END:
            passed, failures = self.check_expectation(expect, evidence)
            out["verified"] = passed
            if not passed:
                final_status = GUIStatus.ERROR
                error_msg = "the model reported finished, but the final page did not match the expected evidence: " + "; ".join(failures)
        out["status"] = final_status.value
        if error_msg:
            out["error"] = error_msg
        return out


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        ctrl = BrowserController()
        assert ctrl._max_loop == 20
        assert ctrl._headless is False
        print(f"OK browser_controller.py — BrowserController init")
        print(f"  model={ctrl._model} max_loop={ctrl._max_loop}")
        print(f"  (full browser task requires Playwright: playwright install)")

    asyncio.run(_smoke())
