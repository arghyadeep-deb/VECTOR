"""Thin SFT wrapper over LoRATrainer — adds the reasoning-chains dataset contract."""
from __future__ import annotations

from loguru import logger

from core.training.lora_trainer import LoRATrainer
from core.training.training_config import AdapterConfig, TrainingArgs
from core.training.openmythos.export_to_ollama import OllamaExporter
from core.training import reasoning_chain_dataset

__all__ = ["run_sft"]


def run_sft(
    adapter_name: str,
    base_model: str,
    min_reward: float = 0.7,
    min_examples: int = 50,
    export: bool = False,
) -> dict:
    examples = reasoning_chain_dataset.chains_to_sft_examples(min_reward=min_reward)
    if len(examples) < min_examples:
        logger.info(
            "[VECTOR][post_training] run_sft skipped — {} examples < min {}",
            len(examples), min_examples,
        )
        return {"status": "skipped", "reason": "insufficient_data", "count": len(examples), "adapter": adapter_name}

    dataset = [
        {"text": f"### Instruction:\n{ex['instruction']}\n\n### Response:\n{ex['response']}"}
        for ex in examples
    ]

    adapter_config = AdapterConfig(name=adapter_name, base_model=base_model, target_modules=["q_proj", "v_proj"])
    training_args = TrainingArgs()

    result = LoRATrainer().train(adapter_config, training_args, dataset)

    if export and result.get("status") == "success" and result.get("save_path"):
        try:
            exporter = OllamaExporter()
            exporter.export_model_weights(src_path=result["save_path"], model_name=adapter_name)
            exporter.create_modelfile(model_name=adapter_name, system_prompt="You are VECTOR.")
            result["export"] = "ok"
        except Exception as exc:
            logger.warning("[VECTOR][post_training] export failed: {}", exc)
            result["export"] = "failed"
    elif export:
        result["export"] = "skipped_no_save_path"

    return result
