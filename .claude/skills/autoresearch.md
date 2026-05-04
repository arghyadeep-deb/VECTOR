---
name: autoresearch
description: Step-by-step implementation guide for karpathy/autoresearch — use when building District 8 Research or studying the self-improving agent loop during 2AM Karpathy sessions
---

# autoresearch — Implementation Guide

## Purpose
Understand how Karpathy's agent autonomously modifies `train.py`, runs fixed-budget experiments (5 min each), evaluates via validation bits-per-byte, and keeps or discards changes — running ~100 experiments unattended overnight. This is the exact loop VECTOR District 8 Research adopts for nightly automated research runs.

## Key Files to Study (in order)
1. `train.py` — the model being iteratively improved (study the eval metric: bits-per-byte)
2. `agent.py` or main script — the modification + eval + keep/discard loop
3. `README.md` — fixed-budget experiment design rationale

## Implementation Steps
1. Clone and read the agent loop from start to finish — identify: propose change → run experiment → evaluate → keep or discard
2. Reproduce the fixed-budget mechanism: each experiment gets exactly N minutes, no exceptions
3. Reproduce the evaluation gate: improvement must beat baseline metric or change is reverted
4. Adapt for VECTOR District 8: swap `train.py` modifications for research query refinements / source expansions
5. Wire to District 7 Memory: successful research strategies get persisted to LightRAG, not just discarded after the run
6. Add to nightly schedule: District 8 runs autoresearch loop from 2:30AM–5:30AM (peak creative zone)

## Key Concepts
- **Fixed budget**: each experiment gets a hard time cap — prevents any single run from dominating the session
- **Self-evaluation**: the agent compares its output to a baseline metric before keeping changes
- **Single file**: the elegance is that train.py is the only thing modified — keep District 8's research loop equally minimal
- **100 experiments/session**: scale comes from parallelism and fixed budgets, not from smarter individual runs

## VECTOR Application
District 8 Research uses this loop pattern for: (1) nightly deep-dives where an agent refines a research question across 50+ source queries, and (2) Phase 3 — the agent will use this exact pattern to iteratively improve VECTOR's custom LLM training script. The key adaptation: instead of modifying train.py, VECTOR's agent modifies its own query strategies and evaluates via information gain from LightRAG retrieval quality. Study autoresearch to understand the minimal agent loop — resist the urge to add complexity.
