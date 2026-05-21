"""VECTOR Training - Adaptive Learning: LoRA fine-tuning, evaluation, self-improvement, RL, distillation."""

from core.training.training_config import AdapterConfig, TrainingArgs, EvalConfig
from core.training.data_collector import DataCollector
from core.training.lora_trainer import LoRATrainer
from core.training.eval_harness import EvalHarness, EvalResult
from core.training.self_improvement_cycle import SelfImprovementCycle
from core.training.continuous_rl_trainer import ContinuousRLTrainer
from core.training.knowledge_distiller import KnowledgeDistiller, DistillationResult
from core.training.benchmarks import CodingBenchmark, ResearchBenchmark

__all__ = [
    "AdapterConfig",
    "TrainingArgs",
    "EvalConfig",
    "DataCollector",
    "LoRATrainer",
    "EvalHarness",
    "EvalResult",
    "SelfImprovementCycle",
    "ContinuousRLTrainer",
    "KnowledgeDistiller",
    "DistillationResult",
    "CodingBenchmark",
    "ResearchBenchmark",
]
