"""
VECTOR × OpenMythos — vector-chairman training pipeline.

This module:
1. Exports VECTOR's reasoning_chains (reward > 0.7) as training data
2. Fine-tunes OpenMythos 1B (fits RTX 5070 Ti 12GB) on that data
3. Saves the result as a model VECTOR can load via Ollama

Usage:
    python core/training/openmythos/trainer.py          # export + train
    python core/training/openmythos/trainer.py --export-only  # just export data
    python core/training/openmythos/trainer.py --check   # verify setup

Architecture: OpenMythos RDT (Recurrent Depth Transformer)
  Prelude → [Recurrent Block × 16 loops] → Coda
  Each loop = one CoT step in latent space (Saunshi et al. 2025)
  1B params ≈ 1.3B standard transformer quality
  RTX 5070 Ti 12GB: trains in ~1-2 hours with LoRA
"""

import sys

__all__ = [
    "check_setup",
    "create_modelfile",
    "export_training_data",
    "SelfImprovementTrainer",
    "train",
]

import json
import datetime
from pathlib import Path


_VENDOR_DIR = Path(__file__).parent / "vendor"
_OPENMYTHOS_REPO = (
    _VENDOR_DIR  # vendored inside VECTOR (preferred — repo deletable)
    if _VENDOR_DIR.exists()
    else Path(__file__).parent.parent.parent.parent / "GitHub" / "OpenMythos-main"
)
_DATA_DIR = Path(__file__).parent.parent.parent / "data/training_runs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

from loguru import logger


# ── Step 1: Export training data from VECTOR's reasoning chains ───────────────

def export_training_data(min_reward: float = 0.7, limit: int = 10000) -> Path:
    """
    Pull high-reward reasoning chains from VECTOR's SQLite DB.
    Format: JSONL with {instruction, input, output} for fine-tuning.
    Returns path to the exported file.
    """
    from core.memory.episodic import EpisodicMemory

    mem = EpisodicMemory()
    chains = mem.get_training_data(limit=limit)

    if not chains:
        logger.warning("[OpenMythos] No training data found. Run VECTOR for a while first.")
        return None

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _DATA_DIR / f"vector_chains_{timestamp}.jsonl"

    count = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for chain in chains:
            if chain.get("reward", 0) < min_reward:
                continue
            steps = chain.get("steps", "[]")
            if isinstance(steps, str):
                try:
                    steps = json.loads(steps)
                except Exception:
                    steps = [steps]

            # Format as instruction-following example
            record = {
                "instruction": f"Given this situation: {chain.get('situation', '')}",
                "input": f"Goals: {chain.get('goal_ids', [])}",
                "output": (
                    f"Reasoning: {' -> '.join(str(s) for s in steps)}\n"
                    f"Action: {chain.get('action_taken', '')}\n"
                    f"Outcome: {chain.get('outcome', '')}"
                ),
                "reward": chain.get("reward", 0),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    logger.info(f"[OpenMythos] Exported {count} training examples → {out_path}")
    return out_path


# ── Step 2: LoRA fine-tune OpenMythos 1B on VECTOR's data ────────────────────

def train(data_path: Path, epochs: int = 3, output_dir: Path = None) -> Path:
    """
    LoRA fine-tune OpenMythos 1B on VECTOR's reasoning chains.
    Requires: torch, transformers, peft, datasets
    RTX 5070 Ti 12GB: ~1-2 hours for 3 epochs on 10k examples.
    """
    if output_dir is None:
        output_dir = _DATA_DIR / "vector_chairman_lora"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Add OpenMythos to path

    try:
        import torch
        from open_mythos import OpenMythos, MythosConfig, mythos_1b
    except ImportError as e:
        logger.error(f"[OpenMythos] Missing dependency: {e}")
        logger.error("Install: pip install torch transformers peft datasets")
        logger.error(f"Also ensure OpenMythos repo is at: {_OPENMYTHOS_REPO}")
        return None

    logger.info("[OpenMythos] Loading mythos_1b config...")
    config = mythos_1b()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"[OpenMythos] Device: {device}")

    if device == "cpu":
        logger.warning("[OpenMythos] No GPU detected. Training will be very slow.")

    # Initialize model
    model = OpenMythos(config).to(device)
    total_params = sum(p.numel() for p in model.parameters())
    logger.info(f"[OpenMythos] Model: {total_params/1e9:.2f}B parameters")

    # Apply LoRA (only train adapter weights — keeps VRAM low)
    try:
        from peft import get_peft_model, LoraConfig, TaskType
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=config.lora_rank,
            lora_alpha=config.lora_rank * 2,
            target_modules=["q_proj", "v_proj", "k_proj"],
            lora_dropout=0.05,
            bias="none",
        )
        model = get_peft_model(model, lora_config)
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        logger.info(f"[OpenMythos] LoRA trainable params: {trainable/1e6:.1f}M ({trainable/total_params*100:.1f}%)")
    except ImportError:
        logger.warning("[OpenMythos] peft not installed — training full model (slower, more VRAM)")

    # Load training data
    try:
        from datasets import load_dataset
        dataset = load_dataset("json", data_files=str(data_path), split="train")
        logger.info(f"[OpenMythos] Dataset: {len(dataset)} examples")
    except ImportError:
        logger.error("[OpenMythos] datasets not installed: pip install datasets")
        return None

    # Simple training loop
    try:
        from transformers import TrainingArguments, Trainer, DataCollatorForLanguageModeling
        from open_mythos import MythosTokenizer

        tokenizer = MythosTokenizer()

        def tokenize(examples):
            texts = [
                f"{ex['instruction']}\n{ex['input']}\n{ex['output']}"
                for ex in zip(
                    examples["instruction"],
                    examples["input"],
                    examples["output"],
                )
            ]
            # MythosTokenizer may not support batch __call__; encode one item at a time
            if hasattr(tokenizer, '__call__'):
                try:
                    return tokenizer(texts, truncation=True, max_length=512, padding="max_length")
                except (TypeError, ValueError):
                    pass
            # Fallback: per-item encode
            encoded = [tokenizer.encode(text) for text in texts]
            # Truncate / pad to max_length=512
            input_ids = []
            for ids in encoded:
                if len(ids) > 512:
                    ids = ids[:512]
                else:
                    ids = ids + [0] * (512 - len(ids))
                input_ids.append(ids)
            return {"input_ids": input_ids, "attention_mask": [[1 if t != 0 else 0 for t in ids] for ids in input_ids]}

        tokenized = dataset.map(tokenize, batched=True, remove_columns=dataset.column_names)

        training_args = TrainingArguments(
            output_dir=str(output_dir),
            num_train_epochs=epochs,
            per_device_train_batch_size=4,
            gradient_accumulation_steps=4,
            learning_rate=2e-4,
            fp16=torch.cuda.is_available(),
            logging_steps=50,
            save_steps=500,
            save_total_limit=2,
            report_to="none",
            dataloader_num_workers=0,
        )

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized,
            data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
        )

        logger.info("[OpenMythos] Starting training...")
        trainer.train()
        trainer.save_model(str(output_dir))
        logger.info(f"[OpenMythos] Training complete. Model saved to {output_dir}")
        return output_dir

    except Exception as e:
        logger.error(f"[OpenMythos] Training failed: {e}")
        return None


