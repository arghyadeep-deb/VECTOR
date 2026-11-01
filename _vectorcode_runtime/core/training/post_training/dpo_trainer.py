"""DPO preference-pair trainer — real trl.DPOTrainer when available, simulated fallback.

Mirrors LoRATrainer's own graceful-degradation convention
(core/training/lora_trainer.py): try the real library, fall back to a
manifest-writing simulation that never silently fakes success without
saying so.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from core.training.training_config import AdapterConfig, TrainingArgs
from core.training import reasoning_chain_dataset

__all__ = ["run_dpo"]

_ADAPTERS_DIR = Path("data/adapters")


def run_dpo(adapter_name: str, base_model: str, min_pairs: int = 20) -> dict:
    pairs = reasoning_chain_dataset.build_dpo_pairs()
    if len(pairs) < min_pairs:
        logger.info(
            "[VECTOR][post_training] run_dpo skipped — {} pairs < min {}",
            len(pairs), min_pairs,
        )
        return {"status": "skipped", "reason": "insufficient_pairs", "count": len(pairs), "adapter": adapter_name}

    try:
        import trl  # noqa: F401
        import peft  # noqa: F401
    except ImportError:
        return _simulate_dpo(pairs, adapter_name, base_model)

    try:
        return _train_with_trl(pairs, adapter_name, base_model)
    except Exception as exc:
        logger.error("[VECTOR][post_training] DPO training failed: {}", exc)
        return {"status": "failed", "reason": str(exc), "adapter": adapter_name}


def _train_with_trl(pairs: list[dict], adapter_name: str, base_model: str) -> dict:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, TaskType
    from trl import DPOConfig, DPOTrainer

    adapter_config = AdapterConfig(name=adapter_name, base_model=base_model, target_modules=["q_proj", "v_proj"])
    training_args = TrainingArgs()

    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(base_model, trust_remote_code=True)

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=adapter_config.rank,
        lora_alpha=adapter_config.alpha,
        lora_dropout=adapter_config.dropout,
        target_modules=adapter_config.target_modules,
    )

    save_dir = str(_ADAPTERS_DIR / adapter_name / "dpo")
    dpo_config = DPOConfig(
        output_dir=save_dir,
        per_device_train_batch_size=training_args.batch_size,
        num_train_epochs=training_args.num_epochs,
        learning_rate=training_args.learning_rate,
    )
    trainer = DPOTrainer(
        model=model,
        args=dpo_config,
        train_dataset=pairs,
        tokenizer=tokenizer,
        peft_config=lora_config,
    )
    trainer.train()
    trainer.save_model(save_dir)

    return {
        "status": "ok",
        "adapter": adapter_name,
        "base_model": base_model,
        "pairs": len(pairs),
        "save_path": save_dir,
    }


def _simulate_dpo(pairs: list[dict], adapter_name: str, base_model: str) -> dict:
    save_dir = _ADAPTERS_DIR / adapter_name
    save_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "adapter": adapter_name,
        "base_model": base_model,
        "pairs": len(pairs),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (save_dir / "dpo_simulated.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("[VECTOR][post_training] DPO simulated for '{}' ({} pairs, trl unavailable)", adapter_name, len(pairs))
    return {"status": "simulated", "pairs": len(pairs), "adapter": adapter_name}
