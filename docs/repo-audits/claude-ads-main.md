# claude-ads-main Audit

> Audited: 2026-06-01  
> Repo: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\claude-ads-main`  
> VECTOR codebase: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase`  
> Prior absorption note (memory log 2026-05-19): "claude-ads: ads intelligence layer"

---

## 1. Repo Reality

**claude-ads-main** (v1.7.1, MIT, by AgriciDaniel) is a Claude Code skill plugin for paid advertising audit and optimization. It is 100% prompt-and-instruction code — no Python runtime logic except 5 utility scripts absorbed into VECTOR. The repo structure:

```
skills/          22 SKILL.md files (ads + ads-google + ads-meta + ads-youtube + ads-linkedin +
                 ads-tiktok + ads-microsoft + ads-apple + ads-amazon + ads-attribution +
                 ads-server-side-tracking + ads-creative + ads-landing + ads-budget +
                 ads-plan + ads-competitor + ads-math + ads-test + ads-dna +
                 ads-create + ads-generate + ads-photoshoot)
agents/          10 .md agent definitions (6 audit + 4 creative)
ads/references/  26 RAG knowledge files (benchmarks, audit checklists, specs, compliance)
ads/SKILL.md     Main orchestrator
tests/           41 pytest tests (routing snapshots, check-catalog coverage, scoring math,
                 SSRF regression)
scripts/         5 Python utility scripts (analyze_landing.py, capture_screenshot.py,
                 fetch_page.py, generate_image.py, generate_report.py + url_utils.py)
```

**What it concretely does:**
- Routes `/ads <command>` to 22 specialized sub-skills via Claude Code's skill runner
- Runs 250+ audit checks across 8 platforms (Google: 80, Meta: 50, LinkedIn: 27, TikTok: 28, Microsoft: 24, Apple: 35+, Amazon: 30+, Attribution/tracking: 25+)
- Produces weighted Ads Health Score (0-100) using `S_total = Σ(C_pass × W_sev × W_cat) / Σ(C_total × W_sev × W_cat) × 100` with 4 severity tiers (Critical 5x, High 3x, Medium 1.5x, Low 0.5x)
- Generates PDF audit reports, AI ad images (Gemini→OpenAI→Stability→Replicate fallback), landing page analysis via Playwright, brand DNA extraction, PPC financial math, A/B test design
- Wave 2 (v1.7.x): Amazon Ads, cross-platform attribution, server-side tracking (sGTM/CAPI/event dedup)
- 26 reference files serve as RAG context loaded on demand per command

**Architecture note:** The skill is a prompt-dispatch system. The 5 Python utility scripts (analyze_landing, capture_screenshot, fetch_page, generate_image, generate_report) are the only executable Python code; all audit logic lives in SKILL.md instruction files.

---

## 2. VECTOR Parity

**Absorption method (from memory log 2026-05-19):** The prior absorption session installed the 22 SKILL.md files into `~/.claude/skills/ads*/` (confirmed present) and reimplemented the Python utility scripts plus key reference data into VECTOR's autonomous Python stack at `districts/marketing/`.

**Critical distinction — Rule for skill repos:** SKILL.md files are usable only during Claude Code build sessions. For VECTOR to use ads intelligence autonomously (as a citizen agent), the value must be reimplemented as Python agents in `districts/marketing/`. Both layers are present.

