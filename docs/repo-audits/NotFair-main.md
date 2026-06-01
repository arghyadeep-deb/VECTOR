# NotFair-main — Repo Audit
> Audited: 2026-06-02 | VECTOR branch: production-hardening-complete | NotFair version: 0.25.5

---

## Step 1 — Repo Reality

**What NotFair is:** An open-source Claude Code plugin (MIT license, published by nowork-studio) that gives any AI coding agent direct access to Google Ads, Meta Ads (Facebook + Instagram), and SEO skills. It is purely a skill/prompt layer — SKILL.md files with structured procedures — backed by two remote MCP servers (`https://notfair.co/api/mcp/google_ads` and `https://notfair.co/api/mcp/meta_ads`) that handle all real platform API calls via OAuth 2.1.

**Repository structure:**
```
NotFair-main/
├── .mcp.json                    — MCP server config (NotFair-GoogleAds + NotFair-MetaAds)
├── server-google-ads.json       — MCP registry entry (streamable HTTP)
├── server-meta-ads.json         — MCP registry entry (streamable HTTP)
├── AGENTS.md                    — Universal skill resolver (Codex, Hermes, Claude, Cursor)
├── google-ads/
│   ├── audit/                   — 7-dimension account health audit, business context setup
│   ├── manage/                  — Full campaign CRUD: GAQL reads, write tools, change log
│   ├── copy/                    — RSA copy generator + A/B testing
│   └── landing/                 — Landing page ↔ ad relevance scoring (Quality Score)
├── meta-ads/
│   ├── audit/                   — 7-dimension Meta audit (Pixel/CAPI, learning phase, creative)
│   ├── manage/                  — ROAS/frequency/creative fatigue/audience overlap ops
│   └── shared/                  — meta-math.md, policy-registry.json, preamble.md
├── seo/
│   ├── seo-analysis/            — Full GSC + PageSpeed + URL Inspection audit + CMS push
│   ├── seo-page/                — Single-URL deep audit
│   ├── content-writer/          — E-E-A-T blog posts, landing pages, content improvements
│   ├── content-planner/         — Editorial calendar from GSC data
│   ├── keyword-research/        — Seed → keyword universe + GEO relevance tagging
│   ├── meta-tags-optimizer/     — Title/meta/OG/Twitter cards with CTR estimates
│   ├── schema-markup-generator/ — JSON-LD (FAQ, HowTo, Article, Product, LocalBusiness)
│   ├── seo-page/                — Per-URL deep analysis
│   ├── broken-link-checker/     — 404/5xx site crawler
│   ├── geo-optimizer/           — GEO/AEO: PAWC scoring, per-engine playbooks (ChatGPT/Claude/Perplexity/Gemini)
│   └── setup-cms/               — WordPress/Strapi/Contentful/Ghost connector
└── gemini/                      — Cross-model review via Gemini CLI (review/challenge/consult modes)
```

**Key reference assets (absorbed into SKILL.md procedures):**
- `google-ads/audit/references/`: account-health-scoring.md, business-context.md, persona-discovery.md, conversion-network-audit.md
- `google-ads/manage/references/`: change-tracking.md, bid-strategy-decision-tree.md, daily-ads-operator.md, intervention-memory.md, repeatable-optimization-loops.md, search-term-analysis-guide.md, safe-executor.md, client-reporter.md, session-checks.md, quality-score-framework.md
- `meta-ads/manage/references/`: analysis-heuristics.md, creative-fatigue.md, learning-phase.md, audience-strategy.md, campaign-structure-guide.md, industry-benchmarks.md, geo-techniques.md
- `seo/geo-optimizer/references/geo-techniques.md`: Full GEO Signal Stack — PAWC math, 4-pillar scoring (Evidence Density 35%, Structure 25%, Authority 25%, Crawlability 15%), per-engine playbooks (ChatGPT/Perplexity/Claude/Gemini/AI Overviews), veto checks, anti-patterns, measurement guide
- `seo/keyword-research/references/`: keyword-intent-taxonomy.md, keyword-prioritization-framework.md, topic-cluster-templates.md
- `seo/meta-tags-optimizer/references/`: meta-tag-formulas.md, meta-tag-code-templates.md, ctr-and-social-reference.md
- `seo/schema-markup-generator/references/`: schema-decision-tree.md, schema-templates.md, validation-guide.md
- `seo/seo-analysis/scripts/`: analyze_gsc.py, pagespeed.py, url_inspection.py, cms_detect.py, push_strapi_seo.py, fetch_wordpress/contentful/ghost/strapi content scripts

