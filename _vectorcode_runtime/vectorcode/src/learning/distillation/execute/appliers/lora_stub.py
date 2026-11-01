# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb

"""LoRA fine-tuning applier.

On machines with CUDA + PEFT + transformers installed this runs a real LoRA
fine-tune.  When the dependencies or GPU are unavailable it degrades
gracefully: validate() returns ok=False with a clear reason and apply()
records the requested edit to a queue artifact instead of raising.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from loguru import logger

from vectorcode.src.learning.distillation.execute.base import (
    ApplyContext,
    ApplyResult,
    EditApplier,
    ValidationResult,
)
from vectorcode.src.learning.distillation.models import Edit, EditOp

# --- Dependency availability check (done once at import time) ---------------

def _check_lora_deps() -> tuple[bool, str]:
    """Return (available, reason_if_not)."""
    try:
        import torch
        if not torch.cuda.is_available():
            return False, "CUDA not available (torch.cuda.is_available() is False)"
    except ImportError:
        return False, "torch not installed"
    try:
        import peft  # noqa: F401
    except ImportError:
        return False, "peft not installed (pip install peft)"
    try:
        import transformers  # noqa: F401
    except ImportError:
        return False, "transformers not installed (pip install transformers)"
    return True, ""


_LORA_AVAILABLE, _LORA_UNAVAIL_REASON = _check_lora_deps()


def _edit_path(parent: Path, edit_id: str, *, suffix: str = "") -> Path:
    """Return a direct child of *parent* for an untrusted edit identifier."""
    parent = parent.resolve()
    path = (parent / f"{edit_id}{suffix}").resolve()
    if path.parent != parent:
        raise ValueError(f"Unsafe edit id: {edit_id!r}")
    return path


# --- Queue file for deferred edits when LoRA is unavailable -----------------

def _queue_edit(edit: Edit, ctx: ApplyContext) -> Path:
    """Persist the edit to a queue JSON file and return the path."""
    queue_dir = ctx.vector_home / "lora_queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    path = _edit_path(queue_dir, edit.id, suffix=".json")
    path.write_text(json.dumps(edit.model_dump(), indent=2, default=str))
    return path


def _snapshot_adapter_state(edit: Edit, ctx: ApplyContext) -> Path:
    """Persist the restorable adapter state before training starts."""
    rollback_root = ctx.vector_home / "lora_rollbacks"
    rollback_root.mkdir(parents=True, exist_ok=True)
    snapshot_dir = _edit_path(rollback_root, edit.id)
    manifest_path = snapshot_dir / "manifest.json"
    if manifest_path.exists():
        return snapshot_dir

    adapter_dir = _edit_path(ctx.vector_home / "lora_adapters", edit.id)
    snapshot_dir.mkdir()
    had_adapter = adapter_dir.is_dir()
    if had_adapter:
        shutil.copytree(adapter_dir, snapshot_dir / "pre_training_adapter")
    manifest_path.write_text(
        json.dumps(
            {
                "edit_id": edit.id,
                "had_adapter": had_adapter,
                "session_id": ctx.session_id,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info(f"[LoRA] Pre-training rollback snapshot saved at {snapshot_dir}")
    return snapshot_dir


# --- Main applier ------------------------------------------------------------

class LoraStubApplier(EditApplier):
    """Apply LORA_FINETUNE edits.

    Real fine-tune when GPU + PEFT + transformers are present; graceful
    degradation to a queue artifact otherwise.

    DESIGN QUESTION: risk_tier.py always assigns this op MANUAL, while both
    shipped execution loops skip MANUAL edits before resolving an applier.
    Consequently neither this queue fallback nor the real training branch is
    reachable through those loops. Enabling either path needs an explicit
    owner decision about the approval-to-execution flow.
    """

    op = EditOp.LORA_FINETUNE

    def validate(self, edit: Edit, ctx: ApplyContext) -> ValidationResult:
        if not _LORA_AVAILABLE:
            return ValidationResult(
                ok=False,
                reason=(
                    f"LoRA fine-tuning requires CUDA + peft + transformers: "
                    f"{_LORA_UNAVAIL_REASON}. "
                    "The edit will be queued for when these dependencies are available."
                ),
            )
        # Deps present — check payload has the minimum required fields
        payload = edit.payload or {}
        if not payload.get("base_model"):
            return ValidationResult(
                ok=False,
                reason="payload.base_model is required for LORA_FINETUNE",
            )
        return ValidationResult(ok=True)

    def apply(self, edit: Edit, ctx: ApplyContext) -> ApplyResult:
        if not _LORA_AVAILABLE:
            # Graceful degradation: queue the edit instead of raising
            queue_path = _queue_edit(edit, ctx)
            logger.warning(
                f"[LoRA] Dependencies unavailable ({_LORA_UNAVAIL_REASON}). "
                f"Edit {edit.id} queued at {queue_path}"
            )
            return ApplyResult(changed_files=[str(queue_path)])

        _snapshot_adapter_state(edit, ctx)
        try:
            return _run_lora_finetune(edit, ctx)
        except Exception:
            self.rollback(edit, ctx)
            raise

    def rollback(self, edit: Edit, ctx: ApplyContext) -> None:
        # Remove queue artifact if it exists
        queue_path = _edit_path(ctx.vector_home / "lora_queue", edit.id, suffix=".json")
        if queue_path.exists():
            queue_path.unlink()
            logger.info(f"[LoRA] Rolled back queued edit {edit.id}")
        adapter_dir = _edit_path(ctx.vector_home / "lora_adapters", edit.id)
        snapshot_dir = _edit_path(ctx.vector_home / "lora_rollbacks", edit.id)
        manifest_path = snapshot_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if adapter_dir.exists():
                shutil.rmtree(adapter_dir)
            if manifest.get("had_adapter"):
                shutil.copytree(snapshot_dir / "pre_training_adapter", adapter_dir)
                logger.info(f"[LoRA] Restored pre-training adapter at {adapter_dir}")
            else:
                logger.info(f"[LoRA] Removed post-training adapter at {adapter_dir}")
        elif adapter_dir.exists():
            shutil.rmtree(adapter_dir)
            logger.info(f"[LoRA] Removed adapter at {adapter_dir}")


def _run_lora_finetune(edit: Edit, ctx: ApplyContext) -> ApplyResult:
    """Execute a real LoRA fine-tune (only called when deps are present)."""
    import torch
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer
    from datasets import Dataset

    payload = edit.payload
    base_model_name: str = payload["base_model"]
    training_data: list = payload.get("training_data", [])
    r: int = int(payload.get("lora_r", 8))
    lora_alpha: int = int(payload.get("lora_alpha", 16))
    epochs: int = int(payload.get("epochs", 1))
    adapter_dir = _edit_path(ctx.vector_home / "lora_adapters", edit.id)

    if not training_data:
        logger.warning(f"[LoRA] No training_data in payload for edit {edit.id}; skipping")
        return ApplyResult(changed_files=[])

    logger.info(
        f"[LoRA] Fine-tuning {base_model_name} | r={r} | alpha={lora_alpha} | "
        f"samples={len(training_data)} | epochs={epochs}"
    )

    tokenizer = AutoTokenizer.from_pretrained(base_model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        torch_dtype=torch.float16,
        device_map="auto",
    )

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=r,
        lora_alpha=lora_alpha,
        lora_dropout=0.05,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Build dataset from training_data list of {"input": ..., "output": ...}
    def tokenize(example):
        text = f"{example.get('input', '')}\n{example.get('output', '')}"
        enc = tokenizer(text, truncation=True, max_length=512, padding="max_length")
        enc["labels"] = enc["input_ids"][:]
        return enc

    dataset = Dataset.from_list(training_data).map(tokenize)

    training_args = TrainingArguments(
        output_dir=str(adapter_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        save_strategy="no",
        logging_steps=10,
        fp16=True,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
    )
    trainer.train()
    model.save_pretrained(str(adapter_dir))
    logger.info(f"[LoRA] Adapter saved at {adapter_dir}")
    return ApplyResult(changed_files=[str(adapter_dir)])
