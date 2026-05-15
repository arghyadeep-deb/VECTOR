<!-- VECTOR-INGESTED ASSET
  Source: .claude/skills/karpathy-build-nanogpt.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:55+00:00
-->

---
name: karpathy-build-nanogpt
description: Step-by-step guide for karpathy/build-nanogpt — use during 2AM sessions to follow the YouTube "Let's build GPT-2 from scratch" walkthrough, the definitive companion to nanoGPT
---

# build-nanogpt — Implementation Guide

## Purpose
This is Karpathy's 4-hour YouTube lecture repo: "Let's reproduce GPT-2 (124M)". It walks through building and training GPT-2 from scratch, then actually reproducing GPT-2's performance on a single GPU. More pedagogically structured than nanoGPT — better for first-pass learning.

## Key Files to Study (in order)
1. `train_gpt2.py` — the complete implementation built up live during the lecture (~1,000 lines final)
2. `README.md` — links to the YouTube video with timestamp index (use this to jump to specific concepts)
3. The lecture itself (YouTube, ~4 hours) — Karpathy builds this file from scratch; watch at 1.5x with the code open

## Implementation Steps
1. **Watch/code session 1** (0:00–1:30): DataLoader, tokenization with tiktoken, forward pass skeleton
2. **Watch/code session 2** (1:30–2:45): CausalSelfAttention from scratch, Flash Attention upgrade, GPT class assembly
3. **Watch/code session 3** (2:45–3:30): Training loop, gradient clipping, cosine LR schedule, gradient accumulation
4. **Watch/code session 4** (3:30–4:00): Multi-GPU DDP, actual GPT-2 reproduction results comparison
5. After completing: compare your `train_gpt2.py` line-by-line with `nanoGPT/model.py` — spot the simplifications Karpathy made for nanoGPT

## Key Concepts
- **`torch.compile`**: dramatic speedup (~2x on A100, meaningful on RTX 5070 Ti) — always use in Phase 3 training
- **`bfloat16` vs `float16`**: Karpathy explains WHY bfloat16 is preferred for training stability — use bfloat16 on RTX 5070 Ti
- **Hellaswag eval**: the in-training evaluation Karpathy uses to verify reproduction — wire this up for VECTOR Phase 3 LLM training
- **DataLoader workers**: how to set up async data loading to keep GPU saturated during training

## VECTOR Application
This is the 2AM Karpathy session repo. The lecture format makes it better for learning; nanoGPT is better for reference after the concepts are clear. The `torch.compile` and `bfloat16` tricks from this lecture are non-negotiable for VECTOR Phase 3 training efficiency on the RTX 5070 Ti. Block out a single 4-hour session to watch + code simultaneously — don't split it across days.
