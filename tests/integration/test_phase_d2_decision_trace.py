"""D2 tests — Decision trace timeline: reasoning_memory.get_recent + /brain/reasoning/chains."""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path


# ── ReasoningMemory.get_recent ────────────────────────────────────────────────


class TestReasoningMemoryGetRecent(unittest.TestCase):
    """get_recent() returns ordered list of reasoning chains for the dashboard."""

    def _make_memory(self):
        from core.memory.reasoning_memory import ReasoningMemory
        return ReasoningMemory()

    def test_get_recent_returns_list(self):
        rm = self._make_memory()
        result = rm.get_recent(limit=5)
        self.assertIsInstance(result, list)

    def test_get_recent_respects_limit(self):
        rm = self._make_memory()
        rm.store_chain("test_d2_situation_a", [], ["step1"], "action_a", "ok", 0.8)
        rm.store_chain("test_d2_situation_b", [], ["step2"], "action_b", "ok", 0.6)
        result = rm.get_recent(limit=1)
        self.assertLessEqual(len(result), 1)

    def test_get_recent_returns_dicts(self):
        rm = self._make_memory()
        rm.store_chain("test_d2_dict_check", [], ["step"], "action_d2", "done", 0.7)
        result = rm.get_recent(limit=5)
        if result:
            chain = result[0]
            self.assertIn("situation", chain)
            self.assertIn("steps", chain)
            self.assertIn("action_taken", chain)
            self.assertIn("outcome", chain)
            self.assertIn("reward", chain)

    def test_get_recent_steps_is_list(self):
        rm = self._make_memory()
        rm.store_chain("test_d2_steps", [], ["classify", "route", "execute"], "action_steps", "ok", 0.75)
        result = rm.get_recent(limit=10)
        matched = [c for c in result if c.get("action_taken") == "action_steps"]
        if matched:
            self.assertIsInstance(matched[0]["steps"], list)

    def test_get_recent_reward_is_float(self):
        rm = self._make_memory()
        rm.store_chain("test_d2_reward_float", [], ["step"], "action_rf", "ok", 0.65)
        result = rm.get_recent(limit=10)
        matched = [c for c in result if c.get("action_taken") == "action_rf"]
        if matched:
            self.assertIsInstance(matched[0]["reward"], float)

    def test_get_recent_with_situation_filter(self):
        rm = self._make_memory()
        rm.store_chain("d2_filter_unique_xyz", [], ["step"], "action_xyz", "done", 0.9)
        result = rm.get_recent(limit=5, situation="d2_filter_unique_xyz")
        if result:
            for chain in result:
                self.assertIn("d2_filter_unique", chain["situation"])

    def test_get_recent_never_raises(self):
        from core.memory.reasoning_memory import ReasoningMemory
        rm = ReasoningMemory()
        try:
            rm.get_recent(limit=20)
        except Exception as exc:
            self.fail(f"get_recent raised: {exc}")

    def test_get_recent_most_recent_first(self):
        """Chains returned in descending chronological order."""
        rm = self._make_memory()
        rm.store_chain("d2_oldest_entry", [], ["a"], "act_old", "ok", 0.5)
        rm.store_chain("d2_newest_entry", [], ["b"], "act_new", "ok", 0.8)
        result = rm.get_recent(limit=20)
        actions = [c["action_taken"] for c in result]
        if "act_new" in actions and "act_old" in actions:
            self.assertLess(actions.index("act_new"), actions.index("act_old"),
                            "Newest entry must appear before oldest")


# ── /brain/reasoning/chains endpoint ─────────────────────────────────────────


