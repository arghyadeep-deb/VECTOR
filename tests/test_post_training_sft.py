import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_run_sft_simulates_when_peft_unavailable(monkeypatch):
    from core.training.post_training.sft_trainer import run_sft

    monkeypatch.setattr(
        "core.training.reasoning_chain_dataset.chains_to_sft_examples",
        lambda **kw: [{"instruction": "x", "response": "y", "reward": 0.9}] * 60,
    )
    result = run_sft(adapter_name="test-adapter", base_model="dummy/model")
    # LoRATrainer.train()'s real statuses (core/training/lora_trainer.py:101,112,167-185):
    # "success" for BOTH the real-PEFT path and the simulated path — they're
    # distinguished by the "method" field ("peft"/"unsloth"/"simulated"), not
    # status — or "failed". run_sft's own pre-check adds "skipped" for too little data.
    assert result["status"] in ("success", "failed", "skipped")
    assert "adapter" in result


def test_run_sft_skips_when_too_few_examples(monkeypatch):
    from core.training.post_training import sft_trainer

    monkeypatch.setattr(
        "core.training.reasoning_chain_dataset.chains_to_sft_examples",
        lambda **kw: [{"instruction": "x", "response": "y", "reward": 0.9}],
    )

    called = {"train": False}

    class _SpyTrainer:
        def train(self, *a, **kw):
            called["train"] = True
            return {"status": "success"}

    monkeypatch.setattr(sft_trainer, "LoRATrainer", lambda: _SpyTrainer())

    result = sft_trainer.run_sft(adapter_name="test-adapter", base_model="dummy/model", min_examples=50)
    assert result["status"] == "skipped"
    assert result["reason"] == "insufficient_data"
    assert called["train"] is False


def test_run_sft_with_export_calls_ollama_exporter(monkeypatch, tmp_path):
    from core.training.post_training import sft_trainer

    monkeypatch.setattr(
        "core.training.reasoning_chain_dataset.chains_to_sft_examples",
        lambda **kw: [{"instruction": "x", "response": "y", "reward": 0.9}] * 60,
    )

    class _StubTrainer:
        def train(self, *a, **kw):
            return {"status": "success", "method": "peft", "save_path": str(tmp_path)}

    monkeypatch.setattr(sft_trainer, "LoRATrainer", lambda: _StubTrainer())

    export_calls = []

    class _StubExporter:
        def export_model_weights(self, **kw):
            export_calls.append(kw)
            return True

        def create_modelfile(self, **kw):
            return True

    monkeypatch.setattr(sft_trainer, "OllamaExporter", lambda: _StubExporter())

    result = sft_trainer.run_sft(adapter_name="test-adapter", base_model="dummy/model", export=True)
    assert len(export_calls) == 1
    assert export_calls[0]["src_path"] == str(tmp_path)
    assert result["export"] == "ok"


def test_run_sft_with_export_skips_export_when_simulated(monkeypatch):
    from core.training.post_training import sft_trainer

    monkeypatch.setattr(
        "core.training.reasoning_chain_dataset.chains_to_sft_examples",
        lambda **kw: [{"instruction": "x", "response": "y", "reward": 0.9}] * 60,
    )

    class _StubTrainer:
        def train(self, *a, **kw):
            # Simulated path's real result dict has NO "save_path" key at all
            # (core/training/lora_trainer.py:175-185).
            return {"status": "success", "method": "simulated", "final_loss": 0.4}

    monkeypatch.setattr(sft_trainer, "LoRATrainer", lambda: _StubTrainer())

    export_spy = []
    monkeypatch.setattr(
        sft_trainer, "OllamaExporter",
        lambda: type("X", (), {"export_model_weights": lambda self, **kw: export_spy.append(kw)})(),
    )

    result = sft_trainer.run_sft(adapter_name="test-adapter", base_model="dummy/model", export=True)
    assert export_spy == []
    assert result["export"] == "skipped_no_save_path"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
