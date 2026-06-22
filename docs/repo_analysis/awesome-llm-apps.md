# awesome-llm-apps-main - VECTOR Absorption Review

**Verdict:** REFERENCE ONLY. Mine selected patterns, do not bulk absorb templates or skills.

**Priority:** LOW-MEDIUM, with occasional HIGH-value examples

**Effort:** 0.5-1 session per selected template/pattern

**License:** Apache-2.0

**Repo size inspected:** About 1653 files, excluding git/build/cache directories.

## What It Is

Awesome LLM Apps is a large cookbook of runnable AI agent and RAG templates. It includes examples for:

- starter agents
- advanced/multi-agent apps
- always-on agents
- MCP agents
- RAG tutorials
- voice agents
- generative UI agents
- agent skills
- fine-tuning/tutorial material

Most examples are standalone templates rather than a shared production library.

## VECTOR Overlap

VECTOR already has many of these categories:

- always-on scheduler and agents
- research engine
- voice stack
- MCP/tool surfaces
- investment/content/startup districts
- memory and RAG-like retrieval
- skill ingestion plans

This repo is useful as a benchmark/cookbook, not as code to import.

## Real Value For VECTOR

Useful things to inspect selectively:

- always-on Hacker News briefing pattern
- trust-gated multi-agent research pattern
- competitor intelligence example
- generative UI/dashboard patterns
- self-improving skill examples
- voice-agent examples for workflow comparison

## Risks

- many standalone apps with inconsistent dependencies and quality
- multiple API-key examples can encourage secret sprawl
- broad template copying creates redundancy
- some examples may be tutorial-grade rather than production-grade
- skill prompts should still be scanned before use

## Recommendation For Sonnet

Do not absorb the repo.

Create a short "pattern shortlist" only when a specific VECTOR gap is being implemented:

1. Pick one template relevant to the active feature.
2. Read its README and minimal source.
3. Extract only the workflow idea.
4. Reimplement in VECTOR's existing district/provider/memory style.
5. Add tests against VECTOR behavior, not template behavior.

## Acceptance Criteria

- No bulk copying of examples.
- No new framework introduced only because a template uses it.
- Any imported skill prompt is SkillSpector-scanned first.
- API keys remain centralized in VECTOR config/secret handling.
- The chosen pattern maps to an open issue or active implementation task.