# ── Step 3: Create Ollama modelfile for vector-chairman ───────────────────────

def create_modelfile(model_dir: Path) -> Path:
    """
    Generate an Ollama modelfile pointing to the trained OpenMythos weights.
    Run: ollama create vector-chairman -f <modelfile_path>
    """
    modelfile_path = model_dir / "Modelfile"
    content = f"""FROM {model_dir}/pytorch_model.bin

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER num_ctx 4096
PARAMETER stop "<|end|>"

SYSTEM \"\"\"You are vector-chairman, the LLM Council Chairman for VECTOR — Arghyadeep's autonomous AI system.
You have been trained on VECTOR's own reasoning chains and decision history.
Your role: synthesize council member responses into a single decisive verdict.
Be direct, specific, and action-oriented. No hedging. No filler.
Always consider: goal alignment, resource cost, and Arghyadeep's current context.\"\"\"
"""
    modelfile_path.write_text(content, encoding="utf-8")
    logger.info(f"[OpenMythos] Modelfile created: {modelfile_path}")
    logger.info(f"[OpenMythos] To load in Ollama: ollama create vector-chairman -f {modelfile_path}")
    return modelfile_path


# ── Step 4: Check setup ───────────────────────────────────────────────────────

def check_setup() -> dict:
    """Verify all dependencies and data are ready for training."""
    results = {}

    # Check OpenMythos repo
    results["openmythos_repo"] = _OPENMYTHOS_REPO.exists()
    if not results["openmythos_repo"]:
        logger.warning(f"[OpenMythos] Repo not found at {_OPENMYTHOS_REPO}")

    # Check PyTorch + CUDA
    try:
        import torch
        results["torch"] = True
        results["cuda"] = torch.cuda.is_available()
        if results["cuda"]:
            results["gpu"] = torch.cuda.get_device_name(0)
            results["vram_gb"] = torch.cuda.get_device_properties(0).total_memory / 1e9
    except ImportError:
        results["torch"] = False
        results["cuda"] = False

    # Check peft
    try:
        import peft
        results["peft"] = True
    except ImportError:
        results["peft"] = False

    # Check training data
    from core.memory.episodic import EpisodicMemory
    mem = EpisodicMemory()
    stats = mem.get_stats()
    results["training_chains"] = stats.get("reasoning_chains", 0)
    results["ready_to_train"] = (
        results["openmythos_repo"]
        and results.get("torch", False)
        and results["training_chains"] > 100
    )

    logger.info(f"[OpenMythos] Setup check: {results}")
    return results


