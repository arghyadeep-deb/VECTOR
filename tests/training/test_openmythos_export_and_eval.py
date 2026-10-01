"""Regression tests: OllamaExporter.create_modelfile() crash + SelfImprovementTrainer
placeholder-eval visibility (Phase 3 whole-repo audit, 2026-10-01)."""

import tempfile
from pathlib import Path

from core.training.openmythos.export_to_ollama import OllamaExporter
from core.training.openmythos.trainer import SelfImprovementTrainer


def _exporter(tmp_dir: str) -> OllamaExporter:
    exporter = OllamaExporter.__new__(OllamaExporter)
    exporter.model_dir = tmp_dir
    exporter.registry_path = Path(tmp_dir) / "registry"
    exporter.registry_path.mkdir(parents=True, exist_ok=True)
    exporter.ollama_host = "http://127.0.0.1:11434"
    return exporter


def test_create_modelfile_with_parameters_does_not_crash():
    """Regression: `if config_name := parameters.get(config_name):` referenced
    config_name on the right-hand side before the walrus assignment ever
    bound it (the loop variable was config_key) -- an UnboundLocalError on
    the very first call with any parameters dict, which is the function's
    whole purpose."""
    with tempfile.TemporaryDirectory() as tmp:
        exporter = _exporter(tmp)
        (exporter.registry_path / "my_model").mkdir()
        path = exporter.create_modelfile(
            model_name="my_model",
            system_prompt="You are VECTOR.",
            parameters={"temperature": 0.7, "top_p": 0.9, "base_model": "llama2"},
        )
        assert path
        content = Path(path).read_text(encoding="utf-8")
        assert "PARAMETER temperature 0.7" in content
        assert "PARAMETER top_p 0.9" in content


def test_create_modelfile_without_parameters_still_works():
    with tempfile.TemporaryDirectory() as tmp:
        exporter = _exporter(tmp)
        (exporter.registry_path / "my_model").mkdir()
        path = exporter.create_modelfile(model_name="my_model", system_prompt="hi")
        assert path
        assert "FROM llama2" in Path(path).read_text(encoding="utf-8")


def test_placeholder_eval_logs_warning_every_call(caplog):
    """The deploy eval-gate (autonomous_loop.py's Sunday reflect) calls
    SelfImprovementTrainer.evaluate() -> generate() for real, but generate()
    is a hash-string placeholder, not real model inference -- should_deploy()
    passes/fails on a fake score. Not fixed here (needs an owner call on
    what checkpoint to evaluate before promotion); this proves the
    limitation is now loud in logs instead of silent."""
    import logging
    from loguru import logger as _loguru_logger

    trainer = SelfImprovementTrainer()
    handler_id = _loguru_logger.add(caplog.handler, format="{message}", level="WARNING")
    try:
        with caplog.at_level(logging.WARNING):
            trainer.generate("test prompt")
    finally:
        _loguru_logger.remove(handler_id)
    assert any("PLACEHOLDER" in r.message for r in caplog.records)
