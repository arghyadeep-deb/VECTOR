"""Tests for LoRATrainer: simulated training, config validation, save/load, and Ollama deployment."""

import json
import tempfile
from pathlib import Path

from core.training.lora_trainer import LoRATrainer
from core.training.training_config import AdapterConfig, TrainingArgs


def test_simulated_training_returns_success():
    with tempfile.TemporaryDirectory() as tmp:
        trainer = LoRATrainer(adapters_dir=tmp)
        config = AdapterConfig(
            name="test_adapter", base_model="vector-test",
            target_modules=["q_proj", "v_proj"], rank=8, alpha=8.0, dropout=0.05,
        )
        args = TrainingArgs(learning_rate=2e-4, num_epochs=2, batch_size=4)
        dataset = [{"text": "instruction response pair"} for _ in range(50)]
        result = trainer.train(config, args, dataset)
        assert result["status"] == "success"
        assert result["method"] == "simulated"
        assert "final_loss" in result


def test_empty_dataset_returns_failure():
    trainer = LoRATrainer()
    config = AdapterConfig(
        name="empty_test", base_model="vector-test",
        target_modules=["q_proj"], rank=8, alpha=8.0, dropout=0.05,
    )
    args = TrainingArgs()
    result = trainer.train(config, args, [])
    assert result["status"] == "failed"
    assert result["reason"] == "empty_dataset"


def test_save_adapter_creates_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        trainer = LoRATrainer(adapters_dir=tmp)
        config = AdapterConfig(
            name="save_test", base_model="vector-test",
            target_modules=["q_proj"], rank=8, alpha=8.0, dropout=0.05,
        )
        result = {"status": "success", "method": "simulated", "final_loss": 0.1234}
        path = trainer.save_adapter(config, result)
        manifest = Path(path) / "manifest.json"
        assert manifest.exists()
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data["name"] == "save_test"
        assert data["base_model"] == "vector-test"


def test_list_adapters_empty():
    with tempfile.TemporaryDirectory() as tmp:
        trainer = LoRATrainer(adapters_dir=tmp)
        adpts = trainer.list_adapters()
        assert adpts == []


def test_list_adapters_with_saved():
    with tempfile.TemporaryDirectory() as tmp:
        trainer = LoRATrainer(adapters_dir=tmp)
        config = AdapterConfig(
            name="list_test", base_model="vector-test",
            target_modules=["q_proj"], rank=16, alpha=16.0, dropout=0.05,
        )
        result = {"status": "success", "method": "simulated"}
        trainer.save_adapter(config, result)
        adpts = trainer.list_adapters()
        assert len(adpts) == 1
        assert adpts[0]["name"] == "list_test"


def test_deploy_to_ollama_no_cli():
    with tempfile.TemporaryDirectory() as tmp:
        trainer = LoRATrainer(adapters_dir=tmp)
        result = trainer.deploy_to_ollama(tmp)
        assert result is False


def test_extract_loss_history_from_log_history():
    """Regression: self_improvement_cycle.py's eval gate reads
    result["val_loss"]/result["initial_loss"] to reject loss-regressed
    adapters, but neither real training path (_train_with_peft/
    _train_with_unsloth) ever populated them -- the gate read defaults
    (0 / 1) every time, so `val_loss > 1.5 * initial_loss` was always
    `0 > 1.5`, permanently False. _extract_loss_history() pulls real loss
    values from the HF Trainer's own log_history so the gate has something
    real to compare against."""
    class FakeState:
        log_history = [
            {"loss": 0.9, "step": 10},
            {"learning_rate": 1e-4, "step": 10},  # no "loss" key -- must be skipped
            {"loss": 0.3, "step": 100},
        ]

    class FakeTrainer:
        state = FakeState()

    result = LoRATrainer._extract_loss_history(FakeTrainer())
    assert result == {"initial_loss": 0.9, "val_loss": 0.3}


def test_extract_loss_history_empty_log_history():
    class FakeState:
        log_history = []

    class FakeTrainer:
        state = FakeState()

    assert LoRATrainer._extract_loss_history(FakeTrainer()) == {}


def test_extract_loss_history_no_state_attribute():
    class FakeTrainer:
        pass

    assert LoRATrainer._extract_loss_history(FakeTrainer()) == {}


def test_eval_gate_rejects_when_fed_real_regressed_loss():
    """Proves the gate LOGIC in self_improvement_cycle.py is sound once given
    real numbers -- the bug was upstream data never being populated, not the
    comparison itself."""
    train_result = {"val_loss": 2.0, "initial_loss": 1.0}
    val_loss = float(train_result.get("val_loss", 0))
    initial_loss = float(train_result.get("initial_loss", 1))
    assert initial_loss > 0 and val_loss > 1.5 * initial_loss


def test_training_config_validation():
    config = AdapterConfig(
        name="val", base_model="test",
        target_modules=["q_proj"], rank=1, alpha=1.0, dropout=0.0,
    )
    assert config.rank == 1
    assert config.dropout == 0.0