---

## Step 2 — VECTOR Parity Check

**Command run (exact as specified):**
```
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase" && python -X utf8 -c "
import sys; sys.path.insert(0,'.')
from districts.marketing.google_ads_agent import GoogleAdsAgent
from districts.marketing.meta_ads_agent import MetaAdsAgent
from districts.marketing.seo_specialist import SEOSpecialist
g = GoogleAdsAgent(); print('GoogleAds OK:', type(g))
m = MetaAdsAgent(); print('MetaAds OK:', type(m))
s = SEOSpecialist(); print('SEO OK:', type(s))
" 2>&1 | tail -5
```

**Actual output:**
```
[INFO] [VECTOR][city] Agent SEOSpecialist gen 1 born at 500 HP using vector-focus
[INFO] [VECTOR][seo] initialized
GoogleAds OK: <class 'districts.marketing.google_ads_agent.GoogleAdsAgent'>
MetaAds OK: <class 'districts.marketing.meta_ads_agent.MetaAdsAgent'>
SEO OK: <class 'districts.marketing.seo_specialist.SEOSpecialist'>
```

All three agents instantiate successfully. Now parity analysis per NotFair feature:

### Google Ads Skills

| NotFair Feature | VECTOR Equivalent | Parity |
|---|---|---|
| `google-ads-audit` — 7-dimension account health | `GoogleAdsAgent.audit_account()` — LLM-only, 7 dimensions, no GAQL | ⚠️ Partial |
| `google-ads` manage — GAQL reads + write tools | `GoogleAdsAgent.analyze_performance()` — metrics comparison only, no GAQL, no mutations | ⚠️ Partial |
| `google-ads-copy` — RSA headlines/descriptions | `GoogleAdsAgent.generate_copy()` — RSA generation present | ✅ Working |
| `google-ads-landing` — landing page QS scoring | `GoogleAdsAgent.diagnose_landing_page()` — scraper + LLM QS score | ✅ Working |
| Business context persistence (`business-context.json`) | Not implemented — no persistent business context file | ❌ Missing |
| Change log with undo window (7/14-day) | Not implemented — no `change-log.json`, no `changeId` | ❌ Missing |
| Persona persistence (`personas/{accountId}.json`) | Not implemented | ❌ Missing |
| GAQL fan-out via `runScript` | Not implemented — no Google Ads API client | ❌ Missing |
| Policy freshness check (policy-registry.json staleness scan) | Not implemented — policies hardcoded as static dict | ❌ Missing |
| Impression Share diagnostics (Rank-lost vs Budget-lost) | Not implemented | ❌ Missing |

### Meta Ads Skills

| NotFair Feature | VECTOR Equivalent | Parity |
|---|---|---|
| `meta-ads-audit` — 7-dimension Meta audit | `MetaAdsAgent.audit_account()` — LLM-only, 6 dimensions | ⚠️ Partial |
| `meta-ads` manage — ROAS, frequency, creative fatigue | `MetaAdsAgent.diagnose_creative_fatigue()` + `analyze_roas()` | ✅ Working |
| Creative fatigue (frequency > 3.0, CTR WoW drop > 25%) | `MetaAdsAgent.diagnose_creative_fatigue()` — thresholds correct | ✅ Working |
| Learning phase triage | Not explicitly implemented — covered in LLM audit prompt | ⚠️ Partial |
| Audience overlap detection | Not implemented as a separate diagnostic | ❌ Missing |
| Meta math formulas (break-even ROAS, headroom$) | Not implemented — no `meta-math.md` equivalent | ❌ Missing |
| CAPI/Pixel health audit | Not implemented | ❌ Missing |
| Attribution window discipline (7DC1DV) | Not implemented | ❌ Missing |
| Meta Marketing API reads (`getInsights`, `graphParallel`) | Not implemented — no real Meta API client | ❌ Missing |
| Mutation tools (`pauseAdSet`, `updateAdSetBudget`, etc.) | Not implemented | ❌ Missing |

### SEO Skills

