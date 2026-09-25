"""Integration tests — Session A7: CouncilBrain.deliberate_action() → permission_gateway RED tier."""
from __future__ import annotations

import json
import inspect
import asyncio
import unittest
from unittest.mock import patch
from pathlib import Path


def _patched_council(verdict_text: str, confidence: float = 0.9):
    """Return a CouncilBrain subclass whose deliberate() is pre-baked (no Ollama).

    2026-09-24 (external review, Phase 2): deliberate()'s real contract
    changed -- it now returns an ALREADY-PARSED "verdict"
    (proceed/reject/defer) plus the raw synthesis text under
    "verdict_text", instead of raw text under "verdict" for the caller to
    re-parse. This stub now extracts the keyword itself (same fail-closed
    logic as the real _parse_vote()) so existing call sites that pass a
    readable "PROCEED — this action is safe" string keep working."""
    from core.brain.council import CouncilBrain, _parse_vote

    class _Patched(CouncilBrain):
        async def deliberate(self, question, hp_gate=700):
            return {
                "stage1": ["vote1", "vote2"],
                "votes": [_parse_vote(verdict_text)] * 2,
                "verdict": _parse_vote(verdict_text),
                "verdict_text": verdict_text,
                "confidence": confidence,
                "timestamp": "2026-01-01T00:00:00",
            }

    return _Patched()


class TestCouncilBrainDeliberateActionSignature(unittest.TestCase):
    """deliberate_action() signature and static contract — no Ollama needed."""

    def setUp(self):
        from core.brain.council import CouncilBrain
        self.cb = CouncilBrain()

    def test_method_exists(self):
        self.assertTrue(hasattr(self.cb, "deliberate_action"))

    def test_is_coroutine(self):
        self.assertTrue(inspect.iscoroutinefunction(self.cb.deliberate_action))

    def test_signature_has_required_params(self):
        sig = inspect.signature(self.cb.deliberate_action)
        for p in ("action_type", "params", "context"):
            self.assertIn(p, sig.parameters)

    def test_context_defaults_to_empty_string(self):
        sig = inspect.signature(self.cb.deliberate_action)
        self.assertEqual(sig.parameters["context"].default, "")


class TestCouncilBrainVerdictParsing(unittest.TestCase):
    """Verify all 3 verdict paths with a patched council (no Ollama)."""

    def test_proceed_parsed(self):
        cb = _patched_council("PROCEED — this action is safe")
        result = asyncio.run(cb.deliberate_action("git_status", {}, "ctx"))
        self.assertEqual(result["verdict"], "proceed")

    def test_reject_parsed(self):
        cb = _patched_council("REJECT — too destructive")
        result = asyncio.run(cb.deliberate_action("delete_files", {}, "ctx"))
        self.assertEqual(result["verdict"], "reject")

    def test_defer_parsed(self):
        cb = _patched_council("DEFER — ask the owner")
        result = asyncio.run(cb.deliberate_action("deploy_production", {}, "ctx"))
        self.assertEqual(result["verdict"], "defer")

    def test_result_has_required_keys(self):
        cb = _patched_council("PROCEED — safe")
        result = asyncio.run(cb.deliberate_action("git_status", {}, ""))
        for key in ("verdict", "votes", "rationale", "confidence"):
            self.assertIn(key, result)

    def test_votes_is_list(self):
        cb = _patched_council("PROCEED")
        result = asyncio.run(cb.deliberate_action("git_status", {}, ""))
        self.assertIsInstance(result["votes"], list)

    def test_confidence_is_float(self):
        cb = _patched_council("DEFER", confidence=0.6)
        result = asyncio.run(cb.deliberate_action("git_status", {}, ""))
        self.assertIsInstance(result["confidence"], float)


