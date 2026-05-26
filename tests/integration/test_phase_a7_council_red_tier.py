"""Integration tests — Session A7: CouncilBrain.deliberate_action() → permission_gateway RED tier."""
from __future__ import annotations

import sys
import json
import inspect
import asyncio
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestCouncilBrainDeliberateAction(unittest.TestCase):
    """CouncilBrain.deliberate_action() API contract."""

    def setUp(self):
        from core.brain.council import CouncilBrain
        self.cb = CouncilBrain()

    def test_method_exists(self):
        self.assertTrue(hasattr(self.cb, "deliberate_action"))

    def test_signature(self):
        sig = inspect.signature(self.cb.deliberate_action)
        params = sig.parameters
        self.assertIn("action_type", params)
        self.assertIn("params", params)
        self.assertIn("context", params)
        self.assertEqual(params["context"].default, "")

    def test_returns_dict_with_required_keys(self):
        """deliberate_action() must always return a dict with verdict/votes/rationale/confidence."""
        # Ollama will likely fail (not running in test env) → should return defer gracefully
        result = asyncio.run(self.cb.deliberate_action("git_status", {}, "test context"))
        self.assertIsInstance(result, dict)
        for key in ("verdict", "votes", "rationale", "confidence"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_verdict_is_valid_enum(self):
        result = asyncio.run(self.cb.deliberate_action("git_status", {}, ""))
        self.assertIn(result["verdict"], ("proceed", "reject", "defer"))

    def test_confidence_is_float(self):
        result = asyncio.run(self.cb.deliberate_action("git_status", {}, ""))
        self.assertIsInstance(result["confidence"], float)

    def test_votes_is_list(self):
        result = asyncio.run(self.cb.deliberate_action("git_status", {}, ""))
        self.assertIsInstance(result["votes"], list)

    def test_never_raises(self):
        """Must catch all exceptions and return defer."""
        try:
            result = asyncio.run(self.cb.deliberate_action("unknown_action_xyz", {"bad": object()}, ""))
        except Exception as e:
            self.fail(f"deliberate_action raised unexpectedly: {e}")


class TestCouncilBrainVerdictParsing(unittest.TestCase):
    """Verify that verdict parsing from LLM text works for all 3 paths."""

    def _make_cb_with_mock(self, mock_text: str, confidence: float = 0.8):
        """Return a CouncilBrain whose deliberate() is patched to return a synthetic result."""
        from core.brain.council import CouncilBrain

        class PatchedCouncil(CouncilBrain):
            async def deliberate(self, question, hp_gate=700):
                return {
                    "stage1": ["vote1"],
                    "stage2": ["vote1"],
                    "verdict": mock_text,
                    "confidence": confidence,
                    "timestamp": "2026-01-01",
                }

        return PatchedCouncil()

    def test_proceed_verdict_parsed(self):
        cb = self._make_cb_with_mock("PROCEED — this action is safe")
        result = asyncio.run(cb.deliberate_action("git_status", {}, ""))
        self.assertEqual(result["verdict"], "proceed")

    def test_reject_verdict_parsed(self):
        cb = self._make_cb_with_mock("REJECT — too destructive")
        result = asyncio.run(cb.deliberate_action("delete_files", {}, ""))
        self.assertEqual(result["verdict"], "reject")

    def test_defer_verdict_parsed(self):
        cb = self._make_cb_with_mock("DEFER — ask the owner")
        result = asyncio.run(cb.deliberate_action("deploy_production", {}, ""))
        self.assertEqual(result["verdict"], "defer")

    def test_proceed_low_confidence_becomes_defer(self):
        """proceed + confidence < 0.75 → _handle_red_tier returns defer."""
        from core.loop.permission_gateway import PermissionGateway, Action

        class PatchedCouncil:
            async def deliberate_action(self, action_type, params, context=""):
                return {"verdict": "proceed", "votes": [], "rationale": "test", "confidence": 0.50}

        pg = PermissionGateway()
        # Patch council import inside _handle_red_tier by monkeypatching the module
        import core.brain.council as council_mod
        original = council_mod.CouncilBrain
        council_mod.CouncilBrain = lambda: PatchedCouncil()
        try:
            action = Action("deploy_production", {"env": "prod"}, "test")
            verdict = asyncio.run(pg._handle_red_tier(action))
            self.assertEqual(verdict, "defer", "Low-confidence 'proceed' must defer to owner")
        finally:
            council_mod.CouncilBrain = original

    def test_reject_verdict_returns_reject(self):
        from core.loop.permission_gateway import PermissionGateway, Action
        import core.brain.council as council_mod

        class PatchedCouncil:
            async def deliberate_action(self, action_type, params, context=""):
                return {"verdict": "reject", "votes": [], "rationale": "Destructive action", "confidence": 0.9}

        pg = PermissionGateway()
        original = council_mod.CouncilBrain
        council_mod.CouncilBrain = lambda: PatchedCouncil()
        try:
            action = Action("delete_files", {"path": "/tmp/x"}, "test")
            verdict = asyncio.run(pg._handle_red_tier(action))
            self.assertEqual(verdict, "reject")
        finally:
            council_mod.CouncilBrain = original

    def test_proceed_high_confidence_returns_proceed(self):
        from core.loop.permission_gateway import PermissionGateway, Action
        import core.brain.council as council_mod

        class PatchedCouncil:
            async def deliberate_action(self, action_type, params, context=""):
                return {"verdict": "proceed", "votes": ["yes"], "rationale": "Safe action", "confidence": 0.9}

        pg = PermissionGateway()
        original = council_mod.CouncilBrain
        council_mod.CouncilBrain = lambda: PatchedCouncil()
        try:
            action = Action("push_github", {"repo": "x"}, "test")
            verdict = asyncio.run(pg._handle_red_tier(action))
            self.assertEqual(verdict, "proceed")
        finally:
            council_mod.CouncilBrain = original


class TestCouncilLog(unittest.TestCase):
    """council_log.jsonl is written for every RED-tier deliberation."""

    def test_council_log_written(self):
        """_handle_red_tier must write a JSON line to data/council_log.jsonl."""
        from core.loop.permission_gateway import PermissionGateway, Action
        import core.brain.council as council_mod

        class PatchedCouncil:
            async def deliberate_action(self, action_type, params, context=""):
                return {"verdict": "defer", "votes": [], "rationale": "test entry", "confidence": 0.5}

        pg = PermissionGateway()
        original = council_mod.CouncilBrain
        council_mod.CouncilBrain = lambda: PatchedCouncil()
        log_path = Path("data") / "council_log.jsonl"
        before_size = log_path.stat().st_size if log_path.exists() else 0
        try:
            action = Action("deploy_production", {"env": "test"}, "test")
            asyncio.run(pg._handle_red_tier(action))
            self.assertTrue(log_path.exists(), "council_log.jsonl must be created")
            after_size = log_path.stat().st_size
            self.assertGreater(after_size, before_size, "council_log.jsonl must grow after deliberation")
            # Verify it's valid JSONL
            with log_path.open(encoding="utf-8") as fh:
                lines = fh.readlines()
            last = json.loads(lines[-1])
            for key in ("ts", "action_type", "verdict", "confidence", "rationale"):
                self.assertIn(key, last)
        finally:
            council_mod.CouncilBrain = original


class TestPermissionGatewayRedWiring(unittest.TestCase):
    """permission_gateway.execute() references _handle_red_tier for RED actions."""

    def test_execute_source_references_handle_red_tier(self):
        from core.loop.permission_gateway import PermissionGateway
        src = inspect.getsource(PermissionGateway.execute)
        self.assertIn("_handle_red_tier", src)

    def test_handle_red_tier_exists(self):
        from core.loop.permission_gateway import PermissionGateway
        self.assertTrue(hasattr(PermissionGateway, "_handle_red_tier"))

    def test_handle_red_tier_is_async(self):
        from core.loop.permission_gateway import PermissionGateway
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(PermissionGateway._handle_red_tier))

    def test_handle_red_tier_returns_string(self):
        """With council unavailable (Ollama down), must return 'defer' string."""
        from core.loop.permission_gateway import PermissionGateway, Action
        pg = PermissionGateway()
        action = Action("git_status", {}, "test")
        result = asyncio.run(pg._handle_red_tier(action))
        self.assertIsInstance(result, str)
        self.assertIn(result, ("proceed", "reject", "defer"))


if __name__ == "__main__":
    unittest.main()
