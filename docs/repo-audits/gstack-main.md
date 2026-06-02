# gstack-main Audit

**Repo:** gstack — Claude Code browser testing skill (garrytan/gstack, MIT)
**Audited:** 2026-06-02

---

## 1. Repo Reality

gstack is a Claude Code skill collection enabling browser-based QA and visual verification inside Claude Code sessions. Commands: `/browse <url>`, `/qa`, `/ship`, `/design`, `/health`, `/investigate`. Uses Playwright + screenshots + Claude vision to verify deployed UIs. Language: SKILL.md files + TypeScript scripts.

**Skills included:** browse, qa, qa-only, ship, health, design, design-review, open-gstack-browser, investigate, land-and-deploy, landing-report, gstack, gstack-upgrade

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Verified output | Status |
|---------|------------------|-----------------|--------|
| Browser screenshot + analysis | `core/browser/dom_pruner.py` + playwright | DOMPruner OK | ⚠️ Partial (no Claude vision loop) |
| `/browse <url>` skill | ❌ Not installed in `~/.claude/skills/` | gstack not found | ❌ |
| QA pipeline | ❌ No Claude Code QA skill | N/A | ❌ |
| Health check skill | ❌ | N/A | ❌ |

---

## 3. Frontend: N/A (build-session skill, not a runtime panel)

---

## 4. Verdict

**PATCH VECTOR** — The gstack skill should be in `~/.claude/skills/` for build sessions. The repo (`gstack-main`) IS the skill source. Need to run `/gstack-upgrade` or install manually. Repo version may be ahead of whatever is installed.

**Delete-readiness:** KEEP — it IS the skill source. Don't delete; symlink into `~/.claude/skills/`.

---

## 5. Gaps

| ID | Issue | File:line | Severity |
|----|-------|-----------|----------|
| G1 | gstack skills not installed in `~/.claude/skills/` — `/browse`, `/qa`, `/health`, `/ship` unavailable | `~/.claude/skills/` | MED |
