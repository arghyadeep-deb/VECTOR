"""Regression/wiring tests: ArchitectureBuilder, DataPrep, and ProgressTracker
must each implement a real `run(self, task: dict) -> dict` that branches on
`task["type"]` (the governor's real dispatch contract — see
core/city/governor.py: `task_type = task.get("type", "unknown")`) and routes
to their existing real methods.

Before this fix:
  - ArchitectureBuilder.run() always called generate_config() regardless of
    task["type"], ignoring design_architecture()/estimate_compute().
  - DataPrep.run() checked `hasattr(self, "prepare")` — a method that does
    not exist anywhere on DataPrep — so it silently always fell through to
    the no-op `{"status": "ok", "agent": self.name}` branch, never calling
    download_dataset()/preprocess_data()/tokenize_data().
  - ProgressTracker.run() always called generate_report() regardless of
    task["type"], ignoring start_run()/log_step()/get_progress().

session-scoped asyncio loop (pytest.ini: asyncio_mode=auto,
asyncio_default_fixture_loop_scope=session) — use `async def test_x():`
directly, never asyncio.run() inside a plain `def` test.
"""
from __future__ import annotations

import pytest

from core.city.agent_base import AgentBase
from districts.karpathy_lab.architecture_builder import ArchitectureBuilder
from districts.karpathy_lab.data_prep import DataPrep
from districts.karpathy_lab.progress_tracker import ProgressTracker


# ── AgentBase subclassing sanity ─────────────────────────────────────────────

def test_architecture_builder_subclasses_agent_base():
    assert issubclass(ArchitectureBuilder, AgentBase)


def test_data_prep_subclasses_agent_base():
    assert issubclass(DataPrep, AgentBase)


def test_progress_tracker_subclasses_agent_base():
    assert issubclass(ProgressTracker, AgentBase)


# ── ArchitectureBuilder ───────────────────────────────────────────────────────

@pytest.fixture
def architecture_builder():
    return ArchitectureBuilder()


async def test_architecture_builder_is_agent_base_instance(architecture_builder):
    assert isinstance(architecture_builder, AgentBase)


async def test_architecture_builder_run_routes_design_architecture(architecture_builder):
    result = await architecture_builder.run({
        "type": "design_architecture",
        "params": {"model_type": "transformer", "params": {"hidden_size": 1024, "num_layers": 8}},
    })
    assert result["status"] == "ok"
    assert result["type"] == "transformer"
    assert result["config"]["hidden_size"] == 1024


async def test_architecture_builder_run_routes_generate_config(architecture_builder):
    arch = architecture_builder.design_architecture("transformer", {"hidden_size": 512, "num_layers": 4})
    result = await architecture_builder.run({
        "type": "generate_config",
        "params": {"architecture": arch},
    })
    assert result["status"] == "ok"
    assert "training" in result
    assert "learning_rate" in result["training"]


async def test_architecture_builder_run_routes_estimate_compute(architecture_builder):
    # hidden_size/num_layers large enough that parameters_billion (rounded to
    # 2 decimals by the real estimate_compute()) doesn't round to 0.0 — a
    # tiny config like hidden_size=512/num_layers=4 computes to ~0.0042B,
    # which legitimately rounds to 0.0 and isn't a routing bug.
    arch = architecture_builder.design_architecture("transformer", {"hidden_size": 2048, "num_layers": 24})
    result = await architecture_builder.run({
        "type": "estimate_compute",
        "params": {"architecture": arch},
    })
    assert result["status"] == "ok"
    assert "parameters_billion" in result
    assert result["parameters_billion"] > 0


async def test_architecture_builder_run_unhandled_type_returns_structured_error(architecture_builder):
    result = await architecture_builder.run({"type": "nonexistent_type", "params": {}})
    assert result["status"] == "error"
    assert "nonexistent_type" in result["error"]
    assert "supported" in result


# ── DataPrep ──────────────────────────────────────────────────────────────────

@pytest.fixture
def data_prep():
    return DataPrep()


async def test_data_prep_is_agent_base_instance(data_prep):
    assert isinstance(data_prep, AgentBase)


