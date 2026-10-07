"""Qwen3 8B intent classifier fine-tuned with LoRA for governor routing.

Generative classifier: "Classify this query: {text} → District: {district}"

Pipeline position: Stage 3 (after embedding similarity, before LLM fallback).

Usage:
    # Train
    python core/city/intent_qwen3_8b.py --train

    # Use
    from core.city.intent_qwen3_8b import IntentQwen3_8B
    classifier = IntentQwen3_8B()
    result = await classifier.classify("quiz me on french")
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from loguru import logger

__all__ = ["IntentQwen3_8B"]


class IntentQwen3_8B:
    """Qwen3 8B intent classifier (fine-tuned with LoRA)."""

    def __init__(self, adapter_path: str = "data/adapters/intent_qwen3_8b/final"):
        """Initialize classifier.

        Args:
            adapter_path: Path to fine-tuned LoRA adapter.
        """
        self._adapter_path = Path(adapter_path)
        self._model = None
        self._tokenizer = None
        self._device = "cuda"
        self._loaded = False

    def _load_model(self) -> bool:
        """Load fine-tuned model and tokenizer."""
        if self._loaded:
            return True

        if not self._adapter_path.exists():
            logger.warning(f"[IntentQwen3] Adapter not found: {self._adapter_path}")
            return False

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel

            # Load base model (qwen3:8b)
            base_model = "Qwen/Qwen3-8B"
            self._tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)

            # Load LoRA adapter
            base = AutoModelForCausalLM.from_pretrained(
                base_model,
                torch_dtype=torch.float16,
                device_map="auto",
                trust_remote_code=True,
            )
            self._model = PeftModel.from_pretrained(base, str(self._adapter_path))
            self._model.eval()

            self._loaded = True
            logger.info(f"[IntentQwen3] Loaded fine-tuned model from {self._adapter_path}")
            return True

        except Exception as e:
            logger.error(f"[IntentQwen3] Failed to load model: {e}")
            return False

    async def classify(self, text: str) -> Optional[dict]:
        """Classify intent.

        Args:
            text: User query text.

        Returns:
            {"type": "", "district": district, "confidence": 1.0, "source": "qwen3_8b_classifier"}
            or None if model not loaded.
        """
        if not self._load_model():
            return None

        try:
            # Imported in _load_model() only has local scope there; inference
            # also needs the module for its no_grad context.
            import torch

            # Format prompt
            prompt = f"Classify this query: {text} → District:"

            # Generate
            inputs = self._tokenizer(prompt, return_tensors="pt").to(self._device)
            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=20,
                    temperature=0.1,  # Low temperature for classification
                    do_sample=False,
                )

            # Decode output
            generated_text = self._tokenizer.decode(outputs[0], skip_special_tokens=True)

            # Parse district from output
            # Expected format: "Classify this query: {text} → District: {district}"
            if "District:" in generated_text:
                district = generated_text.split("District:")[-1].strip().split()[0]
                # Validate district
                from core.city.governor import DISTRICT_TASK_MAP
                if district in set(DISTRICT_TASK_MAP.values()):
                    return {
                        "type": "",  # Governor will use default task_type
                        "district": district,
                        "confidence": 1.0,  # Generative model = high confidence
                        "source": "qwen3_8b_classifier",
                    }

            logger.warning(f"[IntentQwen3] Could not parse district from: {generated_text}")
            return None

        except Exception as e:
            logger.error(f"[IntentQwen3] Classification failed: {e}")
            return None

    def train(self, dataset_path: str = "data/golden_intent_dataset_district_only.jsonl") -> None:
        """Fine-tune qwen3:8b with LoRA on intent classification.

        Args:
            dataset_path: Path to JSONL dataset with district labels.
        """
        logger.info(f"[IntentQwen3] Fine-tuning on {dataset_path}...")

        # Load dataset
        examples = []
        with open(dataset_path, "r", encoding="utf-8") as f:
            for line in f:
                examples.append(json.loads(line))

        logger.info(f"[IntentQwen3] Loaded {len(examples)} training examples")

        # Format as instruction-following data (district-only classification)
        formatted_data = []
        for ex in examples:
            prompt = f"Classify this query: {ex['text']} → District:"
            formatted_data.append({
                "text": prompt,  # Required by LoRATrainer
                "instruction": prompt,
                "output": ex["district"],
            })

        logger.info(f"[IntentQwen3] Formatted {len(formatted_data)} examples")

        # Use LoRA trainer
        from core.training.lora_trainer import LoRATrainer
        from core.training.training_config import AdapterConfig, TrainingArgs

        adapter_config = AdapterConfig(
            name="intent_qwen3_8b",
            base_model="Qwen/Qwen3-8B",
            rank=16,
            alpha=32,
            dropout=0.1,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        )

        training_args = TrainingArgs(
            num_epochs=3,
            batch_size=4,
            gradient_accumulation_steps=4,
            learning_rate=2e-4,
            warmup_steps=100,
            max_seq_length=256,
        )

        trainer = LoRATrainer()
        result = trainer.train(adapter_config, training_args, formatted_data)

        if result["status"] == "success":
            logger.info(f"[IntentQwen3] Fine-tuning complete: {result}")
        else:
            logger.error(f"[IntentQwen3] Fine-tuning failed: {result}")

    def evaluate(self, dataset_path: str = "data/golden_intent_dataset_district_only.jsonl") -> dict:
        """Evaluate model on dataset.

        Returns:
            {"accuracy": float, "correct": int, "total": int}
        """
        if not self._load_model():
            return {"accuracy": 0.0, "correct": 0, "total": 0}

        # Load dataset
        examples = []
        with open(dataset_path, "r", encoding="utf-8") as f:
            for line in f:
                examples.append(json.loads(line))

        correct = 0
        total = len(examples)

        for ex in examples:
            result = self.classify(ex["text"])
            if result and result["district"] == ex["district"]:
                correct += 1

        accuracy = correct / total if total > 0 else 0.0
        logger.info(f"[IntentQwen3] Accuracy: {accuracy:.2%} ({correct}/{total})")

        return {"accuracy": accuracy, "correct": correct, "total": total}


if __name__ == "__main__":
    """Fine-tune or evaluate IntentQwen3_8B."""
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="IntentQwen3_8B classifier")
    parser.add_argument("--train", action="store_true", help="Fine-tune model")
    parser.add_argument("--evaluate", action="store_true", help="Evaluate model")
    parser.add_argument("--dataset", default="data/golden_intent_dataset_augmented.jsonl", help="Dataset path")
    args = parser.parse_args()

    classifier = IntentQwen3_8B()

    if args.train:
        classifier.train(args.dataset)
    elif args.evaluate:
        result = classifier.evaluate(args.dataset)
        print(f"\nEvaluation: {result['accuracy']:.2%} ({result['correct']}/{result['total']})")
    else:
        print("Use --train or --evaluate")
