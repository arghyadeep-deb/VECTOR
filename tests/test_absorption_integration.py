"""Integration tests for absorbed VectorCode modules.

Verifies that 24+ modules imported from vector/VectorCode actually load
and expose their key public APIs without import errors.

Run:
    pytest tests/test_absorption_integration.py -v

These are LIGHTWEIGHT smoke tests — they don't exercise full functionality
(no live Ollama, no real GPU energy reading), they just confirm the wiring
holds end-to-end.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ── Tier 1 — novel-value modules ─────────────────────────────────────────────


class TestTelemetry:
    def test_telemetry_imports(self):
        from core.telemetry import (
            AggregatedStats, BatchMetrics, EnergyBatch,
            SteadyStateConfig, TelemetryAggregator, TelemetryStore,
            capabilities,
        )
        assert callable(capabilities)

    def test_capabilities_returns_dict(self):
        from core.telemetry import capabilities
        caps = capabilities()
        assert isinstance(caps, dict)
        # These keys must exist regardless of vendor support
        for k in ("gpu_monitor", "energy_monitor", "flops", "instrumented"):
            assert k in caps
            assert isinstance(caps[k], bool)

    def test_telemetry_store_can_open(self, tmp_path):
        from core.telemetry import TelemetryStore
        store = TelemetryStore(tmp_path / "test.db")
        assert (tmp_path / "test.db").exists()


class TestEvals:
    def test_evals_package_imports(self):
        import vectorcode.src.evals as evals_pkg
        assert evals_pkg is not None


class TestBench:
    def test_bench_package_imports(self):
        import vectorcode.src.bench as bench_pkg
        assert bench_pkg is not None


class TestSandbox:
    def test_sandbox_imports(self):
        import core.sandbox as sandbox_pkg
        assert sandbox_pkg is not None

    def test_runner_class_present(self):
        try:
            from core.sandbox.runner import SandboxRunner  # type: ignore[import]
        except ImportError:
            try:
                from core.sandbox import runner
                assert runner is not None
            except ImportError:
                pytest.skip("sandbox runner module not available")


class TestA2A:
    def test_a2a_package_imports(self):
        import vectorcode.src.a2a as a2a_pkg
        assert a2a_pkg is not None


# ── Tier 2 — gap fillers ─────────────────────────────────────────────────────


class TestScheduler:
    def test_scheduler_imports(self):
        import core.scheduler
        assert core.scheduler is not None


class TestLearning:
    def test_learning_imports(self):
        import vectorcode.src.learning
        assert vectorcode.src.learning is not None


class TestWorkflow:
    def test_workflow_imports(self):
        import vectorcode.src.workflow
        assert vectorcode.src.workflow is not None

    def test_vector_native_workflow_runner(self):
        from core.loop.workflow_runner import (
            WorkflowRunner, WorkflowTask, WorkflowResult, TaskResult,
            load_workflow_file, _toposort, _substitute,
        )
        # Cycle detection
        bad = [
            WorkflowTask(id="a", depends_on=["b"]),
            WorkflowTask(id="b", depends_on=["a"]),
        ]
        with pytest.raises(ValueError, match="cycle"):
            _toposort(bad)
        # Layer detection
        good = [
            WorkflowTask(id="a"),
            WorkflowTask(id="b"),
            WorkflowTask(id="c", depends_on=["a", "b"]),
        ]
        layers = _toposort(good)
        assert len(layers) == 2
        assert set(layers[0]) == {"a", "b"}
        assert layers[1] == ["c"]
        # Template substitution
        out = _substitute({"x": "hi {{a.value}}"}, {"a": {"value": 42}})
        assert out == {"x": "hi 42"}

    @pytest.mark.asyncio
    async def test_workflow_runner_smoke(self):
        from core.loop.workflow_runner import WorkflowRunner

        async def _a(**_): return {"value": 10}
        async def _b(**_): return {"value": 20}

        wf = {
            "name": "smoke",
            "tasks": [
                {"id": "a", "fn": _a},
                {"id": "b", "fn": _b},
            ],
        }
        runner = WorkflowRunner()
        result = await runner.run(wf)
        assert result.overall_status == "ok"
        assert result.get("a") == {"value": 10}
        assert result.get("b") == {"value": 20}


class TestRecipes:
    def test_recipes_imports(self):
        import vectorcode.src.recipes
        assert vectorcode.src.recipes is not None


# ── Tier 3 — extensions ──────────────────────────────────────────────────────


class TestSpeech:
    def test_speech_imports(self):
        import vectorcode.src.speech
        assert vectorcode.src.speech is not None


class TestConnectors:
    def test_connectors_imports(self):
        import vectorcode.src.connectors
        assert vectorcode.src.connectors is not None


class TestIntelligence:
    def test_intelligence_imports(self):
        import vectorcode.src.intelligence
        assert vectorcode.src.intelligence is not None


# ── Wiring tests — VECTOR-side integration ──────────────────────────────────


class TestVectorWiring:
    def test_ollama_safe_has_telemetry_helpers(self):
        from core.inference.ollama_safe import (
            chat, chat_stream, warm_models, WARM_POOL,
            _get_energy_monitor, _get_telemetry_store, _record_telemetry,
        )
        assert callable(chat)
        assert callable(_get_energy_monitor)
        assert isinstance(WARM_POOL, list)

    def test_ollama_safe_record_telemetry_no_op_safe(self):
        # Even with a None energy monitor and empty response, this MUST NOT raise
        from core.inference.ollama_safe import _record_telemetry
        _record_telemetry("vector-coder", 0.5, {}, None)  # should be a silent no-op

    def test_agent_registry_loads(self):
        from vectorcode.src.agents.registry import get_registry
        reg = get_registry()
        agents = reg.list_all()
        assert isinstance(agents, list)

    def test_slash_commands_registered(self):
        from vectorcode.src.vector_cli.commands import COMMAND_REGISTRY
        assert len(COMMAND_REGISTRY) > 0

    def test_hook_registry_loads(self):
        from vectorcode.src.hooks.registry import get_hook_registry, HookName
        reg = get_hook_registry()
        # At minimum, the registry should expose all enum values
        for h in HookName:
            handlers = reg.list_handlers(h)
            assert isinstance(handlers, list)


# ── Doctor command smoke ─────────────────────────────────────────────────────


class TestDoctorCommand:
    def test_doctor_imports(self):
        from vectorcode.src.vector_cli.doctor_cmd import (
            run_all_checks, CheckResult, check_python, check_disk, check_skills,
        )
        # Each individual check must return a CheckResult
        r = check_python()
        assert isinstance(r, CheckResult)
        assert r.status in {"ok", "warn", "fail", "info"}

    def test_doctor_run_all_returns_results(self):
        from vectorcode.src.vector_cli.doctor_cmd import run_all_checks
        results = run_all_checks()
        assert isinstance(results, list)
        assert len(results) > 5  # we have ~30 checks
        # No check should leak an exception — all return CheckResult
        for r in results:
            assert hasattr(r, "name") and hasattr(r, "status")


# ── Telemetry CLI smoke ──────────────────────────────────────────────────────


class TestTelemetryCommand:
    def test_telemetry_cli_imports(self):
        from vectorcode.src.vector_cli.telemetry_cmd import (
            main, cmd_stats, cmd_leaderboard, cmd_capabilities, _human_joules,
        )
        assert callable(main)

    def test_human_joules_formats(self):
        from vectorcode.src.vector_cli.telemetry_cmd import _human_joules
        assert _human_joules(0.001) == "1.0 mJ"
        assert "J" in _human_joules(50)
        assert "Wh" in _human_joules(7200)
