# ai-website-cloner-template-master Audit

**Repo:** AI Website Cloner Template — Claude Code skill for reverse-engineering sites into Next.js (MIT)
**Audited:** 2026-06-02

---

## 1. Repo Reality

A Claude Code skill template (`/clone-website`) that reverse-engineers any live website into clean Next.js code via:
1. Playwright/Browser MCP → screenshot + inspect live site
2. `getComputedStyle()` sweep → extract design tokens (colors, fonts, spacing)
3. Component spec files → `docs/research/components/`
4. Parallel git-worktree builder agents — one per section
5. Assembly + visual diff QA

Language: SKILL.md + Next.js scaffold. No Python.

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Status |
|---------|------------------|--------|
| Website screenshot | `core/browser/dom_pruner.py` + Playwright | ⚠️ Partial (no design token extraction) |
| Design token extraction (CSS vars) | ❌ No `getComputedStyle()` sweep | ❌ |
| Component spec generation | ❌ No component reverse-engineering | ❌ |
| `/clone-website` skill | ❌ Not installed | ❌ |

---

## 3. Frontend: N/A (generates frontends, is not one)

---

## 4. Verdict

**INTEGRATE DIRECTLY** — Install the `/clone-website` skill into `~/.claude/skills/`. Requires Browser MCP active in session (playwright-mcp sidecar). No Python code needed — pure SKILL.md.

**Delete-readiness:** DELETE-AFTER installing skill.

---

## 5. Gaps

| ID | Issue | File:line | Severity |
|----|-------|-----------|----------|
| G1 | `/clone-website` skill not installed in `~/.claude/skills/` | `~/.claude/skills/clone-website/` | MED |
| G2 | `dom_pruner.py` has no `extract_design_tokens(url)` function | `core/browser/dom_pruner.py` | LOW |