class TestHandleRedTierVerdictPaths(unittest.TestCase):
    """_handle_red_tier returns correct string for each verdict path."""

    def _pg_with_council(self, verdict_text: str, confidence: float = 0.9):
        from core.loop.permission_gateway import PermissionGateway
        import core.brain.council as council_mod
        pg = PermissionGateway()
        cb = _patched_council(verdict_text, confidence)
        council_mod.CouncilBrain = lambda: cb
        return pg, council_mod

    def test_proceed_high_confidence_defers_when_not_allowlisted(self):
        """A confident council "proceed" never auto-executes a RED action on its own (audit F-9).

        COUNCIL_AUTO_PROCEED_ALLOWED is empty by design, and push_github is also OWNER_APPROVAL_ONLY, so
        the owner is still asked. Loosening this is a policy decision, not something a test should assume.
        """
        from core.loop.permission_gateway import Action, COUNCIL_AUTO_PROCEED_ALLOWED
        import core.brain.council as council_mod
        original = council_mod.CouncilBrain
        pg, _ = self._pg_with_council("PROCEED — safe", confidence=0.9)
        try:
            self.assertEqual(COUNCIL_AUTO_PROCEED_ALLOWED, frozenset())
            action = Action("push_github", {"repo": "x"}, "test")
            verdict = asyncio.run(pg._handle_red_tier(action))
            self.assertEqual(verdict, "defer")
        finally:
            council_mod.CouncilBrain = original

    def test_proceed_high_confidence_returns_proceed_only_when_allowlisted(self):
        """The council's proceed path still works for an action the owner has explicitly allowlisted."""
        from core.loop.permission_gateway import Action
        import core.brain.council as council_mod
        import core.loop.permission_gateway as gw
        original = council_mod.CouncilBrain
        pg, _ = self._pg_with_council("PROCEED — safe", confidence=0.9)
        try:
            with patch.object(gw, "COUNCIL_AUTO_PROCEED_ALLOWED", frozenset({"some_red_action"})):
                verdict = asyncio.run(pg._handle_red_tier(Action("some_red_action", {}, "test")))
                self.assertEqual(verdict, "proceed")
        finally:
            council_mod.CouncilBrain = original

    def test_proceed_low_confidence_defers(self):
        from core.loop.permission_gateway import Action
        import core.brain.council as council_mod
        original = council_mod.CouncilBrain
        pg, _ = self._pg_with_council("PROCEED — unsure", confidence=0.50)
        try:
            action = Action("deploy_production", {"env": "prod"}, "test")
            verdict = asyncio.run(pg._handle_red_tier(action))
            self.assertEqual(verdict, "defer", "Low-confidence proceed must defer")
        finally:
            council_mod.CouncilBrain = original

    def test_reject_returns_reject(self):
        from core.loop.permission_gateway import Action
        import core.brain.council as council_mod
        original = council_mod.CouncilBrain
        pg, _ = self._pg_with_council("REJECT — destructive", confidence=0.9)
        try:
            action = Action("delete_files", {"path": "/tmp"}, "test")
            verdict = asyncio.run(pg._handle_red_tier(action))
            self.assertEqual(verdict, "reject")
        finally:
            council_mod.CouncilBrain = original

    def test_defer_returns_defer(self):
        from core.loop.permission_gateway import Action
        import core.brain.council as council_mod
        original = council_mod.CouncilBrain
        pg, _ = self._pg_with_council("DEFER — ask owner", confidence=0.7)
        try:
            action = Action("send_email", {}, "test")
            verdict = asyncio.run(pg._handle_red_tier(action))
            self.assertEqual(verdict, "defer")
        finally:
            council_mod.CouncilBrain = original

    def test_exception_defers_gracefully(self):
        """If CouncilBrain raises, _handle_red_tier must return 'defer'."""
        from core.loop.permission_gateway import PermissionGateway, Action
        import core.brain.council as council_mod

        class Exploding:
            async def deliberate_action(self, *a, **kw):
                raise RuntimeError("Exploded")

        original = council_mod.CouncilBrain
        council_mod.CouncilBrain = lambda: Exploding()
        try:
            pg = PermissionGateway()
            action = Action("git_status", {}, "test")
            verdict = asyncio.run(pg._handle_red_tier(action))
            self.assertEqual(verdict, "defer")
        finally:
            council_mod.CouncilBrain = original


class TestCouncilLog(unittest.TestCase):
    """council_log.jsonl is written for each _handle_red_tier call."""

    def test_council_log_written(self):
        from core.loop.permission_gateway import PermissionGateway, Action
        import core.brain.council as council_mod

        cb = _patched_council("DEFER — log test", confidence=0.5)
        original = council_mod.CouncilBrain
        council_mod.CouncilBrain = lambda: cb
        from core.runtime_paths import data_path

        log_path = data_path("council_log.jsonl")
        before_size = log_path.stat().st_size if log_path.exists() else 0
        try:
            pg = PermissionGateway()
            action = Action("deploy_production", {"env": "test"}, "test")
            asyncio.run(pg._handle_red_tier(action))
            self.assertTrue(log_path.exists(), "council_log.jsonl must exist after _handle_red_tier")
            after_size = log_path.stat().st_size
            self.assertGreater(after_size, before_size, "Log must grow after deliberation")
            with log_path.open(encoding="utf-8") as fh:
                last = json.loads(fh.readlines()[-1])
            for key in ("ts", "action_type", "verdict", "confidence", "rationale"):
                self.assertIn(key, last, f"Log entry missing key: {key}")
        finally:
            council_mod.CouncilBrain = original

    def test_council_log_action_type_correct(self):
        from core.loop.permission_gateway import PermissionGateway, Action
        import core.brain.council as council_mod

        cb = _patched_council("REJECT — test", confidence=0.9)
        original = council_mod.CouncilBrain
        council_mod.CouncilBrain = lambda: cb
        try:
            pg = PermissionGateway()
            action = Action("delete_files_marker_a7", {"path": "/x"}, "test")
            asyncio.run(pg._handle_red_tier(action))
            from core.runtime_paths import data_path

            log_path = data_path("council_log.jsonl")
            with log_path.open(encoding="utf-8") as fh:
                last = json.loads(fh.readlines()[-1])
            self.assertEqual(last["action_type"], "delete_files_marker_a7")
        finally:
            council_mod.CouncilBrain = original


class TestPermissionGatewayWiring(unittest.TestCase):
    """execute() calls _handle_red_tier for RED actions."""

    def test_execute_references_handle_red_tier(self):
        from core.loop.permission_gateway import PermissionGateway
        src = inspect.getsource(PermissionGateway.execute)
        self.assertIn("_handle_red_tier", src)

    def test_handle_red_tier_is_async(self):
        from core.loop.permission_gateway import PermissionGateway
        self.assertTrue(inspect.iscoroutinefunction(PermissionGateway._handle_red_tier))

    def test_handle_red_tier_returns_string(self):
        from core.loop.permission_gateway import PermissionGateway, Action
        import core.brain.council as council_mod

        cb = _patched_council("DEFER")
        original = council_mod.CouncilBrain
        council_mod.CouncilBrain = lambda: cb
        try:
            pg = PermissionGateway()
            action = Action("git_status", {}, "test")
            result = asyncio.run(pg._handle_red_tier(action))
            self.assertIsInstance(result, str)
            self.assertIn(result, ("proceed", "reject", "defer"))
        finally:
            council_mod.CouncilBrain = original


if __name__ == "__main__":
    unittest.main()
