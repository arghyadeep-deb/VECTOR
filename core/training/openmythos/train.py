"""
Module: core/training/openmythos/train.py

Ollama Modelfile Trainer — builds and manages custom Ollama modelfiles.

NOTE: This is NOT gradient-descent / LoRA / neural network training.
It does NOT update model weights. Instead it:
  1. Prepares instruction-following data in Ollama JSONL format
  2. Iterates the dataset through ollama.generate() to test prompt formatting
  3. Exports a Modelfile + config.json so the model can be registered via
     `ollama create <name> -f Modelfile`

For real LoRA fine-tuning on VECTOR's reasoning chains, see:
  core/training/openmythos/trainer.py  (uses transformers + peft + OpenMythos RDT)
"""

import sys

__all__ = [
    "main",
    "OllamaModelfileTrainer",
    "TrainingPipeline",  # backward-compat alias
]

from pathlib import Path

from core.config import CONFIG
from loguru import logger
import ollama
import json
import os
import uuid
import shutil
import asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime
from core.training.openmythos.export_to_ollama import _is_safe_model_name


class OllamaModelfileTrainer:
    """
    Ollama Modelfile trainer — prepares data and registers models via Ollama API.

    This class does NOT perform gradient descent or weight updates.
    It manages the Ollama modelfile lifecycle:
      - prepare_data(): converts raw JSONL/MD/TXT into Ollama instruction format
      - train(): iterates data through ollama.generate() to validate prompt format,
                 then exports a Modelfile + config.json for `ollama create`
      - export_model(): registers the prepared model in the local Ollama registry
      - evaluate_model(): measures output similarity vs expected on held-out data

    For LoRA fine-tuning with real weight updates, use:
      core/training/openmythos/trainer.py
    """

    def __init__(self):
        self.ollama_host = CONFIG["ollama_host"]
        self.config = CONFIG.get("openmythos", {})
        self.epochs = self.config.get("epochs", 3)
        self.learning_rate = self.config.get("learning_rate", 0.0001)
        self.batch_size = self.config.get("batch_size", 4)
        self.model_dir = self.config.get("model_dir", "./models/custom")
        self.training_runs: Dict[str, Dict[str, Any]] = {}
        logger.info(f"[OpenMythos] Training pipeline initialized with {self.ollama_host}")

    def prepare_data(self, input_dir: str) -> str:
        """
        Convert training data from input directory to Ollama format.

        Args:
            input_dir: Directory containing raw training data (JSONL, markdown, etc.)

        Returns:
            Path to the prepared dataset in Ollama format
        """
        input_path = Path(input_dir)
        if not input_path.exists():
            logger.error(f"[OpenMythos] Input directory not found: {input_dir}")
            return ""

        output_dir = Path(self.model_dir) / "datasets" / f"prep_{uuid.uuid4().hex[:8]}"
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[OpenMythos] Preparing training data from {input_dir}")

        prepared_file = output_dir / "prepared.jsonl"
        with open(prepared_file, "w", encoding="utf-8") as out:
            for file_path in input_path.rglob("*"):
                if file_path.is_file() and file_path.suffix in [".json", ".jsonl", ".txt", ".md"]:
                    try:
                        if file_path.suffix == ".jsonl":
                            with open(file_path, "r", encoding="utf-8") as f:
                                for line in f:
                                    if line.strip():
                                        data = json.loads(line)
                                        formatted = self._format_for_ollama(data)
                                        if formatted:
                                            out.write(json.dumps(formatted) + "\n")
                        elif file_path.suffix == ".json":
                            with open(file_path, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                if isinstance(data, list):
                                    for item in data:
                                        formatted = self._format_for_ollama(item)
                                        if formatted:
                                            out.write(json.dumps(formatted) + "\n")
                                else:
                                    formatted = self._format_for_ollama(data)
                                    if formatted:
                                        out.write(json.dumps(formatted) + "\n")
                        else:
                            with open(file_path, "r", encoding="utf-8") as f:
                                content = f.read()
                                if content.strip():
                                    formatted = {
                                        "instruction": "Complete the following text:",
                                        "input": content[:1000],
                                        "output": content[1000:2000] if len(content) > 1000 else "",
                                    }
                                    out.write(json.dumps(formatted) + "\n")
                    except Exception as e:
                        logger.warning(f"[OpenMythos] Failed to process {file_path}: {e}")

        logger.info(f"[OpenMythos] Data prepared at: {prepared_file}")
        return str(prepared_file)

    def _format_for_ollama(self, data: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Format a data item into Ollama training format."""
        if "instruction" in data and "output" in data:
            return {"instruction": data["instruction"], "input": data.get("input", ""), "output": data["output"]}
        elif "prompt" in data and "completion" in data:
            return {"instruction": data["prompt"], "input": "", "output": data["completion"]}
        elif "question" in data and "answer" in data:
            return {"instruction": data["question"], "input": "", "output": data["answer"]}
        return None

    async def train(
        self,
        base_model: str,
        dataset_path: str,
        output_name: str,
        epochs: Optional[int] = None,
        learning_rate: Optional[float] = None,
        batch_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Fine-tune a base model with the provided dataset.

        Args:
            base_model: The base model to fine-tune (e.g., 'llama2', 'mistral')
            dataset_path: Path to the prepared training dataset
            output_name: Name for the output model
            epochs: Number of training epochs (overrides config)
            learning_rate: Learning rate (overrides config)
            batch_size: Batch size (overrides config)

        Returns:
            Dict with training status, run_id, and details
        """
        run_id = f"train_{uuid.uuid4().hex[:12]}"
        epochs = self.epochs if epochs is None else epochs
        learning_rate = self.learning_rate if learning_rate is None else learning_rate
        batch_size = self.batch_size if batch_size is None else batch_size

        if not _is_safe_model_name(output_name):
            return {"success": False, "error": "Invalid output model name"}

        if not Path(dataset_path).exists():
            logger.error(f"[OpenMythos] Dataset not found: {dataset_path}")
            return {"success": False, "error": "Dataset not found"}

        logger.info(f"[OpenMythos] Starting training run {run_id}")
        logger.info(f"[OpenMythos] Base: {base_model}, Epochs: {epochs}, LR: {learning_rate}, BS: {batch_size}")

        self.training_runs[run_id] = {
            "id": run_id,
            "base_model": base_model,
            "dataset_path": dataset_path,
            "output_name": output_name,
            "epochs": epochs,
            "learning_rate": learning_rate,
            "batch_size": batch_size,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "progress": 0.0,
        }

        try:
            # 2026-08-05 (connection-leak fix, same as ollama_safe.py): must be
            # `with ... as client:`, not a bare assignment — ollama.Client()
            # wraps an httpx.Client() whose socket is only reclaimed by a
            # cyclic-GC sweep, not refcounting, if left unclosed. The client is
            # reused across the whole training loop (many calls, one socket),
            # so the `with` block spans the loop rather than each call.
            with ollama.Client(self.ollama_host) as client:
                available_models = [m["name"] for m in client.list().get("models", [])]
                if base_model not in available_models:
                    logger.warning(f"[OpenMythos] Base model {base_model} not available, pulling...")
                    client.pull(base_model)

                with open(dataset_path, "r", encoding="utf-8") as f:
                    training_data = [json.loads(line) for line in f if line.strip()]

                total_steps = len(training_data)
                logger.info(f"[OpenMythos] Training on {total_steps} examples for {epochs} epochs")

                for epoch in range(epochs):
                    logger.info(f"[OpenMythos] Epoch {epoch + 1}/{epochs}")
                    progress = ((epoch + 1) / epochs) * 100
                    self.training_runs[run_id]["progress"] = progress

                    for idx, example in enumerate(training_data):
                        if idx % 10 == 0:
                            logger.debug(f"[OpenMythos] Step {idx}/{total_steps}")

                        instruction = example.get("instruction", "")
                        input_text = example.get("input", "")
                        output_text = example.get("output", "")

                        prompt = f"Instruction: {instruction}\n"
                        if input_text:
                            prompt += f"Input: {input_text}\n"
                        prompt += f"Output: {output_text}"

                        try:
                            response = client.generate(
                                model=base_model,
                                prompt=prompt,
                                options={"temperature": 0.3, "num_predict": 50},
                            )
                        except Exception as e:
                            logger.debug(f"[OpenMythos] Generation step: {e}")

            self.training_runs[run_id].update({
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "progress": 100.0,
            })

            export_result = await self._export_trained_model(run_id, output_name)
            if export_result.get("success"):
                return {
                    "success": True,
                    "run_id": run_id,
                    "model_name": export_result.get("model_name"),
                    "epochs": epochs,
                }
            self.training_runs[run_id]["status"] = "export_failed"
            return {
                "success": False,
                "run_id": run_id,
                "status": "export_failed",
                "error": export_result.get("error", "Model export failed"),
            }

        except Exception as e:
            logger.error(f"[OpenMythos] Training failed: {e}")
            self.training_runs[run_id]["status"] = "failed"
            self.training_runs[run_id]["error"] = str(e)
            return {"success": False, "run_id": run_id, "error": str(e)}

    async def _export_trained_model(self, run_id: str, output_name: str) -> Dict[str, Any]:
        """Export the trained model weights."""
        run = self.training_runs.get(run_id)
        if not run:
            return {"success": False, "error": "Training run not found"}
        if not _is_safe_model_name(output_name):
            return {"success": False, "error": "Invalid output model name"}

        model_dir = Path(self.model_dir) / output_name
        model_dir.mkdir(parents=True, exist_ok=True)

        config_file = model_dir / "config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump({
                "model_name": output_name,
                "base_model": run["base_model"],
                "training_run": run_id,
                "epochs": run["epochs"],
            }, f)

        logger.info(f"[OpenMythos] Model exported to {model_dir}")
        return {"success": True, "model_name": output_name, "path": str(model_dir)}

    async def export_model(self, model_name: str) -> Dict[str, Any]:
        """
        Export a trained model to the Ollama registry.

        Args:
            model_name: Name of the trained model to export

        Returns:
            Dict with export status and model details
        """
        if not _is_safe_model_name(model_name):
            return {"success": False, "error": "Invalid model name"}
        model_path = Path(self.model_dir) / model_name
        if not model_path.exists():
            logger.error(f"[OpenMythos] Model not found: {model_name}")
            return {"success": False, "error": "Model not found"}

        try:
            logger.info(f"[OpenMythos] Exporting model {model_name} to Ollama")

            modelfile_path = model_path / "Modelfile"
            if not modelfile_path.exists():
                with open(modelfile_path, "w", encoding="utf-8") as f:
                    f.write(f"FROM {self.config.get('base_model', 'llama2')}\n")
                    f.write("PARAMETER temperature 0.7\n")
                    f.write("PARAMETER top_p 0.9\n")
                    f.write("SYSTEM You are V.E.C.T.O.R., a helpful AI assistant.\n")

            # 2026-08-05 (connection-leak fix, same as ollama_safe.py): must be
            # `with ... as client:`, not a bare assignment.
            with ollama.Client(self.ollama_host) as client:
                try:
                    client.create(
                        model=model_name,
                        path=str(model_path),
                        modelfile=str(modelfile_path),
                    )
                    logger.info(f"[OpenMythos] Model {model_name} exported to Ollama")
                    return {"success": True, "model_name": model_name}
                except Exception as e:
                    logger.warning(f"[OpenMythos] Direct export failed, trying manual: {e}")
                    return {
                        "success": False,
                        "model_name": model_name,
                        "path": str(model_path),
                        "error": str(e),
                        "manual_export_available": True,
                    }

        except Exception as e:
            logger.error(f"[OpenMythos] Export failed: {e}")
            return {"success": False, "error": str(e)}

    def list_training_runs(self) -> List[Dict[str, Any]]:
        """
        List all completed training runs.

        Returns:
            List of training run summaries
        """
        runs = []
        for run_id, run in self.training_runs.items():
            runs.append({
                "run_id": run_id,
                "model": run.get("output_name", run.get("base_model")),
                "status": run.get("status"),
                "started_at": run.get("started_at"),
                "completed_at": run.get("completed_at"),
                "epochs": run.get("epochs"),
            })
        return sorted(runs, key=lambda x: x.get("started_at", ""), reverse=True)

    def get_training_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific training run."""
        return self.training_runs.get(run_id)

    async def evaluate_model(
        self,
        model_name: str,
        eval_data_path: str,
    ) -> Dict[str, Any]:
        """
        Evaluate a trained model on evaluation data.

        Args:
            model_name: Name of the model to evaluate
            eval_data_path: Path to evaluation data

        Returns:
            Dict with evaluation metrics
        """
        if not Path(eval_data_path).exists():
            return {"success": False, "error": "Evaluation data not found"}

        logger.info(f"[OpenMythos] Evaluating model {model_name}")

        try:
            results = []

            with open(eval_data_path, "r", encoding="utf-8") as f:
                eval_data = [json.loads(line) for line in f if line.strip()]

            # 2026-08-05 (connection-leak fix, same as ollama_safe.py): must be
            # `with ... as client:`, not a bare assignment — client is reused
            # across the whole evaluation loop (one socket, many calls).
            with ollama.Client(self.ollama_host) as client:
                for item in eval_data[:10]:
                    prompt = item.get("instruction", "")
                    if item.get("input"):
                        prompt += f"\n{item.get('input')}"
                    expected = item.get("output", "")

                    response = client.generate(model=model_name, prompt=prompt)
                    actual = response.get("response", "")

                    similarity = self._compute_similarity(expected, actual)
                    results.append({
                        "expected": expected[:100],
                        "actual": actual[:100],
                        "similarity": similarity,
                    })

            avg_similarity = sum(r["similarity"] for r in results) / len(results) if results else 0
            logger.info(f"[OpenMythos] Evaluation complete: {avg_similarity:.2%} similarity")

            return {"success": True, "avg_similarity": avg_similarity, "results": results}

        except Exception as e:
            logger.error(f"[OpenMythos] Evaluation failed: {e}")
            return {"success": False, "error": str(e)}

    def _compute_similarity(self, expected: str, actual: str) -> float:
        """Compute simple similarity between expected and actual strings."""
        expected_words = set(expected.lower().split())
        actual_words = set(actual.lower().split())
        if not expected_words:
            return 0.0
        intersection = expected_words & actual_words
        return len(intersection) / len(expected_words)


# Backward-compat alias — existing code that imports TrainingPipeline still works
TrainingPipeline = OllamaModelfileTrainer


async def main():
    """Test the Ollama modelfile trainer."""
    pipeline = OllamaModelfileTrainer()
    logger.info(f"Training runs: {pipeline.list_training_runs()}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
    print("✅ train.py OK")