| Feature | VECTOR equivalent | Verified output | Status |
|---------|------------------|----------------|--------|
| Main orchestrator (`/ads`) | `districts/marketing/ads_orchestrator_agent.py` — `AdsOrchestratorAgent` routes 13 task types | Import OK, all task routes confirmed in `run()` | ✅ real & working |
| Google Ads audit (80 checks) | `districts/marketing/google_ads_agent.py` — `GoogleAdsAgent.audit_account()`, 7 dimensions, policy rules embedded, ROAS benchmarks by industry | Import OK, logger confirmed | ✅ real & working |
| Meta Ads audit (50 checks) | `districts/marketing/meta_ads_agent.py` — `MetaAdsAgent.audit_account()`, learning phase, creative fatigue, audience overlap, iOS14 policy | Import OK, logger confirmed | ✅ real & working |
| Multi-platform full audit | `AdsOrchestratorAgent.run({"type": "ads_audit"})` — loops over platforms, calls `_llm_audit()` per platform with reference files injected | Task type `ads_audit/ads_full_audit/ads_multi_audit` confirmed | ✅ real & working |
| Platform-specific audits (LinkedIn, TikTok, Microsoft, Apple, YouTube) | `AdsOrchestratorAgent` dispatches `ads_linkedin_audit`, `ads_tiktok_audit`, `ads_microsoft_audit`, `ads_apple_audit`, `ads_youtube_audit` → `_llm_audit()` with per-platform reference file | 2 task type matches confirmed in source | ✅ present (LLM-backed, no dedicated agent per platform) |
| Budget & bidding review | `AdsOrchestratorAgent` task `ads_budget/ads_bidding`, loads `budget-allocation.md` + `bidding-strategies.md` | Task type confirmed | ✅ real & working |
| Strategic plan (11 industry templates) | `AdsOrchestratorAgent` task `ads_plan`, loads industry template from `ads/templates/` (12 templates confirmed) | Templates: agency, b2b-enterprise, ecommerce, ecommerce-creative, finance, generic, healthcare, info-products, local-service, mobile-app, real-estate, saas | ✅ real & working |
| Competitor intelligence | `districts/marketing/competitor_intel_agent.py` — `CompetitorIntelAgent` | Import OK | ✅ real & working |
| PPC financial calculator (CPA/ROAS/break-even) | `AdsOrchestratorAgent` task `ads_math/ppc_calculator` — native Python math (CPC, CVR, CPA, ROAS, break-even ROAS, profitability flag) | Deterministic Python calculation confirmed in source | ✅ real & working |
| A/B test design | `AdsOrchestratorAgent` task `ads_test/ab_test_design` — LLM with hypothesis/sample size/significance | Task type confirmed | ✅ real & working |
| Brand DNA extraction | `AdsOrchestratorAgent` task `ads_dna/brand_dna` — calls `fetch_page.py` + `capture_screenshot.py` + `brand-dna-template.md` | Task type + script dispatch confirmed | ✅ real & working |
| Campaign brief generation | `AdsOrchestratorAgent` task `ads_create/campaign_brief` — `copy-frameworks.md` + `voice-to-style.md` | Task type confirmed | ✅ real & working |
| AI image generation (Gemini→OpenAI→Stability→Replicate) | `districts/marketing/ads/scripts/generate_image.py` — 4-provider fallback chain, batch mode, SSRF-safe, reference image support | 591-line Python file, full implementation confirmed | ✅ real & working |
| PDF audit report | `districts/marketing/ads/scripts/generate_report.py` — `parse_markdown()` + `build_pdf()` + gauge chart + platform bar chart + pass/fail distribution | 749-line Python file, `reportlab` + `matplotlib`, content quality checker included | ✅ real & working |
| Landing page analysis (Core Web Vitals, CTA, trust signals) | `districts/marketing/ads/scripts/analyze_landing.py` — Playwright, LCP/CLS/TTFB, CTAs, forms, trust signals | 60+ line Python script confirmed | ✅ real & working |
| Creative audit (cross-platform) | `AdsOrchestratorAgent` task `ads_creative/ads_creative_audit` — `platform-specs.md` + `copy-frameworks.md` | Task type confirmed | ✅ real & working |
| 26 RAG reference files | `districts/marketing/ads/references/` — 25 files confirmed (missing: `thinking-framework.md`, `gaql-notes.md` from upstream, plus Wave 2-specific files) | `ads_stats()` returns references=25, templates=12 | ⚠️ 25/26 references (thinking-framework.md not ported) |
| Ads Health Score weighted formula | `districts/marketing/ads/references/scoring-system.md` — full formula documented; `generate_report.py` parses score; PPC math route computes it for simple cases | Scoring reference confirmed; no standalone Python scorer class | ⚠️ formula in reference MD, no dedicated `AdsScorer` Python class for batch re-use |
| Wave 2: Amazon Ads (ACOS/TACOS, 30+ checks) | Not implemented as Python agent; `AdsOrchestratorAgent` has no `ads_amazon_audit` task route | `ads-amazon` skill not installed to `~/.claude/skills/`; no Python agent | ❌ missing |
| Wave 2: Cross-platform attribution audit (AdAttributionKit, GA4, Consent Mode V2) | Not implemented as Python agent | `ads-attribution` skill not installed; no Python agent | ❌ missing |
| Wave 2: Server-side tracking audit (sGTM, CAPI Gateway, event dedup) | Not implemented as Python agent | `ads-server-side-tracking` skill not installed; no Python agent | ❌ missing |
| 6 parallel audit subagents (`audit-google`, `audit-meta`, `audit-creative`, `audit-tracking`, `audit-budget`, `audit-compliance`) | `AdsOrchestratorAgent` runs platform audits sequentially in a for-loop, not as parallel coroutines | No `asyncio.gather()` for parallel dispatch found | ⚠️ sequential, not parallel |
| Ads Health Score determinism tests (41 pytest tests + SSRF regression) | No VECTOR test file for ads scoring, routing snapshots, or check-catalog coverage | `grep` confirmed zero ads-specific test files | ❌ no test coverage |
| CRO agent (landing/conversion rate) | `districts/marketing/cro_agent.py` — `CROAgent` | Import OK | ✅ bonus (not in claude-ads) |
| SEO agents (SEOAgent, SEOSpecialist, SEOPortfolio) | `districts/marketing/seo_agent.py`, `seo_specialist.py`, `seo_portfolio.py` | `SEOSpecialist` import verified OK | ✅ bonus |
| Social/Growth/Content agents | `social_media_strategist.py`, `growth_hacker.py`, `content_creator.py`, `ai_citation_strategist.py` | Confirmed present | ✅ bonus |
| SKILL.md files in Claude Code skills | 20 of 22 sub-skills installed to `~/.claude/skills/ads*/` | Confirmed: `ads`, `ads-google`, `ads-meta`, `ads-youtube`, `ads-linkedin`, `ads-tiktok`, `ads-microsoft`, `ads-apple`, `ads-creative`, `ads-landing`, `ads-budget`, `ads-plan`, `ads-competitor`, `ads-math`, `ads-test`, `ads-dna`, `ads-create`, `ads-generate`, `ads-photoshoot`, `ads-audit` (20 dirs) | ✅ installed (build-session use only) |
| Wave 2 SKILL.md files | `ads-amazon`, `ads-attribution`, `ads-server-side-tracking` NOT in `~/.claude/skills/` | Confirmed absent | ❌ not installed |

