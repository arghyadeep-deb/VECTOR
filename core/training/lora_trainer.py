"""LoRA adapter training with PEFT, Unsloth, or simulated fallback."""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Any

from loguru import logger
from core.training.training_config import AdapterConfig, TrainingArgs

try:
    import torch
    HAS_TORCH = torch.cuda.is_available()
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    if not torch.cuda.is_available():
        logger.warning("[Training] CUDA not available, training on CPU (slow)")
except ImportError:
    HAS_TORCH = False
    DEVICE = "cpu"
    logger.warning("[Training] torch not installed, using simulated training")


class LoRATrainer:
    def __init__(self, adapters_dir: str = "data/adapters"):
        self.adapters_dir = Path(adapters_dir)
        self.adapters_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[Training] LoRATrainer initialized (device={})", DEVICE)

    def train(self, adapter_config: AdapterConfig, training_args: TrainingArgs, dataset: list[dict]) -> dict:
        logger.info("[Training] Starting training for adapter '{}'", adapter_config.name)
        if not dataset:
            logger.warning("[Training] Empty dataset, cannot train")
            return {"status": "failed", "reason": "empty_dataset", "adapter": adapter_config.name}
        dataset_size = len(dataset)
        logger.info("[Training] Dataset size: {} examples", dataset_size)
        if self._should_simulate(adapter_config.base_model):
            return self._simulate_training(adapter_config, training_args, dataset_size)
        try:
            import transformers
            import peft
            return self._train_with_peft(adapter_config, training_args, dataset, dataset_size)
        except ImportError:
            try:
                import unsloth
                return self._train_with_unsloth(adapter_config, training_args, dataset, dataset_size)
            except ImportError:
                logger.warning("[Training] PEFT/Unsloth not available, simulating training")
                return self._simulate_training(adapter_config, training_args, dataset_size)

    @staticmethod
    def _extract_loss_history(trainer: Any) -> dict:
        """Pull initial/final train loss from the HF Trainer's own log history.

        self_improvement_cycle.py's eval gate (Phase 4C, "reject regressions")
        reads result["val_loss"]/result["initial_loss"] to decide whether an
        adapter regressed -- but neither key was ever populated by a real
        training run, only defaulted (0 / 1) at the read site, so the
        comparison `val_loss > 1.5 * initial_loss` was `0 > 1.5`, permanently
        False. No held-out eval split exists here (train_dataset only), so
        this is train loss, not true validation loss -- still a real signal
        the gate can act on, versus the permanent no-op it had before.
        """
        try:
            history = [h["loss"] for h in trainer.state.log_history if "loss" in h]
        except AttributeError:
            return {}
        if not history:
            return {}
        return {"initial_loss": history[0], "val_loss": history[-1]}

    def _should_simulate(self, base_model: str) -> bool:
        if os.environ.get("VECTOR_TRAINING_REAL") != "1":
            return True
        if os.environ.get("VECTOR_TRAINING_SIMULATE") == "1":
            return True
        model = (base_model or "").strip().lower()
        return model in {"test", "vector-test"} or model.startswith("test-")

    def _train_with_peft(self, config: AdapterConfig, args: TrainingArgs, dataset: list[dict], size: int) -> dict:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer
            from peft import LoraConfig, get_peft_model, TaskType
            logger.info("[Training] Loading base model '{}'", config.base_model)
            tokenizer = AutoTokenizer.from_pretrained(config.base_model, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            model = AutoModelForCausalLM.from_pretrained(
                config.base_model,
                torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
                device_map="auto" if DEVICE == "cuda" else None,
                trust_remote_code=True,
            )
            lora_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=config.rank,
                lora_alpha=config.alpha,
                lora_dropout=config.dropout,
                target_modules=config.target_modules,
            )
            model = get_peft_model(model, lora_config)
            model.print_trainable_parameters()
            texts = [ex.get("text", "") for ex in dataset if ex.get("text")]
            if not texts:
                return {"status": "failed", "reason": "no_text_data"}
            encodings = tokenizer(texts, truncation=True, padding=True, max_length=args.max_seq_length, return_tensors="pt")
            class TextDataset(torch.utils.data.Dataset):
                def __init__(self, encodings):
                    self.encodings = encodings
                def __getitem__(self, idx):
                    item = {k: v[idx] for k, v in self.encodings.items()}
                    # For causal LM, labels are the same as input_ids (shifted)
                    item["labels"] = item["input_ids"].clone()
                    return item
                def __len__(self):
                    return len(self.encodings.input_ids)
            train_dataset = TextDataset(encodings)
            training_args = TrainingArguments(
                output_dir=str(self.adapters_dir / config.name),
                per_device_train_batch_size=args.batch_size,
                gradient_accumulation_steps=args.gradient_accumulation_steps,
                num_train_epochs=args.num_epochs,
                learning_rate=args.learning_rate,
                warmup_steps=args.warmup_steps,
                logging_steps=10,
                save_strategy="epoch",
                fp16=DEVICE == "cuda",
                dataloader_num_workers=0,
            )
            trainer = Trainer(model=model, args=training_args, train_dataset=train_dataset)
            trainer.train()
            save_path = str(self.adapters_dir / config.name / "final")
            trainer.save_model(save_path)
            logger.info("[Training] PEFT training complete, saved to {}", save_path)
            result = {
                "status": "success",
                "method": "peft",
                "adapter": config.name,
                "base_model": config.base_model,
                "save_path": save_path,
                "train_samples": size,
                "epochs": args.num_epochs,
            }
            result.update(self._extract_loss_history(trainer))
            return result
        except Exception as e:
            logger.error("[Training] PEFT training failed: {}", e)
            return {"status": "failed", "reason": str(e), "adapter": config.name}

    def _train_with_unsloth(self, config: AdapterConfig, args: TrainingArgs, dataset: list[dict], size: int) -> dict:
        try:
            from unsloth import FastLanguageModel, is_bfloat16_supported
            dtype = torch.bfloat16 if is_bfloat16_supported() else torch.float16
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=config.base_model,
                max_seq_length=args.max_seq_length,
                dtype=dtype,
                load_in_4bit=True,
            )
            model = FastLanguageModel.get_peft_model(
                model,
                r=config.rank,
                lora_alpha=config.alpha,
                lora_dropout=config.dropout,
                target_modules=config.target_modules or ["q_proj", "k_proj", "v_proj", "o_proj"],
                use_gradient_checkpointing="unsloth",
            )
            texts = [ex.get("text", "") for ex in dataset if ex.get("text")]
            if not texts:
                return {"status": "failed", "reason": "no_text_data"}
            from unsloth import to_device
            tokens = to_device(tokenizer(texts, truncation=True, padding=True, max_length=args.max_seq_length, return_tensors="pt"))
            from transformers import TrainingArguments, Trainer
            training_args = TrainingArguments(
                output_dir=str(self.adapters_dir / config.name),
                per_device_train_batch_size=args.batch_size,
                gradient_accumulation_steps=args.gradient_accumulation_steps,
                num_train_epochs=args.num_epochs,
                learning_rate=args.learning_rate,
                warmup_steps=args.warmup_steps,
                logging_steps=10,
                save_strategy="epoch",
                fp16=not is_bfloat16_supported(),
                bf16=is_bfloat16_supported(),
            )
            trainer = Trainer(model=model, args=training_args, train_dataset=tokens)
            trainer.train()
            save_path = str(self.adapters_dir / config.name / "unsloth_final")
            model.save_pretrained(save_path)
            logger.info("[Training] Unsloth training complete, saved to {}", save_path)
            result = {
                "status": "success",
                "method": "unsloth",
                "adapter": config.name,
                "base_model": config.base_model,
                "save_path": save_path,
                "train_samples": size,
            }
            result.update(self._extract_loss_history(trainer))
            return result
        except Exception as e:
            logger.error("[Training] Unsloth training failed: {}", e)
            return {"status": "failed", "reason": str(e), "adapter": config.name}

    def _simulate_training(self, config: AdapterConfig, args: TrainingArgs, size: int) -> dict:
        import time
        logger.info("[Training] Simulating training for '{}' ({} samples, {} epochs)", config.name, size, args.num_epochs)
        total_steps = int(size / max(args.batch_size, 1) * args.num_epochs)
        for step in range(min(total_steps, 20)):
            time.sleep(0.05)
            if step % 5 == 0:
                logger.info("[Training] Simulated step {}/{}", step + 1, min(total_steps, 20))
        result = {
            "status": "success",
            "method": "simulated",
            "adapter": config.name,
            "base_model": config.base_model,
            "train_samples": size,
            "epochs": args.num_epochs,
            "final_loss": round(0.5 / (args.num_epochs ** 0.5), 4),
        }
        logger.info("[Training] Simulated training complete: {}", result)
        return result

    def save_adapter(self, adapter_config: AdapterConfig, result: dict) -> str:
        save_dir = self.adapters_dir / adapter_config.name
        save_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "name": adapter_config.name,
            "base_model": adapter_config.base_model,
            "rank": adapter_config.rank,
            "alpha": adapter_config.alpha,
            "dropout": adapter_config.dropout,
            "target_modules": adapter_config.target_modules,
            "training_result": result,
            "created_at": datetime.now().isoformat(),
        }
        manifest_path = save_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        logger.info("[Training] Adapter manifest saved to {}", manifest_path)
        return str(save_dir)

    def deploy_to_ollama(self, adapter_path: str, modelfile_template: str = "") -> bool:
        try:
            import subprocess
            adapter_name = Path(adapter_path).name
            modelfile_content = modelfile_template or f"FROM {adapter_path}\nPARAMETER temperature 0.7\n"
            modelfile_path = Path(adapter_path) / "Modelfile"
            modelfile_path.write_text(modelfile_content, encoding="utf-8")
            result = subprocess.run(
                ["ollama", "create", adapter_name, "-f", str(modelfile_path)],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                logger.info("[Training] Deployed adapter '{}' to Ollama", adapter_name)
                return True
            logger.warning("[Training] Ollama deploy failed: {}", result.stderr)
            return False
        except FileNotFoundError:
            logger.warning("[Training] Ollama CLI not found, skipping deploy")
            return False
        except Exception as e:
            logger.warning("[Training] Ollama deploy error: {}", e)
            return False

    def list_adapters(self) -> list[dict]:
        adapters = []
        for d in self.adapters_dir.iterdir():
            if d.is_dir():
                manifest_path = d / "manifest.json"
                if manifest_path.exists():
                    try:
                        data = json.loads(manifest_path.read_text(encoding="utf-8"))
                        adapters.append(data)
                    except Exception as e:
                        logger.warning("[Training] Failed to read manifest {}: {}", manifest_path, e)
        logger.info("[Training] Found {} adapters", len(adapters))
        return adapters