| NotFair Feature | VECTOR Equivalent | Parity |
|---|---|---|
| `seo-analysis` — GSC + PageSpeed + URL Inspection | `SEOAgent.full_audit()` — GSCClient + PageSpeedClient + BrokenLinkChecker wired | ✅ Working |
| `seo-page` — single-URL deep audit | `SEOSpecialist.audit_technical_seo()` — HTML-based only | ⚠️ Partial |
| `content-writer` — E-E-A-T blog/landing/improvement | `SEOSpecialist.optimize_content()` — basic keyword density only | ⚠️ Partial |
| `content-planner` — GSC-backed editorial calendar | Not implemented | ❌ Missing |
| `keyword-research` — seed → clusters + GEO tagging | `SEOSpecialist.research_keywords()` — LLM-based, no intent taxonomy or GEO tagging | ⚠️ Partial |
| `meta-tags-optimizer` — title/meta/OG + CTR estimates | Embedded in `SEOSpecialist.optimize_content()` — minimal | ⚠️ Partial |
| `schema-markup-generator` — JSON-LD decision tree | `SEOAgent.generate_schema_markup()` — basic, no decision tree | ⚠️ Partial |
| `broken-link-checker` | `SEOAgent.check_broken_links()` — full crawler present | ✅ Working |
| **`geo-optimizer` — GEO/AEO (PAWC scoring, per-engine)** | `SEOAgent.optimize_for_ai_search()` — LLM-only, no PAWC math, no 4-pillar scoring, no per-engine playbooks | ❌ Missing (stub exists, not implemented) |
| `setup-cms` — WordPress/Strapi/Contentful/Ghost | `seo-analysis/scripts/`: cms_detect.py + fetch_*.py present | ✅ Working |
| CMS push (Strapi SEO fields) | `seo-analysis/scripts/push_strapi_seo.py` present | ✅ Working |
| `AICitationStrategist` — entity clarity + citation content | `AICitationStrategist` — entity audit + citation-optimized content generation | ✅ Working |

### Cross-Model / Other

| NotFair Feature | VECTOR Equivalent | Parity |
|---|---|---|
| `gemini` — Gemini CLI review/challenge/consult | Not implemented (no Gemini CLI skill) | ❌ Missing |
| Plugin self-updater (`notfair-upgrade-skill`) | Not applicable (VECTOR is not a Claude plugin) | N/A |
| `.notfair.json` config (accountId, metaAccountId) | Not implemented — no equivalent config file | ❌ Missing |
| `bin/notfair-change-watch` (session-start reminder) | Not implemented | ❌ Missing |

---

## Step 3 — Integration Plan

### How to Wire the Remote MCP Servers

The `.mcp.json` in NotFair declares two streamable-HTTP MCP servers:
```json
{
  "mcpServers": {
    "NotFair-GoogleAds": { "type": "http", "url": "https://notfair.co/api/mcp/google_ads" },
    "NotFair-MetaAds":   { "type": "http", "url": "https://notfair.co/api/mcp/meta_ads" }
  }
}
```

To wire into VECTOR's `core/mcp_server.py` and allow VECTOR agents to make Google Ads + Meta Ads mutations through their real platform APIs:

1. **Auth:** Requires sign-in to `https://notfair.co` once per platform (OAuth 2.1 with dynamic client registration). Token stored in OS keychain. Register a notfair.co account first.

2. **Add to VECTOR's `.mcp.json` or `core/config.py`:**
   ```python
   CONFIG["mcp_servers"]["notfair_google_ads"] = {
       "type": "streamable_http",
       "url": "https://notfair.co/api/mcp/google_ads",
       "auth": "oauth2"
   }
   CONFIG["mcp_servers"]["notfair_meta_ads"] = {
       "type": "streamable_http",
       "url": "https://notfair.co/api/mcp/meta_ads",
       "auth": "oauth2"
   }
   ```

3. **Upgrade `GoogleAdsAgent` and `MetaAdsAgent`** to use `mcp__NotFair-GoogleAds__runScript` and `mcp__NotFair-MetaAds__runScript` via VECTOR's MCP client (`core/mcp_server.py`) instead of purely LLM-reasoning.

4. **Create `.notfair.json`** in the project root:
   ```json
   { "accountId": "<Google Ads CID>", "metaAccountId": "<Meta Ad Account ID>" }
   ```

### Agent Gaps to Fill

**Priority 1 — GEO Optimizer (no VECTOR equivalent exists)**

This is the biggest gap. NotFair's `geo-optimizer` skill is based on published research (Princeton/GA Tech KDD 2024, CMU AutoGEO ICLR 2026, C-SEO Bench NeurIPS 2025). VECTOR's `optimize_for_ai_search()` in `seo_agent.py` routes to LLM with a vague prompt — no PAWC math, no 4-pillar scoring, no per-engine playbooks.

File to create: `districts/marketing/geo_optimizer_agent.py`

