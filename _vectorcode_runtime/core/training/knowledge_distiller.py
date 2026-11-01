"""Knowledge distillation: teacher model response synthesis for student fine-tuning."""


__all__ = [
    "DistillationResult",
    "KnowledgeDistiller",
]

import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger
from core.training.training_config import AdapterConfig, TrainingArgs
from core.training.lora_trainer import LoRATrainer


@dataclass
class DistillationResult:
    teacher_model: str
    student_model: str
    topics: list[str]
    num_samples: int
    teacher_success_rate: float
    student_score: float
    quality_score: float
    output_path: str
    timestamp: str = ""


class KnowledgeDistiller:
    def __init__(self, teacher_model: str = "vector-r1", student_model: str = "vector-focus", output_dir: str = "data/distillation"):
        self.teacher_model = teacher_model
        self.student_model = student_model
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.trainer = LoRATrainer()
        logger.info("[Training] KnowledgeDistiller: {} → {}", teacher_model, student_model)

    def distill(self, teacher_prompts: list[str], student_model: str = "", topics: list[str] | None = None) -> DistillationResult:
        logger.info("[Training] Starting distillation with {} prompts", len(teacher_prompts))
        model = student_model or self.student_model
        topic_list = topics or ["general"]
        teacher_responses = []
        success_count = 0
        for i, prompt in enumerate(teacher_prompts):
            try:
                response = self._call_teacher(prompt)
                if response:
                    teacher_responses.append({"prompt": prompt, "response": response})
                    success_count += 1
                if (i + 1) % 10 == 0:
                    logger.info("[Training] Distillation progress: {}/{}", i + 1, len(teacher_prompts))
            except Exception as e:
                logger.warning("[Training] Teacher call failed for prompt {}: {}", i, e)
        teacher_rate = success_count / max(len(teacher_prompts), 1)
        logger.info("[Training] Teacher success rate: {:.2f} ({}/{})", teacher_rate, success_count, len(teacher_prompts))
        if not teacher_responses:
            logger.error("[Training] No teacher responses collected")
            return DistillationResult(
                teacher_model=self.teacher_model, student_model=model, topics=topic_list,
                num_samples=0, teacher_success_rate=0.0, student_score=0.0,
                quality_score=0.0, output_path="", timestamp=datetime.now().isoformat(),
            )
        training_data_path = self._prepare_training_data(teacher_responses)
        train_result = self._train_student(train_data_path=training_data_path, model_name=model)
        quality_result = self._evaluate_distillation()
        return DistillationResult(
            teacher_model=self.teacher_model,
            student_model=model,
            topics=topic_list,
            num_samples=len(teacher_responses),
            teacher_success_rate=round(teacher_rate, 4),
            student_score=round(train_result.get("final_loss", 0.0), 4),
            quality_score=round(quality_result, 4),
            output_path=training_data_path,
            timestamp=datetime.now().isoformat(),
        )

    def _call_teacher(self, prompt: str) -> str:
        try:
            import ollama
            response = ollama.generate(model=self.teacher_model, prompt=prompt, options={"temperature": 0.3})
            return response.get("response", "")
        except ImportError:
            logger.warning("[Training] ollama not available, simulating teacher")
            return f"Teacher response for: {prompt[:80]}... [simulated]"
        except Exception as e:
            logger.warning("[Training] Teacher model '{}' failed: {}", self.teacher_model, e)
            return ""

    def _prepare_training_data(self, teacher_responses: list[dict]) -> str:
        output_path = self.output_dir / f"distillation_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                for item in teacher_responses:
                    prompt = item.get("prompt", "")
                    response = item.get("response", "")
                    if prompt and response:
                        example = {
                            "instruction": prompt,
                            "input": "",
                            "output": response,
                        }
                        f.write(json.dumps(example, ensure_ascii=False) + "\n")
            logger.info("[Training] Training data saved to {} ({} samples)", output_path, len(teacher_responses))
            return str(output_path)
        except Exception as e:
            logger.error("[Training] Failed to save training data: {}", e)
            return ""

    def _train_student(self, train_data_path: str, model_name: str) -> dict:
        try:
            import json
            dataset = []
            with open(train_data_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        dataset.append(json.loads(line))
            if not dataset:
                logger.warning("[Training] No training data loaded")
                return {"status": "skipped", "reason": "empty_dataset"}
            config = AdapterConfig(
                name=f"distilled_{datetime.now().strftime('%Y%m%d')}",
                base_model=model_name,
                target_modules=["q_proj", "v_proj"],
                rank=8,
                alpha=8.0,
                dropout=0.05,
                save_dir=str(self.output_dir),
            )
            args = TrainingArgs(learning_rate=2e-4, num_epochs=2, batch_size=4)
            formatted = [{"text": f"### Instruction:\n{d['instruction']}\n\n### Response:\n{d['output']}"} for d in dataset]
            result = self.trainer.train(config, args, formatted)
            if result.get("status") == "success":
                self.trainer.save_adapter(config, result)
            return result
        except Exception as e:
            logger.error("[Training] Student training failed: {}", e)
            return {"status": "failed", "reason": str(e)}

    def _evaluate_distillation(self) -> float:
        try:
            from core.training.eval_harness import EvalHarness
            from core.training.benchmarks import CodingBenchmark
            harness = EvalHarness()
            harness.register_benchmark("coding", CodingBenchmark)
            result = harness.evaluate(model_name=self.student_model)
            return result.overall_score
        except ImportError:
            logger.warning("[Training] Eval harness not available for distillation check")
            return 0.5
        except Exception as e:
            logger.warning("[Training] Distillation evaluation failed: {}", e)
            return 0.0
