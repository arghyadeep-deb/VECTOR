# last30days-skill-main - VECTOR Absorption Review

**Verdict:** VET / CLEAN-ROOM ONLY. Do not blindly install or execute this as a live skill. Use it as input for a quarantined social-intelligence research mode after SkillSpector exists.

**Priority:** MEDIUM-HIGH for research capability, HIGH for security review before use

**Effort:** 1-2 sessions for a narrow clean-room implementation

**License:** MIT

**Repo size inspected:** About 127 files / 3.8 MB.

## What It Is

`last30days` is an agent skill and search workflow for recent internet intelligence. It collects and ranks signals from sources such as Reddit, X/Twitter, YouTube transcripts, TikTok, Instagram, Hacker News, Polymarket, GitHub, Bluesky, web search, and other social/news surfaces.

It includes:

- a large `skills/last30days/SKILL.md` instruction payload
- Python source connectors
- a vendored `bird-search` component
- MCP/server pieces
- shareable HTML brief generation
- source fanout and social-signal scoring ideas
- recent-person/company/product comparison workflows

## VECTOR Overlap

VECTOR already has:

- research engine/library direction
- scraper components
- public API notes for Reddit/GitHub/Hacker News and others
- YouTube/content analysis plans
- provider client infrastructure
- SkillSpector planned as the safety gate for external skills

So this should not become a second research engine. It should inform one focused VECTOR mode.

## Real Value For VECTOR

Useful clean-room ideas:

- "last 30 days" recency-first research mode
- source health and degraded-source reporting
- social-signal ranking by upvotes, comments, money, citations, velocity, and freshness
- HTML brief artifact output
- GitHub person/project mode
- competitor comparison discovery
- source clustering and duplicate merging

## Security Risks

The repo is an agent skill, not just a library. Its `SKILL.md` contains operational instructions and tool expectations such as shell/web/write access. That makes it prompt/runtime material and must be treated as untrusted.

Risks to gate:

- prompt injection through skill instructions or fetched web content
- arbitrary shell/tool expansion if installed directly
- accidental access to `.env` or local secrets
- browser/session/cookie assumptions
- external paid APIs and scraping terms
- vendored or embedded connector behavior

## Recommendation For Sonnet

Do not install this skill directly into VECTOR.

Implement a VECTOR-native, narrow research mode:

1. Wait until SkillSpector can scan external skills/repos.
2. Define a `last_30_days` research workflow inside VECTOR's existing research stack.
3. Use VECTOR's public API registry and existing provider client.
4. Store citations, source timestamps, content hashes, and `as_of` metadata.
5. Produce a safe HTML/Markdown brief artifact.
6. Keep all credentials in VECTOR's normal secret handling path.

## Acceptance Criteria

- No external skill prompt is injected unscanned.
- No direct read access to `.env`.
- Every external source result has source URL, fetch time, and confidence/degraded status.
- Missing API keys degrade gracefully.
- Workflow can run with only public/free sources enabled.