async def test_data_prep_has_no_prepare_method():
    """The old run() guarded on hasattr(self, "prepare") — that method never
    existed on this class, so the guard was always False and run() always
    fell through to a no-op stub. Document that fact explicitly so nobody
    re-introduces the dead branch."""
    assert not hasattr(DataPrep(), "prepare")


async def test_data_prep_run_routes_preprocess_data(data_prep, tmp_path):
    src = tmp_path / "input.txt"
    src.write_text("a line that is definitely long enough to survive the filter\nshort\n", encoding="utf-8")
    out = tmp_path / "output.txt"

    result = await data_prep.run({
        "type": "preprocess_data",
        "params": {"input_path": str(src), "output_path": str(out)},
    })
    assert result["status"] == "success"
    assert "cleaned_lines" in result
    assert out.exists()


async def test_data_prep_run_routes_tokenize_data(data_prep, tmp_path):
    text_path = tmp_path / "corpus.txt"
    text_path.write_text("hello world hello vector", encoding="utf-8")

    result = await data_prep.run({
        "type": "tokenize_data",
        "params": {"text_path": str(text_path), "vocab_size": 64},
    })
    assert result["status"] == "success"
    assert "total_tokens" in result


async def test_data_prep_run_routes_download_dataset(data_prep, monkeypatch):
    """Avoid a real network call — point at a dataset name that already
    exists on disk by faking dest.exists() via a pre-created file."""
    monkeypatch.setattr(DataPrep, "_download_with_progress", lambda self, url, dest: True)
    result = await data_prep.run({
        "type": "download_dataset",
        "params": {"dataset_name": "tiny_shakespeare"},
    })
    assert result["status"] in ("downloaded", "already_exists")
    assert result["dataset"] == "tiny_shakespeare"


async def test_data_prep_run_unhandled_type_returns_structured_error(data_prep):
    result = await data_prep.run({"type": "made_up_type", "params": {}})
    assert result["status"] == "error"
    assert "made_up_type" in result["error"]
    assert "supported" in result


# ── ProgressTracker ───────────────────────────────────────────────────────────

@pytest.fixture
def progress_tracker():
    return ProgressTracker()


async def test_progress_tracker_is_agent_base_instance(progress_tracker):
    assert isinstance(progress_tracker, AgentBase)


async def test_progress_tracker_run_routes_start_run(progress_tracker):
    result = await progress_tracker.run({
        "type": "start_run",
        "params": {"run_name": "wiring-test-run", "config": {"training": {"max_steps": 100}}},
    })
    assert result["status"] == "running"
    assert result["run_name"] == "wiring-test-run"


async def test_progress_tracker_run_routes_log_step(progress_tracker):
    await progress_tracker.run({
        "type": "start_run",
        "params": {"run_name": "wiring-log-test", "config": {"training": {"max_steps": 100}}},
    })
    result = await progress_tracker.run({
        "type": "log_step",
        "params": {"step": 1, "metrics": {"loss": 1.23}, "run_name": "wiring-log-test"},
    })
    assert result["step"] == 1
    assert result["metrics"]["loss"] == 1.23


async def test_progress_tracker_run_routes_get_progress(progress_tracker):
    await progress_tracker.run({
        "type": "start_run",
        "params": {"run_name": "wiring-progress-test", "config": {"training": {"max_steps": 100}}},
    })
    result = await progress_tracker.run({
        "type": "get_progress",
        "params": {"run_name": "wiring-progress-test"},
    })
    assert result["run_name"] == "wiring-progress-test"
    assert result["status"] == "running"


async def test_progress_tracker_run_routes_generate_report(progress_tracker):
    await progress_tracker.run({
        "type": "start_run",
        "params": {"run_name": "wiring-report-test", "config": {"training": {"max_steps": 100}}},
    })
    await progress_tracker.run({
        "type": "log_step",
        "params": {"step": 1, "metrics": {"loss": 2.0}, "run_name": "wiring-report-test"},
    })
    result = await progress_tracker.run({
        "type": "generate_report",
        "params": {"run_name": "wiring-report-test"},
    })
    assert result["status"] == "ok"
    assert "loss_summary" in result


async def test_progress_tracker_run_unhandled_type_returns_structured_error(progress_tracker):
    result = await progress_tracker.run({"type": "unknown_kind", "params": {}})
    assert result["status"] == "error"
    assert "unknown_kind" in result["error"]
    assert "supported" in result
