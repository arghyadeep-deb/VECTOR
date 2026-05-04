---
name: karpathy-makemore
description: Step-by-step implementation guide for karpathy/makemore — use during 2AM Karpathy sessions to progress from bigrams to transformers through character-level language models
---

# makemore — Implementation Guide

## Purpose
Build a character-level language model from scratch, progressing through 6 progressively more capable architectures: bigram → MLP → RNN → GRU → WaveNet → Transformer. makemore teaches the "why" of each architectural improvement, not just the "what". Prerequisite: micrograd.

## Key Files to Study (in order)
1. `makemore.py` — monolithic single-file, each part adds one architectural layer
2. The 6 Jupyter notebooks in the YouTube series (each maps to an architecture)
3. `names.txt` — the training dataset: 32,033 English names, one per line

## Implementation Steps (architecture progression)
### Part 1 — Bigram (counting)
1. Build bigram count matrix: `N[i,j]` = count of character j following character i
2. Convert to probability matrix P via row normalization
3. Sample names by drawing from P at each step

### Part 2 — MLP (Bengio 2003)
1. Embed each character into a learned `C` lookup table (embedding dim = 2 initially)
2. Concat embeddings of context window (3 chars) → hidden layer (tanh) → output logits
3. Train with cross-entropy, SGD, check train/val loss

### Part 3–4 — RNN and GRU
1. Add hidden state `h_t = tanh(W_xh @ x_t + W_hh @ h_{t-1} + b_h)`
2. Understand vanishing gradient problem through experimentation
3. GRU: add reset and update gates — study how they gate gradient flow

### Part 5 — WaveNet dilated convolutions
1. Understand dilated causal convolutions as a way to increase receptive field
2. Build the tree-structured MLP that merges character pairs hierarchically

### Part 6 — Transformer (makemore)
1. Implement self-attention on characters — connects directly to nanoGPT
2. At this point the architecture is identical to nanoGPT, just at character level

## Key Concepts
- **Embedding table C**: the most important concept — characters become learnable vectors
- **Batch normalization**: Part 3 introduces batchnorm — study the train/eval mode distinction carefully
- **Learning rate sweep**: makemore teaches empirical LR finding via loss-vs-LR plots — apply to all VECTOR training

## VECTOR Application
makemore is the conceptual bridge between micrograd and nanoGPT. After makemore Part 6, nanoGPT's architecture has no surprises. The embedding table pattern directly maps to how VECTOR's custom LLM will handle domain-specific tokens. Study Parts 1-3 in one session, Parts 4-6 in a second session.
