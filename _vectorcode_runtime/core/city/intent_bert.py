"""BERT-based intent classifier for governor routing.

Small, fast classifier trained on golden dataset. Replaces LLM fallback
for sub-100ms inference on RTX 5070 Ti.

Pipeline position: Stage 3 (after embedding similarity, before fallback).

Usage:
    # Train
    python core/city/intent_bert.py --train

    # Use
    from core.city.intent_bert import IntentBERT
    classifier = IntentBERT("models/intent_bert.pt")
    result = await classifier.classify("quiz me on french")
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import torch
from loguru import logger

__all__ = ["IntentBERT"]


class IntentBERT:
    """BERT-based intent classifier."""

    def __init__(self, model_path: str = "models/intent_bert.pt"):
        """Initialize classifier.

        Args:
            model_path: Path to trained model file.
        """
        self._model_path = Path(model_path)
        self._model = None
        self._tokenizer = None
        self._label_map = {}  # district/task_type -> label_id
        self._reverse_label_map = {}  # label_id -> (district, task_type)
        self._device = "cuda" if torch.cuda.is_available() else "cpu"

        # Lazy load model on first use
        self._loaded = False

    def _load_model(self) -> bool:
        """Load trained model and tokenizer."""
        if self._loaded:
            return True

        if not self._model_path.exists():
            logger.warning(f"[IntentBERT] Model not found: {self._model_path}")
            return False

        try:
            checkpoint = torch.load(self._model_path, map_location=self._device, weights_only=False)
            self._model = checkpoint["model"]
            self._label_map = checkpoint["label_map"]
            self._reverse_label_map = {v: k for k, v in self._label_map.items()}

            # Load tokenizer
            from transformers import BertTokenizer
            self._tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")

            self._model.to(self._device)
            self._model.eval()

            self._loaded = True
            logger.info(f"[IntentBERT] Loaded model from {self._model_path}")
            return True

        except Exception as e:
            logger.error(f"[IntentBERT] Failed to load model: {e}")
            return False

    async def classify(self, text: str) -> Optional[dict]:
        """Classify intent.

        Args:
            text: User query text.

        Returns:
            {"type": task_type, "district": district, "confidence": float, "source": "bert_classifier"}
            or None if model not loaded.
        """
        if not self._load_model():
            return None

        try:
            # Tokenize
            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=128,
            )
            inputs = {k: v.to(self._device) for k, v in inputs.items()}

            # Predict
            with torch.no_grad():
                outputs = self._model(**inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=1)
                pred_label = torch.argmax(probs, dim=1).item()
                confidence = probs[0, pred_label].item()

            # Map back to district/task_type
            if pred_label not in self._reverse_label_map:
                logger.warning(f"[IntentBERT] Unknown label: {pred_label}")
                return None

            district, task_type = self._reverse_label_map[pred_label]

            return {
                "type": task_type,
                "district": district,
                "confidence": confidence,
                "source": "bert_classifier",
            }

        except Exception as e:
            logger.error(f"[IntentBERT] Classification failed: {e}")
            return None

    def train(self, dataset_path: str = "data/golden_intent_dataset.jsonl", epochs: int = 3, batch_size: int = 16) -> None:
        """Train classifier on golden dataset.

        Args:
            dataset_path: Path to JSONL dataset.
            epochs: Number of training epochs.
            batch_size: Batch size for training.
        """
        logger.info(f"[IntentBERT] Training on {dataset_path}...")

        # Load dataset
        examples = []
        with open(dataset_path, "r", encoding="utf-8") as f:
            for line in f:
                examples.append(json.loads(line))

        logger.info(f"[IntentBERT] Loaded {len(examples)} training examples")

        # Build label map
        labels = set()
        for ex in examples:
            labels.add((ex["district"], ex["task_type"]))

        self._label_map = {label: i for i, label in enumerate(sorted(labels))}
        self._reverse_label_map = {i: label for label, i in self._label_map.items()}

        logger.info(f"[IntentBERT] {len(self._label_map)} unique labels")

        # Load model
        from transformers import BertForSequenceClassification, BertTokenizer
        self._tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
        self._model = BertForSequenceClassification.from_pretrained(
            "bert-base-uncased",
            num_labels=len(self._label_map),
        )
        # Reinitialize classifier weights to ensure they're properly created
        self._model.classifier.weight.data.normal_(mean=0.0, std=0.02)
        self._model.classifier.bias.data.zero_()
        self._model.to(self._device)

        # Prepare data
        from torch.utils.data import Dataset, DataLoader

        class IntentDataset(Dataset):
            def __init__(self, examples, tokenizer, label_map):
                self.examples = examples
                self.tokenizer = tokenizer
                self.label_map = label_map

            def __len__(self):
                return len(self.examples)

            def __getitem__(self, idx):
                ex = self.examples[idx]
                encoding = self.tokenizer(
                    ex["text"],
                    padding="max_length",
                    truncation=True,
                    max_length=128,
                    return_tensors="pt",
                )
                label = self.label_map[(ex["district"], ex["task_type"])]
                return {
                    "input_ids": encoding["input_ids"].squeeze(),
                    "attention_mask": encoding["attention_mask"].squeeze(),
                    "labels": torch.tensor(label, dtype=torch.long),
                }

        dataset = IntentDataset(examples, self._tokenizer, self._label_map)
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        # Train
        from transformers import get_linear_schedule_with_warmup
        optimizer = torch.optim.AdamW(self._model.parameters(), lr=2e-5)
        total_steps = len(dataloader) * epochs
        scheduler = get_linear_schedule_with_warmup(
            optimizer,
            num_warmup_steps=int(0.1 * total_steps),
            num_training_steps=total_steps,
        )

        self._model.train()
        for epoch in range(epochs):
            total_loss = 0
            for batch in dataloader:
                batch = {k: v.to(self._device) for k, v in batch.items()}
                outputs = self._model(**batch)
                loss = outputs.loss
                total_loss += loss.item()

                loss.backward()
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()

            avg_loss = total_loss / len(dataloader)
            logger.info(f"[IntentBERT] Epoch {epoch+1}/{epochs}, Loss: {avg_loss:.4f}")

        # Save model
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "model": self._model,
            "label_map": self._label_map,
        }, self._model_path)

        logger.info(f"[IntentBERT] Model saved to {self._model_path}")

    def evaluate(self, dataset_path: str = "data/golden_intent_dataset.jsonl") -> dict:
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

        self._model.eval()
        correct = 0

        for ex in examples:
            text = ex["text"]
            expected_label = self._label_map.get((ex["district"], ex["task_type"]))
            if expected_label is None:
                continue

            # Tokenize
            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=128,
            )
            inputs = {k: v.to(self._device) for k, v in inputs.items()}

            # Predict
            with torch.no_grad():
                outputs = self._model(**inputs)
                pred_label = torch.argmax(outputs.logits, dim=1).item()

            if pred_label == expected_label:
                correct += 1

        accuracy = correct / len(examples) if examples else 0.0
        logger.info(f"[IntentBERT] Accuracy: {accuracy:.2%} ({correct}/{len(examples)})")

        return {"accuracy": accuracy, "correct": correct, "total": len(examples)}


if __name__ == "__main__":
    """Train or evaluate IntentBERT."""
    import argparse

    parser = argparse.ArgumentParser(description="IntentBERT classifier")
    parser.add_argument("--train", action="store_true", help="Train model")
    parser.add_argument("--evaluate", action="store_true", help="Evaluate model")
    parser.add_argument("--dataset", default="data/golden_intent_dataset.jsonl", help="Dataset path")
    args = parser.parse_args()

    classifier = IntentBERT()

    if args.train:
        classifier.train(args.dataset)
    elif args.evaluate:
        result = classifier.evaluate(args.dataset)
        print(f"\nEvaluation: {result['accuracy']:.2%} ({result['correct']}/{result['total']})")
    else:
        print("Use --train or --evaluate")