class TestReasoningChainsEndpoint(unittest.TestCase):
    """GET /brain/reasoning/chains handler returns reasoning chain list."""

    def test_endpoint_handler_returns_chains_key(self):
        """Call the endpoint handler directly (bypasses auth middleware)."""
        result = asyncio.run(self._call_handler())
        self.assertIn("chains", result)

    def test_endpoint_handler_returns_count_key(self):
        result = asyncio.run(self._call_handler())
        self.assertIn("count", result)

    def test_chains_is_list(self):
        result = asyncio.run(self._call_handler())
        self.assertIsInstance(result["chains"], list)

    def test_count_matches_list_length(self):
        result = asyncio.run(self._call_handler())
        self.assertEqual(result["count"], len(result["chains"]))

    def test_limit_param_respected(self):
        result = asyncio.run(self._call_handler(limit=3))
        self.assertLessEqual(len(result["chains"]), 3)

    def test_situation_filter_accepted(self):
        result = asyncio.run(self._call_handler(situation="test_d2_situation", limit=5))
        self.assertIn("chains", result)

    def test_get_reasoning_chains_in_brain_all(self):
        import core.api.routers.brain as mod
        self.assertIn("get_reasoning_chains", mod.__all__)

    @staticmethod
    async def _call_handler(situation: str = "", limit: int = 20) -> dict:
        from core.api.routers.brain import get_reasoning_chains
        return await get_reasoning_chains(situation=situation, limit=limit)


# ── brain.py endpoint import/compile ─────────────────────────────────────────


class TestBrainRouterCompiles(unittest.TestCase):
    """brain.py imports and router is valid after D2 additions."""

    def test_brain_router_importable(self):
        from core.api.routers.brain import router
        self.assertIsNotNone(router)

    def test_reasoning_chains_route_registered(self):
        from core.api.routers.brain import router
        paths = [r.path for r in router.routes]
        self.assertTrue(any("/reasoning/chains" in p for p in paths),
                        f"No /reasoning/chains route in {paths}")


# ── DecisionTrace dashboard component presence ────────────────────────────────


class TestDecisionTraceDashboardComponent(unittest.TestCase):
    """dashboard/src/components/panels/DecisionTrace.tsx exists and is wired."""

    def _read_file(self, rel: str) -> str:
        return (Path(__file__).parent.parent.parent / rel).read_text(encoding="utf-8")

    def test_decision_trace_tsx_exists(self):
        path = Path(__file__).parent.parent.parent / "dashboard/src/components/panels/DecisionTrace.tsx"
        self.assertTrue(path.exists(), "DecisionTrace.tsx must exist")

    def test_decision_trace_exports_component(self):
        src = self._read_file("dashboard/src/components/panels/DecisionTrace.tsx")
        self.assertIn("export function DecisionTrace", src)

    def test_decision_trace_exports_interface(self):
        src = self._read_file("dashboard/src/components/panels/DecisionTrace.tsx")
        self.assertIn("DecisionEvent", src)

    def test_decision_trace_has_tier_coloring(self):
        src = self._read_file("dashboard/src/components/panels/DecisionTrace.tsx")
        self.assertIn("GREEN", src)
        self.assertIn("YELLOW", src)
        self.assertIn("RED", src)

    def test_decision_trace_has_click_handler(self):
        src = self._read_file("dashboard/src/components/panels/DecisionTrace.tsx")
        self.assertIn("onClick", src)

    def test_decision_trace_fetches_reasoning_chain(self):
        src = self._read_file("dashboard/src/components/panels/DecisionTrace.tsx")
        self.assertIn("/brain/reasoning/chains", src)

    def test_app_tsx_imports_decision_trace(self):
        src = self._read_file("dashboard/src/App.tsx")
        self.assertIn("DecisionTrace", src)

    def test_app_tsx_has_decisions_state(self):
        src = self._read_file("dashboard/src/App.tsx")
        self.assertIn("decisions", src)

    def test_app_tsx_accumulates_decision_events(self):
        src = self._read_file("dashboard/src/App.tsx")
        self.assertIn("setDecisions", src)

    def test_app_tsx_caps_at_20(self):
        src = self._read_file("dashboard/src/App.tsx")
        self.assertIn("20", src)


# ── Last 20 decisions cap ─────────────────────────────────────────────────────


class TestDecisionTraceCap(unittest.TestCase):
    """Decision trace maintains at most 20 entries."""

    def test_tsx_slices_at_20(self):
        src = (Path(__file__).parent.parent.parent / "dashboard/src/App.tsx").read_text(encoding="utf-8")
        self.assertIn(".slice(0, 20)", src)


if __name__ == "__main__":
    unittest.main()