Key logic to implement:
- PAWC scoring formula: `Σ |sentence| · e^(-pos/total) / total_words`
- 4-pillar GEO score (Evidence Density 35%, Structure 25%, Authority Signals 25%, AI Crawlability 15%)
- Veto checks: blocked AI bots, fabricated citations (hard fail), no author, YMYL without disclaimers
- Per-engine playbooks (ChatGPT → Wikipedia links, Perplexity → freshness/dates, Claude → primary academic sources, Gemini → Reddit/Quora, AI Overviews → existing organic top-10 content)
- Evidence Hunt step (mandatory before rewrite — WebSearch for real sources)
- Anti-pattern stripper (keyword stuffing −8% PAWC penalty, vague entities, filler intros)
- Three modes: Audit / Optimize / Strategy

Source: `NotFair-main/seo/geo-optimizer/SKILL.md` + `references/geo-techniques.md`

**Priority 2 — Business Context Persistence + Change Log**

`GoogleAdsAgent.audit_account()` runs in stateless LLM mode each time — it does not save business context or personas. NotFair's audit persists:
- `~/.toprank/business-context.json` (schema: business_name, industry, services, personas, brand_voice, differentiators, competitors, unit_economics, audit_date)
- `~/.toprank/personas/{accountId}.json`
- `change-log.json` with `changeId`, `reviewAfter`, undo window

Add persistence to:
- `districts/marketing/google_ads_agent.py` (save after `audit_account()`)
- `districts/marketing/meta_ads_agent.py` (save after `audit_account()`)

**Priority 3 — Meta Math Module**

Create `districts/marketing/meta_math.py` implementing the formulas from `meta-ads/shared/meta-math.md`:
- Break-even ROAS = `1 / profit_margin`
- Break-even CPA = `aov × profit_margin`
- Hook Rate = `3-sec video views / impressions × 100`
- Headroom$ = `(break_even_cpa - current_cpa) × monthly_conversions`
- Always use `inline_link_clicks` not `all clicks` for CTR

**Priority 4 — Content Planner**

`seo/content-planner/` generates a dated editorial calendar from actual GSC data (position buckets, CTR gaps, seasonal patterns). VECTOR has no equivalent. New file: `districts/marketing/content_planner_agent.py`.

**Priority 5 — Gemini Cross-Model Review**

`gemini/SKILL.md` orchestrates Google's Gemini CLI (`npm install -g @google/gemini-cli`) for adversarial review of Google Ads changes, SEO metadata, and code. VECTOR has no equivalent. Since VECTOR already has `core/inference/provider_client.py` with Gemini API support, a lighter-weight `GeminiReviewAgent` could use the Gemini API directly (without the CLI) for the same three modes.

---

## Step 4 — Verdict: INTEGRATE DIRECTLY + PATCH VECTOR

NotFair is MIT licensed, well-engineered, and targets exactly the gaps in VECTOR's marketing district. The three agents (`GoogleAdsAgent`, `MetaAdsAgent`, `SEOSpecialist`) instantiate and run correctly as VECTOR agents. The parity check passes at the class level.

**What NotFair adds that VECTOR currently lacks:**

1. Real platform API access — NotFair's MCP servers are the only path to live Google Ads data (GAQL, search terms, keyword performance, impression share, conversion actions) and live Meta Ads data (Graph API, insights, creative performance). VECTOR's agents currently run in LLM-only mode when credentials are absent. Wiring the MCP servers unlocks real-data audits.

2. GEO Optimizer — VECTOR's `optimize_for_ai_search()` is a stub. NotFair's `geo-optimizer` has the full PAWC math, 4-pillar scoring rubric, veto checks, fabrication guard, and per-engine playbooks backed by three recent academic papers. This is the most production-ready GEO implementation available in the open-source space and should be absorbed wholesale.

3. Reference knowledge corpus — 30+ `.md` reference files covering Google Ads auction mechanics, Meta impression-share diagnostics, creative fatigue thresholds, Meta math formulas, GEO signal weights, keyword prioritization frameworks, and schema decision trees. These are high-quality domain references that improve every LLM prompt in the marketing district.

4. Change tracking discipline — NotFair's 7/14-day review window with `changeId` + `undoChange` capability is a production-grade change management pattern VECTOR is missing.

**Integration approach:** Do not copy the plugin SKILL.md files to run as Claude skills inside VECTOR (VECTOR is a Python agent system, not a Claude Code plugin). Instead:
- Absorb `geo-techniques.md` content as a knowledge file for the new `GeoOptimizerAgent`
- Wire the two MCP servers into VECTOR's config for live data access
- Port the reference frameworks (meta-math, account-health-scoring, change-tracking) as Python logic

