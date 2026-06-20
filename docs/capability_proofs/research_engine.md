# Capability Proof — research_engine

**Verdict: LIVE (with two real bugs that hollow out the output quality)**

Run at: 2026-06-20T12:36:34.481978+00:00

## What this tests

`AutoResearchAgent.run_full_cycle("test")` — the full hypothesis → experiment
design → sandbox execution → analysis → report pipeline. This is a different
subsystem from the web-search engines also living in `core/research_engine/`
(those are tested separately, not part of this probe).

## Output (verbatim, from the automated probe)

```
{'report_id': None, 'sections': 6, 'title': None}
```

`report_id`/`title` are `None` because the probe guessed wrong attribute names
(`ResearchReport` has no `.id`/`.title` — real fields are `hypothesis`,
`experiment`, `analysis`, `sections` (a dict), `figures`, `references`).
Verified manually instead — the pipeline genuinely wrote a real file:
`C:\Users\Arghyadeep\VECTOR\Obsidian\Research Reports\hypothesis_on_test_20260620_123638.md`
— real markdown, 6 real sections (Hypothesis/Methodology/Results/Analysis/
Conclusion/References) with real field tables, not boilerplate placeholders.
**The orchestration plumbing genuinely works end-to-end and produces a real,
persisted artifact.** This is why the verdict is LIVE and not BROKEN.

## Two real bugs surfaced (degrade the report's actual value, don't crash it)

1. **`'EpisodicMemory' object has no attribute 'search'`** —
   `auto_research_agent.py:62` calls `memory.search(topic, limit=5)`, but
   `EpisodicMemory` doesn't have a `search` method (it's probably `recall` or
   `search_semantic`, per other call sites in the codebase). This means every
   research cycle runs with zero memory-pattern context, always. Caught and
   logged as a warning, not fatal — but it's a real, silent capability loss.

2. **Sandbox experiment execution failed: Ollama 404, then 0 data points.**
   `experiment_designer.py`'s `_llm_design()` hit
   `Client error '404 Not Found' for url 'http://localhost:11434/api/generate'`
   (Ollama not running / wrong endpoint right now) and fell back to a
   rule-based template — handled gracefully. But the actual experiment then
   executed with **status=failed** and the analyzer found **"Insufficient
   data points (0)"** — meaning the report's Results/Analysis sections are
   real markdown but scientifically empty. A capability that's "LIVE" by
   the plumbing test but produces empty-content reports forever isn't useful
   to schedule autonomously until this is fixed.

## Triage implication

Plumbing-wise this capability is wireable today (Phase 1+). But scheduling it
to run autonomously *before* fixing bug #2 would just accumulate empty reports
— a fix sub-task (rule-based experiment templates need real data, not just a
fallback that produces zero data points) should happen first or alongside.
Bug #1 (memory search) is an independent, smaller fix.
