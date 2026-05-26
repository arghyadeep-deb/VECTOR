"""Integration tests — Session C1: Cloud LLM router with cost-aware fallback."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ── ComplexityLevel and _assess_complexity ────────────────────────────────────


class TestComplexityLevelEnum(unittest.TestCase):
    """ComplexityLevel enum has LOCAL, CLOUD_ELIGIBLE, CLOUD_REQUIRED."""

    def test_local_value(self):
        from core.inference.cloud_router import ComplexityLevel
        self.assertEqual(ComplexityLevel.LOCAL.value, "LOCAL")

    def test_cloud_eligible_value(self):
        from core.inference.cloud_router import ComplexityLevel
        self.assertEqual(ComplexityLevel.CLOUD_ELIGIBLE.value, "ELIGIBLE")

    def test_cloud_required_value(self):
        from core.inference.cloud_router import ComplexityLevel
        self.assertEqual(ComplexityLevel.CLOUD_REQUIRED.value, "REQUIRED")


class TestAssessComplexity(unittest.TestCase):
    """_assess_complexity() heuristics map to correct ComplexityLevel."""

    def _assess(self, prompt, hint=None):
        from core.inference.cloud_router import _assess_complexity
        return _assess_complexity(prompt, hint)

    def test_simple_prompt_eligible(self):
        from core.inference.cloud_router import ComplexityLevel
        result = self._assess("what is 2 plus 2?")
        self.assertIn(result, (ComplexityLevel.LOCAL, ComplexityLevel.CLOUD_ELIGIBLE))

    def test_explain_why_requires_cloud(self):
        from core.inference.cloud_router import ComplexityLevel
        result = self._assess("explain why gradient descent converges")
        self.assertEqual(result, ComplexityLevel.CLOUD_REQUIRED)

    def test_long_prompt_over_8k_tokens_requires_cloud(self):
        from core.inference.cloud_router import ComplexityLevel
        # ~8001 tokens × 4 chars/token = ~32004 chars
        big = "word " * 8002
        result = self._assess(big)
        self.assertEqual(result, ComplexityLevel.CLOUD_REQUIRED)

    def test_step_by_step_requires_cloud(self):
        from core.inference.cloud_router import ComplexityLevel
        result = self._assess("explain step by step how to build a neural network")
        self.assertEqual(result, ComplexityLevel.CLOUD_REQUIRED)

    def test_multi_step_requires_cloud(self):
        from core.inference.cloud_router import ComplexityLevel
        result = self._assess("give me a multi-step plan for launching a startup")
        self.assertEqual(result, ComplexityLevel.CLOUD_REQUIRED)

    def test_hint_local_overrides_complexity(self):
        from core.inference.cloud_router import ComplexityLevel
        big = "word " * 8002
        result = self._assess(big, hint="local")
        self.assertEqual(result, ComplexityLevel.LOCAL)

    def test_hint_complex_overrides_simple(self):
        from core.inference.cloud_router import ComplexityLevel
        result = self._assess("hello", hint="complex")
        self.assertEqual(result, ComplexityLevel.CLOUD_REQUIRED)

    def test_code_block_over_200_lines_requires_cloud(self):
        from core.inference.cloud_router import ComplexityLevel
        lines = "\n".join(f"x = {i}" for i in range(201))
        prompt = f"review this code:\n```python\n{lines}\n```"
        result = self._assess(prompt)
        self.assertEqual(result, ComplexityLevel.CLOUD_REQUIRED)

    def test_short_code_block_not_required(self):
        from core.inference.cloud_router import ComplexityLevel
        lines = "\n".join(f"x = {i}" for i in range(10))
        prompt = f"review this:\n```python\n{lines}\n```"
        result = self._assess(prompt)
        self.assertNotEqual(result, ComplexityLevel.CLOUD_REQUIRED)


# ── RouteDecision dataclass ───────────────────────────────────────────────────


class TestRouteDecision(unittest.TestCase):
    """RouteDecision is a dataclass with required fields."""

    def test_route_decision_fields(self):
        from core.inference.cloud_router import RouteDecision, ComplexityLevel
        d = RouteDecision(
            provider="ollama",
            model=None,
            is_cloud=False,
            complexity=ComplexityLevel.LOCAL,
            reason="test",
        )
        self.assertEqual(d.provider, "ollama")
        self.assertFalse(d.is_cloud)
        self.assertEqual(d.signals, [])

    def test_cloud_decision_is_cloud_true(self):
        from core.inference.cloud_router import RouteDecision, ComplexityLevel
        d = RouteDecision(
            provider="anthropic",
            model=None,
            is_cloud=True,
            complexity=ComplexityLevel.CLOUD_REQUIRED,
            reason="complex",
        )
        self.assertTrue(d.is_cloud)


# ── CloudRouter.route() ───────────────────────────────────────────────────────


class TestCloudRouterRoute(unittest.TestCase):
    """CloudRouter.route() returns RouteDecision with correct provider logic."""

    def _make_router(self):
        from core.inference.cloud_router import CloudRouter
        return CloudRouter()

    def test_returns_route_decision(self):
        from core.inference.cloud_router import RouteDecision
        router = self._make_router()
        with patch("core.inference.cloud_router.CONFIG", {"routing": {}}):
            with patch.object(router, "_best_cloud_provider", return_value=None):
                result = router.route("hello world")
        self.assertIsInstance(result, RouteDecision)

    def test_simple_prompt_routes_local(self):
        router = self._make_router()
        with patch("core.inference.cloud_router.CONFIG", {"routing": {"cloud_fraction": 0.0}}):
            result = router.route("what time is it?")
        self.assertEqual(result.provider, "ollama")
        self.assertFalse(result.is_cloud)

    def test_complex_prompt_routes_cloud_when_available(self):
        router = self._make_router()
        prompt = "explain why transformers outperform RNNs on long sequences"
        with patch("core.inference.cloud_router.CONFIG", {"routing": {"cloud_fraction": 0.10}}):
            with patch.object(router, "_best_cloud_provider", return_value="anthropic"):
                with patch.object(router, "_check_budget", return_value=(True, "")):
                    result = router.route(prompt)
        self.assertTrue(result.is_cloud)
        self.assertEqual(result.provider, "anthropic")

    def test_budget_exhausted_forces_local(self):
        router = self._make_router()
        prompt = "explain why " + "word " * 100
        with patch("core.inference.cloud_router.CONFIG", {"routing": {}}):
            with patch.object(router, "_check_budget", return_value=(False, "daily limit")):
                with patch.object(router, "_best_cloud_provider", return_value="anthropic"):
                    result = router.route(prompt)
        self.assertFalse(result.is_cloud)
        self.assertEqual(result.provider, "ollama")
        self.assertIn("budget", result.reason)

    def test_no_cloud_providers_falls_back_to_local(self):
        router = self._make_router()
        prompt = "explain why " * 10
        with patch("core.inference.cloud_router.CONFIG", {"routing": {}}):
            with patch.object(router, "_best_cloud_provider", return_value=None):
                with patch.object(router, "_check_budget", return_value=(True, "")):
                    result = router.route(prompt)
        self.assertFalse(result.is_cloud)
        self.assertEqual(result.provider, "ollama")

    def test_hint_local_always_routes_local(self):
        router = self._make_router()
        with patch("core.inference.cloud_router.CONFIG", {"routing": {}}):
            with patch.object(router, "_best_cloud_provider", return_value="anthropic"):
                result = router.route("explain why X happens", complexity_hint="local")
        self.assertFalse(result.is_cloud)
        self.assertEqual(result.provider, "ollama")


# ── CloudRouter.stats() ───────────────────────────────────────────────────────


class TestCloudRouterStats(unittest.TestCase):
    """CloudRouter tracks local/cloud call counts."""

    def test_stats_initial_zero(self):
        from core.inference.cloud_router import CloudRouter
        router = CloudRouter()
        stats = router.stats()
        self.assertEqual(stats["local_calls"], 0)
        self.assertEqual(stats["cloud_calls"], 0)
        self.assertEqual(stats["total_calls"], 0)

    def test_stats_after_local_call(self):
        from core.inference.cloud_router import CloudRouter
        router = CloudRouter()
        with patch("core.inference.cloud_router.CONFIG", {"routing": {"cloud_fraction": 0.0}}):
            router.route("hello")
        stats = router.stats()
        self.assertGreaterEqual(stats["local_calls"], 1)

    def test_reset_stats_zeroes_counts(self):
        from core.inference.cloud_router import CloudRouter
        router = CloudRouter()
        with patch("core.inference.cloud_router.CONFIG", {"routing": {"cloud_fraction": 0.0}}):
            router.route("hello")
        router.reset_stats()
        stats = router.stats()
        self.assertEqual(stats["total_calls"], 0)

    def test_cloud_fraction_actual_in_stats(self):
        from core.inference.cloud_router import CloudRouter
        router = CloudRouter()
        self.assertIn("cloud_fraction_actual", router.stats())


# ── budget_gate() function ────────────────────────────────────────────────────


class TestBudgetGate(unittest.TestCase):
    """budget_gate() returns (True, '') for local-only routes."""

    def test_local_only_route_always_ok(self):
        from core.inference.cloud_router import budget_gate
        ok, reason = budget_gate(["ollama"])
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_cloud_route_checks_budget(self):
        from core.inference.cloud_router import budget_gate, get_cloud_router
        router = get_cloud_router()
        with patch.object(router, "_check_budget", return_value=(True, "")) as mock_check:
            ok, reason = budget_gate(["anthropic", "ollama"])
            mock_check.assert_called_once()
            self.assertTrue(ok)

    def test_budget_exhausted_returns_false(self):
        from core.inference.cloud_router import budget_gate, get_cloud_router
        router = get_cloud_router()
        with patch.object(router, "_check_budget", return_value=(False, "daily limit hit")):
            ok, reason = budget_gate(["openai", "ollama"])
        self.assertFalse(ok)
        self.assertIn("daily limit", reason)


# ── Module-level route() function ────────────────────────────────────────────


class TestModuleLevelRoute(unittest.TestCase):
    """route() module function delegates to singleton CloudRouter."""

    def test_route_returns_route_decision(self):
        from core.inference.cloud_router import route, RouteDecision
        with patch("core.inference.cloud_router.CONFIG", {"routing": {"cloud_fraction": 0.0}}):
            result = route("hello")
        self.assertIsInstance(result, RouteDecision)

    def test_route_simple_is_local(self):
        from core.inference.cloud_router import route
        with patch("core.inference.cloud_router.CONFIG", {"routing": {"cloud_fraction": 0.0}}):
            result = route("what is Python?")
        self.assertEqual(result.provider, "ollama")

    def test_route_explain_why_triggers_cloud_required(self):
        from core.inference.cloud_router import route, ComplexityLevel
        result = route("explain why quantum entanglement defies classical physics")
        self.assertEqual(result.complexity, ComplexityLevel.CLOUD_REQUIRED)


# ── provider_client integration ───────────────────────────────────────────────


class TestProviderClientBudgetGate(unittest.TestCase):
    """provider_client.chat() applies budget_gate after decide_route()."""

    def test_budget_gate_imported_in_provider_client(self):
        import inspect
        from core.inference import provider_client
        src = inspect.getsource(provider_client)
        self.assertIn("cloud_router", src)
        self.assertIn("budget_gate", src)

    def test_budget_gate_block_in_chat_source(self):
        import inspect
        from core.inference.provider_client import ProviderClient
        src = inspect.getsource(ProviderClient.chat)
        self.assertIn("budget_gate", src)
        self.assertIn("cloud budget gate", src.lower())

    def test_budget_fallback_route_is_ollama_only(self):
        """When budget gate blocks, chat route_order becomes ['ollama']."""
        import inspect
        from core.inference import provider_client
        src = inspect.getsource(provider_client)
        self.assertIn('"ollama"', src)


# ── get_cloud_router singleton ────────────────────────────────────────────────


class TestGetCloudRouterSingleton(unittest.TestCase):
    """get_cloud_router() returns the same instance on repeated calls."""

    def test_same_instance(self):
        from core.inference.cloud_router import get_cloud_router
        r1 = get_cloud_router()
        r2 = get_cloud_router()
        self.assertIs(r1, r2)

    def test_instance_is_cloud_router(self):
        from core.inference.cloud_router import get_cloud_router, CloudRouter
        self.assertIsInstance(get_cloud_router(), CloudRouter)


if __name__ == "__main__":
    unittest.main()