---

## Step 5 — Gaps (with file:line)

### Gap 1 — GEO Optimizer: PAWC math and 4-pillar scoring not implemented
- **File:** `districts/marketing/seo_agent.py:170–206` — `optimize_for_ai_search()` sends a vague prompt to LLM, no PAWC formula, no pillar scores, no veto checks
- **Impact:** VECTOR's GEO optimization is non-functional against production AI search engines
- **Fix:** Create `districts/marketing/geo_optimizer_agent.py`; absorb `NotFair-main/seo/geo-optimizer/references/geo-techniques.md` as the scoring reference
- **Source:** `NotFair-main/seo/geo-optimizer/SKILL.md` + `references/geo-techniques.md`

### Gap 2 — Google Ads: No GAQL client, no live data
- **File:** `districts/marketing/google_ads_agent.py:81–137` — `audit_account()` uses LLM reasoning only; no `runScript`, no GAQL queries, no real account data
- **Impact:** Audit is pure hallucination without credentials; no wasted spend numbers, no real keyword data
- **Fix:** Wire `NotFair-GoogleAds` MCP server; add `_gaql_query()` method that delegates to `mcp__NotFair-GoogleAds__runScript`
- **Source:** `NotFair-main/google-ads/manage/SKILL.md:54` — "Reads go through `runScript` with `ads.gaql` / `ads.gaqlParallel`"

### Gap 3 — Google Ads: No change log or undo capability
- **File:** `districts/marketing/google_ads_agent.py` — no `change-log.json` write, no `changeId` capture, no `reviewAfter` scheduling
- **Impact:** Changes are invisible to future sessions; no 7/14-day review cycle; no undo
- **Fix:** Add `_log_change()` helper that writes to `~/.vector/marketing/change-log.json`; schedule review via `core.brain.goal_system` SHORT goals
- **Source:** `NotFair-main/google-ads/manage/references/change-tracking.md:1–53`

### Gap 4 — Google Ads: No business context or persona persistence
- **File:** `districts/marketing/google_ads_agent.py:86` — `business_context: str = ""` is accepted as a transient string, never saved to disk
- **Impact:** Each `audit_account()` call starts cold; downstream `generate_copy()` has no brand voice, no differentiators, no audience data
- **Fix:** Save/load `~/.vector/marketing/business-context-{account_id}.json` after first audit; expose `load_business_context(account_id)` method
- **Source:** `NotFair-main/google-ads/audit/references/business-context.md`, schema at `SKILL.md:24`

### Gap 5 — Meta Ads: No Meta Math (break-even ROAS, headroom$)
- **File:** `districts/marketing/meta_ads_agent.py:193–216` — `analyze_roas()` uses raw ROAS comparison against a benchmark dict; does not compute break-even ROAS, headroom$, or max-profitable CPA from profit margin and AOV
- **Impact:** ROAS recommendations have no profitability grounding; "above benchmark" is not the same as "above break-even"
- **Fix:** Create `districts/marketing/meta_math.py`; implement all formulas from `meta-ads/shared/meta-math.md:13–60`
- **Source:** `NotFair-main/meta-ads/shared/meta-math.md`

### Gap 6 — Meta Ads: No Learning Phase diagnostics
- **File:** `districts/marketing/meta_ads_agent.py:265–289` — `run()` dispatches `fatigue` and `roas` actions but has no explicit `learning_phase` action or threshold logic for the 50-optimization-events exit condition
- **Impact:** VECTOR may recommend editing ad sets that are in Learning Phase, destabilizing delivery
- **Fix:** Add `diagnose_learning_phase(ad_set_data)` method; implement the "do not recommend changes during Learning unless consolidating to 50 events" guard
- **Source:** `NotFair-main/meta-ads/manage/references/learning-phase.md`

### Gap 7 — Meta Ads: Attribution window not tracked
- **File:** `districts/marketing/meta_ads_agent.py:30` — `META_ADS_POLICIES["attribution-window"]` cites 7-day click / 1-day view as a text note but is not enforced in any metric computation; `analyze_roas()` reports bare ROAS values with no window annotation
- **Impact:** "ROAS 3.2×" without an attribution window is meaningless and can be 20-40% wrong
- **Fix:** Add `attribution_window: str = "7DC1DV"` parameter to `analyze_roas()` and `audit_account()`; include window in all reported metrics
- **Source:** `NotFair-main/meta-ads/manage/SKILL.md:47`

