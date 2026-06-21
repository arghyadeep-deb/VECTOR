# train-llm-from-scratch — Absorption Analysis

> Authored by Opus (parallel agent hit session limit before writing; recovered from recon).

**Verdict:** IMPLEMENT (selective) — absorb the **post-training suite** (SFT · Reward Model · DPO/GRPO) adapted to VECTOR's small/LoRA scale, fed from VECTOR's reasoning_chains. Skip the from-scratch pretraining (GPU-infeasible here).

**What it is:** Pure-PyTorch (no `trl`/`peft`/`transformers`) implementation of: (a) transformer pretraining from scratch, and (b) a complete post-training pipeline — **SFT → Reward Model → {PPO, DPO/ORPO/KTO} → GRPO/RLVR** — on real datasets (Alpaca, Dolly, Anthropic HH-RLHF, UltraFeedback, GSM8K), multi-GPU DDP+bf16. License: MIT. Vendor expectation: ~400M model needs 2×H100 to be coherent.

**VECTOR already has:** `core/training/openmythos/` (train.py, trainer.py, data_prep, export_to_ollama, forward) — **pretraining-focused** (the OpenMythos RDT path). Plus `core/training/`: `lora_trainer.py`, `continuous_rl_trainer.py`, `knowledge_distiller.py`, `self_improvement_cycle.py`, `eval_harness.py`. And `vectorcode/src/neural_training.py` (A2C/DQN/PPO/SARSA/Q-Learning/DecisionTransformer — but these are **RL for the decision engine**, not LLM alignment). `districts/karpathy_lab/` for the learning track.

**Overlap %:** ~30%. Pretraining overlaps OpenMythos (and is infeasible on 1×RTX 5070 Ti 12 GB, so not worth duplicating). LoRA overlaps `lora_trainer.py`. **The genuine non-overlap is the LLM post-training/alignment pipeline (SFT/RM/DPO/GRPO) — VECTOR does NOT have this.**

**Genuine gaps worth absorbing:**
- **SFT trainer** on instruction data — feeds directly from VECTOR's `reasoning_memory` reasoning_chains (RULE 8 training data). HIGH value: this is the missing bridge between "VECTOR stores its reasoning" and "VECTOR trains a model on it." Fits 12 GB at small/LoRA scale.
- **DPO / GRPO** (preference + verifiable-reward RL) — aligns a small/LoRA model on VECTOR's accepted-vs-rejected decisions (counterfactual.py already tracks rejections → preference pairs!). HIGH value, conceptually fits VECTOR's Darwinian/feedback loop. Pure PyTorch, runnable at LoRA scale.
- **Reward Model** trainer — moderate value; pairs with policy/HP signal.
- From-scratch pretraining + PPO-at-scale → SKIP (need H100-class compute).

**If UPGRADE — what to replace & risk:** Not a replacement — an *addition* to `core/training/`. Reuse OpenMythos's data_prep/export_to_ollama seams. Low risk (new modules, gated, run offline/overnight per VECTOR's airllm/overnight pattern).

**Integration plan:** (1) `core/training/post_training/` — port SFT, DPO, GRPO trainers (pure PyTorch, small/LoRA config for 12 GB). (2) `core/training/reasoning_chain_dataset.py` — adapter: `reasoning_memory` chains (reward>0.7) → SFT pairs; `counterfactual` accepted/rejected → DPO preference pairs. (3) Wire into `weekly_scheduler.py` / a Hand for overnight runs. (4) Export via existing `export_to_ollama.py`. Effort: 2–3 sessions; owner runs the actual training overnight.

**Recommendation:** **IMPLEMENT the post-training half.** This is the single most strategically valuable repo of the five for VECTOR's long game — it closes the loop "VECTOR reasons → stores chains → trains its own aligned model on them," which is exactly the vector-chairman / OpenMythos endgame in your roadmap. Skip pretraining-from-scratch (compute-infeasible). Adapt everything to LoRA/small scale for the 12 GB GPU.
