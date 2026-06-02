# gsap-skills-main Audit

## 1. Repo Reality

**Source:** `greensock/gsap-skills` (official GreenSock repo, MIT license)
**Purpose:** Official Claude Code / Cursor / Copilot skills for the GSAP JavaScript animation library. Teaches AI agents correct GSAP API usage across 8 skill modules.
**Language:** Pure Markdown SKILL.md files — zero Python, zero backend logic.
**Size:** 8 skill folders + `llms.txt` index inside `skills/`.

| Skill | Domain |
|-------|--------|
| gsap-core | `gsap.to()`, `from()`, `fromTo()`, easing, stagger |
| gsap-timeline | Sequencing, position parameter, labels, nesting |
| gsap-scrolltrigger | Scroll-linked animation, pinning, scrub |
| gsap-plugins | Flip, Draggable, SplitText, MorphSVG, 20+ plugins |
| gsap-utils | `gsap.utils`: clamp, mapRange, normalize, snap |
| gsap-react | `useGSAP` hook, refs, `gsap.context()`, SSR |
| gsap-performance | transform-over-layout, will-change, batching |
| gsap-frameworks | Vue, Svelte, lifecycle cleanup |

**License risk:** MIT — zero restriction.
**Security surface:** LOW (animation library, no network, no data handling).

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Verified output | Status |
|---------|-------------------|-----------------|--------|
| GSAP animation knowledge | None — VECTOR has no JS animation layer | `grep -r "gsap" frontend/` → empty | NOT PRESENT |
| Frontend JS (any) | `frontend/js/` has 14 files (cinematic, orb, city3d, widgets, etc.) | `ls frontend/js/` → 14 files confirmed | VECTOR uses vanilla JS / Three.js style — no GSAP |
| Dashboard / Next.js UI | `dashboard/` does not exist | `ls dashboard/` → not found | Unbuilt — dashboard is a Phase 3 gap |
| Animation context | `frontend/VECTOR.html` — no GSAP import | Confirmed: no CDN link, no npm dep | GSAP not installed anywhere |
| Claude Code skill location | `~/.claude/skills/` — no gsap* folder | `ls ~/.claude/skills/ \| grep gsap` → empty | Not installed globally |
| brain skills | `brain/.claude/skills/` — path does not exist | Checked: directory absent | Not installed in brain |

---

## 3. Frontend

VECTOR's current frontend (`frontend/VECTOR.html` + `frontend/js/`) is a standalone vanilla JS + Three.js-style HTML page. No bundler, no React, no npm — so GSAP would need to be loaded via CDN (`https://cdn.gsap.com/public/gsap@3/dist/gsap.min.js`).

The GSAP skills are specifically designed for agents writing JavaScript animation code. VECTOR has no active JS animation work in progress; the planned Next.js dashboard does not exist yet.

**If/when the Next.js dashboard or a frontend animation task is scoped**, these skills would be directly useful for:
- Scroll-driven onboarding animations (`gsap-scrolltrigger`)
- HP bar animations for the Agent City UI (`gsap-core` + `gsap-timeline`)
- Page transition effects (`gsap-frameworks` for React/Next.js)

---

## 4. Verdict

**DELETE-NOW**

Reasons:
1. VECTOR is a Python backend system. Zero GSAP usage exists anywhere in the codebase.
2. No npm/React/Next.js frontend exists — the dashboard is unbuilt.
3. These skills only activate when an AI agent writes JavaScript animation code. That use case is not on the current roadmap (Phase 3 gaps are all Python/cloud).
4. The skills are not installed in `~/.claude/skills/` or `brain/.claude/skills/` — they have never been wired in.
5. When the Next.js dashboard is eventually built, re-adding via `npx skills add https://github.com/greensock/gsap-skills` takes 30 seconds.

**Risk of deletion:** ZERO. MIT licensed, re-downloadable instantly.

---

## 5. Gaps

No gaps to absorb. These are AI coding-guidance skills for JavaScript animation — not Python utilities, not APIs, not architectural patterns. The correct action is deletion of the local repo clone; re-clone when a frontend animation sprint is actually scheduled.

**One-line re-install (future):**
```bash
npx skills add https://github.com/greensock/gsap-skills
```
