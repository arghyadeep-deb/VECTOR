# competitor-x-ray-main - VECTOR Absorption Review

**Verdict:** VET / CLEAN-ROOM competitor-intelligence workflow only. Do not directly install the skill.

**Priority:** MEDIUM-HIGH for agency/startup/content research

**Effort:** 1 session for a VECTOR-native competitor brief workflow

**License:** MIT

**Repo size inspected:** About 12 files.

## What It Is

Competitor X-Ray is a Claude skill for competitor research. It normalizes competitor targets, researches each one, separates audience from buyer, maps funnels, identifies monetization streams, ranks threats, and can output chat, spreadsheet, Word, or designed PDF reports.

The skill emphasizes:

- ICP vs audience distinction
- funnel stages from top to bottom
- monetization and price-point discovery
- evidence tiers: confirmed, reported, inferred
- source links and confidence notes
- per-competitor parallel research
- designed intelligence-brief output

## VECTOR Overlap

VECTOR already has:

- startup/agency competitor research surfaces
- content strategy and YouTube competitor analysis
- research engine and citation discipline
- document/report generation direction
- SkillSpector planned for external skill vetting

This should become a workflow/template inside VECTOR research, not a foreign skill.

## Security Note

The skill file includes large prompt instructions and hidden/zero-width provenance-like text near the end. Even if benign, this is exactly the kind of external skill content SkillSpector should inspect before activation.

## Real Value For VECTOR

Useful clean-room ideas:

- competitor target normalization
- evidence-tier labels on every claim
- ICP / funnel / monetization brief schema
- threat ranking by maturity and momentum
- links directory separate from evidence sources
- designed PDF or spreadsheet output for client-ready briefs

## Risks

- direct SKILL.md import expands prompt-injection surface
- social platforms and analytics sources may be gated or unreliable
- designed PDF workflow may introduce unrelated rendering dependencies
- follower/revenue estimates can become hallucinated unless evidence tiers are enforced

## Recommendation For Sonnet

Do not install the skill directly.

Implement a VECTOR-native `competitor_xray` research mode:

1. Reuse existing research/search/citation paths.
2. Add a strict output schema: target, ICP, funnel, monetization, metrics, sources, confidence.
3. Require evidence tier on every claim.
4. Use SkillSpector before importing any skill text or references.
5. Store results in research library and optionally export Markdown/CSV/PDF.

## Acceptance Criteria

- No unscanned external skill prompt is injected into VECTOR.
- Every competitor claim has source and evidence tier.
- Missing/gated data is reported as missing, not guessed.
- PDF/spreadsheet export is optional.
- Workflow degrades gracefully without paid analytics sources.

