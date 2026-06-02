# agency-agents-main Audit

**Repo:** agency-agents — Claude Code agent role library (MIT)
**Audited:** 2026-06-02
**Verified:** VECTOR marketing: 13 agents, design: 3 agents

---

## 1. Repo Reality

A Claude Code agent role library with categories:
- `academic/` — research, literature review, citation
- `design/` — UI designer, UX researcher, image prompt engineer
- `engineering/` — code reviewer, architect, security, DevOps, testing
- `finance/` — financial analyst, FP&A
- `marketing/` — SEO, growth hacker, social media, content creator, AI citation strategist
- `integrations/` — Slack, GitHub, Linear, Jira
- `game-development/` — game designer, narrative, etc.

---

## 2. VECTOR Parity

| Category | VECTOR equivalent | Status |
|---------|------------------|--------|
| engineering agents | `districts/coding/` (5 agents) + brain agents | ✅ Most covered |
| marketing agents | `districts/marketing/` (13 agents) | ✅ |
| design agents | `districts/design/` (3 agents: ui_designer, ux_researcher, image_prompt_engineer) | ✅ |
| finance agents | `districts/finance/` (financial_analyst, fpa_analyst) | ✅ |
| academic/research | `districts/research/` (6 agents) | ✅ |
| integration agents (Slack/GitHub) | vectorcode channels + coding district | ✅ |
| game-development | ❌ No game dev agents in VECTOR | ❌ |

---

## 3. Frontend: N/A (SKILL.md files)

---

## 4. Verdict

**SAFE TO DELETE** — Core categories (engineering, marketing, design, finance, research) absorbed in 2026-05-17 session. 3 small remaining gaps:
1. Game-development agents — not needed for VECTOR's scope
2. Some integration agents (.md files) not in brain — low priority
3. Academic citation/literature review agents — could supplement research district

**Delete-readiness:** ✅ DELETE-NOW (optional: copy 2-3 missing .md agent files to brain first)

---

## 5. Gaps

| ID | Issue | File:line | Severity |
|----|-------|-----------|----------|
| G1 | `academic/` citation + literature-review agents not in brain | `brain/.claude/agents/` | LOW |
| G2 | Integration agents (Slack/GitHub event-driven) missing | `brain/.claude/agents/` | LOW |