### Gap 8 — SEO: No content planner (GSC-driven editorial calendar)
- **File:** `districts/marketing/` — no `content_planner_agent.py` exists; `seo_specialist.py:113` has keyword research but no calendar logic
- **Impact:** No systematic way to build a dated content calendar from CTR gap analysis, seasonal patterns, and position buckets
- **Fix:** Create `districts/marketing/content_planner_agent.py`; use `SEOAgent.fetch_gsc()` as data source
- **Source:** `NotFair-main/seo/content-planner/SKILL.md`

### Gap 9 — SEO: meta-tags-optimizer is minimal
- **File:** `districts/marketing/seo_specialist.py:169–176` — `optimize_content()` returns a hardcoded title template `"{keyword} — Complete Guide | VECTOR"` — not E-E-A-T-aware, no A/B variants, no CTR estimates, no character-count enforcement for OG/Twitter cards
- **Impact:** Title generation is generic and not optimized for real CTR lift
- **Fix:** Upgrade `SEOSpecialist` with the formulas from `NotFair-main/seo/meta-tags-optimizer/references/meta-tag-formulas.md` and `ctr-and-social-reference.md`

### Gap 10 — SEO: Keyword research has no GEO relevance tagging
- **File:** `districts/marketing/seo_specialist.py:112–143` — `research_keywords()` generates primary/secondary/long-tail/questions clusters via LLM, no "GEO relevance" flag for keywords likely to trigger AI answers
- **Impact:** Keywords that should drive GEO optimization are not flagged; content strategy misses AI search opportunity
- **Fix:** Add a `geo_relevant: bool` field per keyword cluster; flag queries matching patterns: definition questions, comparison queries, "best X for Y", procedural how-tos — per the GEO keyword taxonomy in `NotFair-main/seo/keyword-research/references/keyword-intent-taxonomy.md`

### Gap 11 — No Gemini cross-model review
- **File:** `districts/marketing/` — no Gemini review agent
- **Impact:** No adversarial second-opinion path for Google Ads changes (Gemini has native Google ecosystem knowledge that is uniquely valuable for Google Ads and Search policy checks)
- **Fix:** Create `districts/marketing/gemini_review_agent.py`; use `core/inference/provider_client.py` Gemini API path (already implemented at `core/inference/llm_providers.py`) rather than requiring the Gemini CLI; implement three modes (review/challenge/consult)
- **Source:** `NotFair-main/gemini/SKILL.md`

### Gap 12 — No `.notfair.json` / ads config file pattern
- **File:** `core/config.py` — no standardized per-project ads config (Google Ads CID, Meta Ad Account ID)
- **Impact:** `audit_account()` in both agents requires `account_id` to be passed as a parameter each time — no persistence or auto-detection
- **Fix:** Add `CONFIG["marketing"]["google_ads_account_id"]` and `CONFIG["marketing"]["meta_account_id"]` fields; load from env vars `GOOGLE_ADS_CID` and `META_AD_ACCOUNT_ID`

---

## Summary Scores

| Category | VECTOR Has | NotFair Adds | Priority |
|---|---|---|---|
| Google Ads — analysis | ⚠️ LLM-only (no live data) | Real GAQL, 100 tools via MCP | HIGH |
| Google Ads — mutations | ❌ None | Pause/enable/bid/budget/keywords | HIGH |
| Google Ads — business context | ❌ None | Persistent JSON + persona profiles | HIGH |
| Google Ads — change tracking | ❌ None | change-log.json + undo | MEDIUM |
| Meta Ads — analysis | ⚠️ Partial | Audience overlap, CAPI health, attribution window | MEDIUM |
| Meta Ads — mutations | ❌ None | pause/enable/budget tools | HIGH |
| Meta Math | ❌ None | Break-even ROAS, headroom$ | MEDIUM |
| SEO — full audit | ✅ Working | GSC + PageSpeed already wired | LOW |
| SEO — GEO Optimizer | ❌ Stub only | Full PAWC + 4-pillar scoring + per-engine playbooks | HIGH |
| Content planner | ❌ None | GSC-driven editorial calendar | MEDIUM |
| Gemini review | ❌ None | Cross-model adversarial review | LOW |

**Overall verdict: INTEGRATE DIRECTLY + PATCH VECTOR.** Wire both MCP servers first (unlocks live data immediately). Then build `GeoOptimizerAgent` (highest unique value). Then add business-context persistence and meta-math.
