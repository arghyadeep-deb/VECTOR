<!-- VECTOR-INGESTED ASSET
  Source: .claude/skills/llm-council.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:55+00:00
-->

---
name: llm-council
description: Step-by-step implementation guide for karpathy/llm-council — use when building or studying the LLM Council during 2AM Karpathy sessions, especially for District 2 design
---

# llm-council — Implementation Guide

## Purpose
Understand how Karpathy routes a query to multiple LLMs, runs anonymous peer review, and synthesises a final answer via a Chairman model. This is the exact pattern VECTOR District 2 runs with HP-gated voting across kimi-k2.6, glm-5.1, and local models.

## Key Files to Study (in order)
1. `council.py` — the full pipeline: independent → peer review → synthesis
2. `llm.py` — how OpenRouter multi-model calls are structured
3. `prompts.py` — peer review prompt engineering (study for District 2 council prompts)
4. `README.md` — three-stage pipeline diagram

## Implementation Steps
1. Clone and read `council.py` top-to-bottom — map each stage to a VECTOR district action
2. Reproduce Stage 1: send the same query to 3 models via OpenRouter, collect responses
3. Reproduce Stage 2: send all responses to each model anonymously for ranking (the HP mechanic maps here)
4. Reproduce Stage 3: synthesise with Chairman — in VECTOR this is vector-reasoning (qwen3:8b)
5. Wire the HP gate: only models above HP threshold participate in peer review
6. Replace OpenRouter calls with VECTOR's local Ollama models for runtime (cloud only for HIGH stakes, ≤10/week)

## Key Concepts
- **Chairman model**: the synthesiser — in VECTOR this is vector-reasoning. Must be the highest-HP council member
- **Anonymous peer review**: models don't know whose answer they're ranking — prevents anchoring bias
- **Three-stage pipeline**: independent → peer-review → synthesis. Don't collapse these into one call
- **HP gate**: Karpathy's original has no HP concept — you ADD this. Models below 30 HP are excluded from voting

## VECTOR Application
District 2 (LLM Council) is a direct implementation of this pattern. The main difference: VECTOR uses local Ollama models for the independent response stage and only escalates to cloud (kimi-k2.6, glm-5.1) when the confidence gap between responses exceeds a threshold. Study llm-council to understand the prompt engineering for peer review — those prompts need adaptation for HP-aware voting.
