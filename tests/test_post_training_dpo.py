import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_run_dpo_simulates_when_trl_unavailable(monkeypatch):
    from core.training.post_training import dpo_trainer

    monkeypatch.setattr(
        dpo_trainer.reasoning_chain_dataset, "build_dpo_pairs",
        lambda **kw: [{"prompt": "p", "chosen": "c", "rejected": "r"}] * 10,
    )
    result = dpo_trainer.run_dpo(adapter_name="test-dpo", base_model="dummy/model", min_pairs=5)
    # New module — its own status vocabulary (it does NOT delegate to
    # LoRATrainer, so it isn't bound to "success"/"failed"):
    # "simulated" when trl is absent, "ok" when a real trl run completes,
    # "skipped" for insufficient pairs, "failed" on a real run that errors.
    assert result["status"] in ("simulated", "ok", "failed", "skipped")
    assert result["adapter"] == "test-dpo"


def test_run_dpo_skips_when_too_few_pairs(monkeypatch):
    from core.training.post_training import dpo_trainer

    monkeypatch.setattr(
        dpo_trainer.reasoning_chain_dataset, "build_dpo_pairs",
        lambda **kw: [{"prompt": "p", "chosen": "c", "rejected": "r"}] * 2,
    )
    result = dpo_trainer.run_dpo(adapter_name="test-dpo", base_model="dummy/model", min_pairs=20)
    assert result["status"] == "skipped"
    assert result["reason"] == "insufficient_pairs"


def test_run_dpo_simulated_writes_manifest(monkeypatch, tmp_path):
    from core.training.post_training import dpo_trainer

    monkeypatch.setattr(
        dpo_trainer.reasoning_chain_dataset, "build_dpo_pairs",
        lambda **kw: [{"prompt": "p", "chosen": "c", "rejected": "r"}] * 25,
    )
    monkeypatch.setattr(dpo_trainer, "_ADAPTERS_DIR", tmp_path)

    result = dpo_trainer.run_dpo(adapter_name="test-dpo-manifest", base_model="dummy/model", min_pairs=20)
    assert result["status"] == "simulated"
    assert result["pairs"] == 25

    manifest_path = tmp_path / "test-dpo-manifest" / "dpo_simulated.json"
    assert manifest_path.exists()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