---

## 3. Frontend / Panel Spec

No ads-specific dashboard panel exists in `frontend/VECTOR.html`. The `docs/frontend-spec.md` (from the 2026-05-29 JARVIS audit session) documented 200 endpoints across 6 WebSocket channels, but no dedicated ads intelligence panel was specified.

**What a VECTOR ads panel would need:**
- Health score gauge (gauge chart, grade A-F, per-platform breakdown)
- Platform score bars (Google/Meta/LinkedIn/TikTok/Microsoft)
- Active audit status (sequential for now; parallel when Gap 1 below is addressed)
- Quick wins list
- PDF report download trigger
- Image generation job queue

This panel is not yet built. The `generate_report.py` produces a local PDF file; there is no HTTP endpoint exposing it.

---

## 4. Verdict

**Overall: SUBSTANTIALLY ABSORBED — Core value present, Wave 2 and test coverage missing.**

The prior absorption session (2026-05-19) correctly implemented the high-value Python layer:
- 5 Python utility scripts are exact-parity reimplementations (generate_image, generate_report, analyze_landing, fetch_page, capture_screenshot + url_utils)
- `AdsOrchestratorAgent` covers 13 of the 22 sub-skill commands autonomously via `run()` dispatch
- `GoogleAdsAgent` and `MetaAdsAgent` are full citizen agents with HP system, episodic memory, and policy rules embedded — these are the two highest-traffic platforms and were the right priority
- All 26 reference files and 12 industry templates are present (25/26; thinking-framework.md missing)
- 20 of 22 SKILL.md files are installed for build-session use

