"""
Module: agents/districts/karpathy_lab/architecture_builder.py
District: karpathy_lab | Focus: Neural architecture design for LLM training
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, math
from typing import Optional


class ArchitectureBuilder(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ArchitectureBuilder",
            district="karpathy_lab",
            generation=1
        )
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.supported_architectures = ["transformer", "lstm", "moe", "mamba", "hyena"]
        logger.info("[VECTOR][karpathy_lab] ArchitectureBuilder ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )

    def design_architecture(self, model_type: str, params: dict) -> dict:
        logger.info(f"[VECTOR][karpathy_lab] Designing {model_type} architecture")
        self.add_lesson({"action": "design_architecture", "model_type": model_type, "params": params})

        architecture = {
            "type": model_type,
            "config": {
                "hidden_size": params.get("hidden_size", 4096),
                "num_layers": params.get("num_layers", 32),
                "num_attention_heads": params.get("num_attention_heads", 32),
                "intermediate_size": params.get("intermediate_size", 11008),
                "vocab_size": params.get("vocab_size", 32000),
                "max_position_embeddings": params.get("max_position_embeddings", 8192),
                "rope_theta": params.get("rope_theta", 10000.0),
                "rms_norm_eps": params.get("rms_norm_eps", 1e-6),
                "initializer_range": params.get("initializer_range", 0.02),
                "use_cache": True,
                "pad_token_id": params.get("pad_token_id", 0),
                "bos_token_id": params.get("bos_token_id", 1),
                "eos_token_id": params.get("eos_token_id", 2),
            },
            "precision": params.get("precision", "bf16"),
            "activation": params.get("activation", "silu"),
            "created_by": self.name,
            "created_at": self.last_active,
        }

        prompt = f"Analyze this architecture config for a {model_type} model: {json.dumps(architecture['config'], indent=2)}. Provide a concise critique focusing on potential bottlenecks and recommended tweaks."
        critique = self._call_ollama(prompt)
        architecture["critique"] = critique

        self.memory.store(
            event_type="architecture_design",
            content=f"Designed {model_type} architecture: {architecture['type']}",
            tags=["architecture", model_type],
            context=architecture,
            source="ArchitectureBuilder"
        )

        logger.info(f"[VECTOR][karpathy_lab] Architecture design complete: {model_type}")
        return architecture

    def generate_config(self, architecture: dict) -> dict:
        logger.info("[VECTOR][karpathy_lab] Generating training config")
        self.add_lesson({"action": "generate_config", "architecture": architecture.get("type")})

        base_config = {
            "model_name": architecture.get("type", "unnamed"),
            "training": {
                "learning_rate": 3e-4,
                "batch_size": 8,
                "gradient_accumulation_steps": 4,
                "max_steps": 100000,
                "warmup_steps": 2000,
                "weight_decay": 0.1,
                "clip_grad_norm": 1.0,
                "optimizer": "adamw",
                "scheduler": "cosine",
                "beta1": 0.9,
                "beta2": 0.999,
                "epsilon": 1e-8,
            },
            "data": {
                "train_path": "./data/train.parquet",
                "val_path": "./data/val.parquet",
                "seq_length": 4096,
                "prefetch_buffer": 16,
                "num_workers": 4,
            },
            "hardware": {
                "num_gpus": 1,
                "gpu_memory_gb": 16,
                "use_mixed_precision": True,
                "gradient_checkpointing": True,
            },
            "logging": {
                "log_interval": 10,
                "eval_interval": 1000,
                "save_interval": 5000,
                "project_name": "vector-training",
            }
        }

        if architecture.get("precision") == "fp8":
            base_config["hardware"]["use_fp8"] = True

        config_yaml = f"""# Training config for {architecture.get('type')}
model:
  type: {architecture.get('type')}
  architecture: {json.dumps(architecture['config'], indent=2)}

