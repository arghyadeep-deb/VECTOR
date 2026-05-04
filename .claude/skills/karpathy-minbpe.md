---
name: karpathy-minbpe
description: Step-by-step implementation guide for karpathy/minbpe — use when building VECTOR's custom tokenizer for the Phase 3 domain-specific LLM, or studying BPE during 2AM sessions
---

# minbpe — Implementation Guide

## Purpose
Implement Byte Pair Encoding (BPE) tokenization from scratch in ~200 lines. The same algorithm used in GPT-2/GPT-4 tokenizers. VECTOR Phase 3 uses minbpe as the base to train a custom tokenizer on VECTOR's domain-specific corpus (code, AI research, finance terms).

## Key Files to Study (in order)
1. `minbpe/base.py` — abstract `Tokenizer` class: `train`, `encode`, `decode`
2. `minbpe/basic.py` — pure Python BPE, no special tokens (~100 lines): the clearest implementation
3. `minbpe/regex.py` — the GPT-4 tokenizer: adds regex pre-tokenization (the important upgrade)
4. `minbpe/gpt4.py` — loads the actual GPT-4 cl100k_base tokenizer via `tiktoken`
5. `train.py` — trains a new BPE tokenizer on input text

## Implementation Steps
### Part 1 — basic BPE
1. Implement `get_stats(ids)`: count all consecutive byte pairs in a list of integers
2. Implement `merge(ids, pair, idx)`: replace every occurrence of `pair` in `ids` with new token `idx`
3. Implement `BasicTokenizer.train(text, vocab_size)`: iteratively find top pair, merge, repeat until `vocab_size`
4. Implement `BasicTokenizer.encode(text)`: apply all learned merges in the same order as training
5. Implement `BasicTokenizer.decode(ids)`: map ids back to bytes → decode as UTF-8

### Part 2 — regex pre-tokenization (GPT-4 style)
1. Apply GPT-4's regex pattern to split text before BPE — prevents merging across word boundaries
2. Run BPE independently on each chunk
3. This is why GPT-4 tokenizes "hello world" as ["hello", " world"] not ["hello world"]

### Part 3 — custom VECTOR tokenizer
1. Gather corpus: VECTOR codebase + LightRAG exports + research papers
2. `python train.py --input corpus.txt --vocab-size 8192 --output vector-tokenizer`
3. Test: check that domain-specific tokens ("VECTOR", "District", "HP", Python keywords) get dedicated token ids

## Key Concepts
- **Bytes not characters**: BPE works on raw UTF-8 bytes — handles any language/emoji without special casing
- **Merge order = tokenizer**: the merge table IS the tokenizer; different training corpora → different vocabularies
- **`vocab_size` tradeoff**: larger vocab = longer tokens = shorter sequences = faster inference, but more embedding parameters
- **Special tokens**: `<|endoftext|>`, `<|im_start|>` etc. are appended AFTER BPE training — they don't participate in merges

## VECTOR Application
Phase 3: train a VECTOR-specific tokenizer on a domain corpus to reduce sequence lengths for VECTOR's knowledge and code. Target vocab size: 16K-32K (smaller than GPT-4's 100K — VECTOR's domain is narrower). The custom tokenizer plugs directly into nanoGPT's `DataLoader` by swapping tiktoken for minbpe. Study basic.py first (1 session), then regex.py (1 session), then train the custom tokenizer.