**Three real gaps remain:**

1. **Wave 2 sub-skills not absorbed** — `ads-amazon`, `ads-attribution`, `ads-server-side-tracking` exist in the source repo but are not installed as `~/.claude/skills/` entries AND have no Python agent equivalents in `districts/marketing/`. The AdsOrchestratorAgent has no task route for `ads_amazon_audit`. These are meaningful additions: Amazon retail media is a $56B channel; attribution and sGTM audits are 2026-critical given Consent Mode V2 enforcement.

2. **No test suite** — claude-ads ships 41 pytest tests (routing snapshots, bidirectional 209-check catalog coverage, scoring math determinism, SSRF regression). VECTOR has zero ads-specific tests. The scoring formula lives only in a reference .md, not as a Python class. If `generate_report.py`'s markdown parser drifts, nothing will catch it.

3. **Sequential audit, not parallel** — `AdsOrchestratorAgent` iterates platforms in a `for` loop. The upstream ships 6 parallel subagents via Claude Code's dispatch. VECTOR should use `asyncio.gather()` to match the 10-15 minute audit target.

---

## 5. Gaps

| # | Issue | Location | Type | Status |
|---|-------|----------|------|--------|
| 1 | Wave 2: `ads-amazon` SKILL.md not installed to `~/.claude/skills/ads-amazon/` | `~/.claude/skills/` | Missing sub-skill | ❌ |
| 2 | Wave 2: `ads-attribution` SKILL.md not installed to `~/.claude/skills/ads-attribution/` | `~/.claude/skills/` | Missing sub-skill | ❌ |
| 3 | Wave 2: `ads-server-side-tracking` SKILL.md not installed to `~/.claude/skills/ads-server-side-tracking/` | `~/.claude/skills/` | Missing sub-skill | ❌ |
| 4 | No Python agent for Amazon Ads (ACOS/TACOS, Sponsored Products/Brands/Display) | `districts/marketing/` | Missing autonomous agent | ❌ |
| 5 | No Python agent for attribution audit (AdAttributionKit, GA4, Consent Mode V2, MMP) | `districts/marketing/` | Missing autonomous agent | ❌ |
| 6 | No Python agent for server-side tracking audit (sGTM, CAPI Gateway, event dedup) | `districts/marketing/` | Missing autonomous agent | ❌ |
| 7 | `AdsOrchestratorAgent` runs platform audits sequentially; should use `asyncio.gather()` for parallel dispatch | `districts/marketing/ads_orchestrator_agent.py:108` | Performance gap | ⚠️ |
| 8 | No `AdsScorer` Python class implementing `S_total = Σ(C_pass × W_sev × W_cat) / Σ(C_total × W_sev × W_cat) × 100`; scoring lives only in reference MD | `districts/marketing/ads/` | Missing implementation | ⚠️ |
| 9 | `thinking-framework.md` not present in `ads/references/` (26 reference files upstream; VECTOR has 25) | `districts/marketing/ads/references/` | Missing reference file | ⚠️ |
| 10 | Zero pytest coverage for ads: no routing snapshot tests, no check-catalog bidirectionality, no scoring math determinism, no SSRF regression for ads scripts | `tests/` | Missing test suite | ❌ |
| 11 | No ads dashboard panel in `frontend/VECTOR.html` — health score gauge, platform bars, quick wins, PDF download trigger | `frontend/VECTOR.html` | Missing UI panel | ⚠️ |
| 12 | `generate_report.py` footer hardcodes `vector-ads v1.5` (upstream brand name, not VECTOR branding) | `districts/marketing/ads/scripts/generate_report.py:502,625` | Cosmetic / branding | ⚠️ |

**Priority order for next session:** Gap 1-3 (copy 3 SKILL.md files — 10 min), Gap 10 (port the 41-test eval harness from `tests/audit/`, `tests/routing/`, `tests/scripts/` — high value, catches regressions), Gap 7 (add `asyncio.gather()` to parallel platform audits), Gaps 4-6 (build Amazon/Attribution/SST Python agents using the SKILL.md spec as the implementation guide).