training:
  learning_rate: {base_config['training']['learning_rate']}
  batch_size: {base_config['training']['batch_size']}
  gradient_accumulation_steps: {base_config['training']['gradient_accumulation_steps']}
  max_steps: {base_config['training']['max_steps']}
  warmup_steps: {base_config['training']['warmup_steps']}
  optimizer: {base_config['training']['optimizer']}
  scheduler: {base_config['training']['scheduler']}

data:
  train_path: {base_config['data']['train_path']}
  val_path: {base_config['data']['val_path']}
  seq_length: {base_config['data']['seq_length']}

hardware:
  num_gpus: {base_config['hardware']['num_gpus']}
  use_mixed_precision: {base_config['hardware']['use_mixed_precision']}
  gradient_checkpointing: {base_config['hardware']['gradient_checkpointing']}
"""
        base_config["config_yaml"] = config_yaml

        self.memory.store(
            event_type="config_generated",
            content=f"Generated training config for {architecture.get('type')}",
            tags=["config", "training"],
            context=base_config,
            source="ArchitectureBuilder"
        )

        return base_config

    def estimate_compute(self, architecture: dict) -> dict:
        logger.info("[VECTOR][karpathy_lab] Estimating compute requirements")
        self.add_lesson({"action": "estimate_compute", "architecture": architecture.get("type")})

        config = architecture.get("config", {})
        hidden = config.get("hidden_size", 4096)
        layers = config.get("num_layers", 32)
        heads = config.get("num_attention_heads", 32)
        seq_len = config.get("max_position_embeddings", 8192)

        head_dim = hidden // heads
        flops_per_layer = 4 * hidden * hidden * seq_len + 2 * hidden * seq_len * hidden // heads * heads
        total_flops = flops_per_layer * layers
        flops_per_token = 6 * hidden * (1 + (hidden // heads) + seq_len / hidden)
        estimated_flops = flops_per_token * layers * 1e-9

        params_billion = (hidden * hidden * 4 * layers) / 1e9

        bytes_per_param = {"fp32": 4, "bf16": 2, "fp16": 2, "fp8": 1}
        prec = architecture.get("precision", "bf16")
        model_size_gb = params_billion * bytes_per_param.get(prec, 2)

        activation_memory = (layers * hidden * seq_len * 12) / 1e9
        total_memory_gb = model_size_gb * 1.2 + activation_memory

        estimate = {
            "parameters_billion": round(params_billion, 2),
            "estimated_tflops_per_token": round(estimated_flops, 2),
            "total_flops_per_forward_pass": total_flops,
            "model_size_gb": round(model_size_gb, 2),
            "activation_memory_gb": round(activation_memory, 2),
            "total_memory_gb_estimate": round(total_memory_gb, 2),
            "precision": prec,
            "estimated_vram_per_gpu": round(total_memory_gb / 0.65, 2),
            "recommended_gpus": math.ceil(total_memory_gb / 16),
            "estimated_training_time_hours": round(params_billion * 1.5, 1),
        }

        self.memory.store(
            event_type="compute_estimated",
            content=f"Compute estimate for {architecture.get('type')}: {estimate['parameters_billion']}B params",
            tags=["compute", "estimation"],
            context=estimate,
            source="ArchitectureBuilder"
        )

        logger.info(f"[VECTOR][karpathy_lab] Compute estimate: {estimate['parameters_billion']}B params, {estimate['estimated_tflops_per_token']} TFLOPs/token")
        return estimate


    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        result = self.generate_config(p.get("architecture", {}))
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = ArchitectureBuilder()
    assert agent.health_points == 500
    assert agent.district == "karpathy_lab"

    arch = agent.design_architecture("transformer", {"hidden_size": 2048, "num_layers": 12})
    assert arch["type"] == "transformer"
    assert "config" in arch

    config = agent.generate_config(arch)
    assert "training" in config
    assert "learning_rate" in config["training"]

    estimate = agent.estimate_compute(arch)
    assert "parameters_billion" in estimate
    assert estimate["parameters_billion"] > 0

    print("✅ architecture_builder.py OK")