# ── Self-improvement train-and-eval cycle ─────────────────────────────────────

import random as _random


class SelfImprovementTrainer:
    """Wraps the training pipeline with eval gates for deploy decisions."""

    def __init__(self, baseline: dict | None = None) -> None:
        self._baseline = baseline or {"coherence": 0.5}

    def evaluate(self, holdout_prompts: list[str] | None = None) -> dict:
        """Score coherence on a holdout set. Returns metrics dict."""
        if holdout_prompts is None:
            holdout_prompts = [
                "What should VECTOR prioritize today?",
                "Summarize the last hour of activity.",
                "Is there a security threat in the current context?",
            ]
        coherence_scores = []
        for prompt in holdout_prompts[:50]:
            try:
                output = self.generate(prompt)
                score = self._llm_judge_coherence(output)
                coherence_scores.append(score)
            except Exception:
                coherence_scores.append(0.0)
        avg = sum(coherence_scores) / len(coherence_scores) if coherence_scores else 0.0
        return {"coherence": avg, "samples": len(coherence_scores)}

    def should_deploy(self, eval_result: dict, baseline: dict | None = None) -> tuple[bool, str]:
        """Gate: reject if any metric regresses beyond threshold."""
        bl = baseline or self._baseline
        if eval_result["coherence"] < bl["coherence"] * 0.85:
            return (False, f"coherence dropped: {eval_result['coherence']:.2f} vs {bl['coherence']:.2f}")
        return (True, "all gates passed")

    def generate(self, prompt: str) -> str:
        """Placeholder: produce a sample output for eval scoring.

        FLAG-FOR-OWNER (2026-10-01 audit): this is wired into the real
        Sunday-reflect deploy gate (autonomous_loop.py calls
        SelfImprovementTrainer.evaluate() -> should_deploy() after a weekly
        training cycle completes) but never calls the actual trained model --
        it scores a deterministic hash string's length/char-variety, not real
        output. should_deploy() will pass or fail based on that fake score,
        not on whether the trained model is actually any good. Wiring this to
        real inference needs an owner call: what checkpoint to call before
        it's promoted to the live "vector-chairman" Ollama tag (a staging tag?
        direct weight loading?), and what the real holdout prompt set should
        be -- not a narrow patch. Logging loudly so this limitation is visible
        in production logs instead of silently passing as a real eval.
        """
        logger.warning(
            "[OpenMythos] SelfImprovementTrainer.generate() is a PLACEHOLDER -- "
            "not calling the real trained model. The deploy eval-gate's "
            "coherence score does not reflect actual model quality."
        )
        import hashlib
        return f"VECTOR response to: {prompt[:50]}... [hash={hashlib.md5(prompt.encode()).hexdigest()[:8]}]"

    def _llm_judge_coherence(self, output: str) -> float:
        """Heuristic coherence score based on output length and variety."""
        score = min(1.0, len(output) / 200.0)
        unique_chars = len(set(output.lower()))
        score *= min(1.0, unique_chars / 20.0)
        return round(score, 4)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="VECTOR × OpenMythos training pipeline")
    parser.add_argument("--check", action="store_true", help="Check setup only")
    parser.add_argument("--export-only", action="store_true", help="Export data without training")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--min-reward", type=float, default=0.7)
    args = parser.parse_args()

    if args.check:
        status = check_setup()
        print(json.dumps(status, indent=2))
        sys.exit(0 if status["ready_to_train"] else 1)

    # Export training data
    data_path = export_training_data(min_reward=args.min_reward)
    if not data_path:
        print("No training data. Run VECTOR for a while to accumulate reasoning chains.")
        sys.exit(1)

    if args.export_only:
        print(f"Data exported to: {data_path}")
        sys.exit(0)

    # Train
    model_dir = train(data_path, epochs=args.epochs)
    if model_dir:
        modelfile = create_modelfile(model_dir)
        print(f"\n✅ Training complete!")
        print(f"   Model: {model_dir}")
        print(f"   Modelfile: {modelfile}")
        print(f"\nTo activate vector-chairman:")
        print(f"   ollama create vector-chairman -f {modelfile}")
    else:
        print("Training failed. Check logs above.")
        sys.exit(1)
