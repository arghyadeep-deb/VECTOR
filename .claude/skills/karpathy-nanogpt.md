---
name: karpathy-nanogpt
description: Step-by-step implementation guide for karpathy/nanoGPT — use during 2AM Karpathy sessions when studying GPT-2 from scratch, or when building Phase 3 custom LLM training for VECTOR
---

# nanoGPT — Implementation Guide

## Purpose
Build a clean, minimal GPT-2 implementation from scratch. nanoGPT is the reference Karpathy uses to train a real GPT-2 (124M) on a single GPU in ~4 hours. VECTOR Phase 3 uses nanoGPT as the base training script before customizing into vector-gpt.

## Key Files to Study (in order)
1. `model.py` — the full GPT model: `CausalSelfAttention`, `MLP`, `Block`, `GPT`. ~300 lines total.
2. `train.py` — training loop with gradient accumulation, cosine LR, DDP multi-GPU support
3. `config/` — `train_gpt2.py` is the canonical training config (hyperparams for 124M GPT-2)
4. `data/` — `prepare.py` for OpenWebText tokenization via tiktoken

## Implementation Steps
1. Read `model.py` in full — understand each class before touching train.py
2. Reproduce `CausalSelfAttention` by hand: Q/K/V projections, scaled dot-product, causal mask, output projection
3. Reproduce `Block`: layernorm → attention → layernorm → MLP (GELU activation)
4. Reproduce `GPT.__init__`: token embed + position embed → N blocks → final layernorm → lm_head
5. Reproduce `GPT.forward`: embed → blocks → norm → logits → cross-entropy loss
6. Study `train.py` gradient accumulation: `micro_batch × accumulation_steps = effective_batch`
7. Phase 3 adaptation: swap `tiktoken` for a VECTOR-specific BPE vocab (minbpe), add LoRA layers for efficient fine-tuning

## Key Concepts
- **Weight tying**: `wte` (token embed) and `lm_head` share weights — critical for memory efficiency
- **Flash Attention**: `torch.nn.functional.scaled_dot_product_attention` with `is_causal=True` — use this, not manual softmax
- **Gradient accumulation**: nanoGPT's main trick for training large batches on a single GPU
- **`configure_optimizers`**: separates weight-decay from non-weight-decay parameters — copy this pattern exactly

## VECTOR Application
Phase 3 target: fine-tune nanoGPT on VECTOR's distilled knowledge (LightRAG exports) to create a lightweight local model for District 2's council. The 124M param GPT-2 fits in ~500MB VRAM — leaves headroom on the RTX 5070 Ti. Study `model.py` deeply before Phase 3 begins. The clean architecture is the point — resist any urge to add complexity before you can train baseline GPT-2 from scratch.
