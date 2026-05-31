# Repo Audit — `ui-ux-pro-max-skill-main`

> Audited 2026-05-31 against VECTOR (`production-hardening-complete`). Read + run only; no VECTOR code modified.
> Repo: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill (v2.5.0, MIT)

---

## Section 1 — Repo Reality

**What it is:** A **Claude Code / multi-platform AI design skill** — a curated UI/UX *knowledge database* (CSV) plus a tiny offline **BM25 search engine** and a **design-system generator**, packaged as an installable skill via an npm CLI (`uipro-cli`). It is NOT an app, NOT a runtime service, NOT a component library. It produces *design recommendations* (text/markdown/ASCII), not rendered UI.

**Languages:**
- **Python 3.x** — the actual search/generation engine (`src/ui-ux-pro-max/scripts/core.py`, `search.py`, `design_system.py`). Pure stdlib (`csv`, `re`, `math`, `argparse`) — zero pip deps.
- **TypeScript** — the `cli/` installer (`uipro-cli`): detects the target AI tool, downloads + extracts the skill, writes platform configs for 18 tools (Claude, Cursor, Windsurf, Copilot, Codex, Gemini, etc.).
- **Markdown + CSV** — the knowledge payload and `.claude/skills/*/SKILL.md` skill manifests.

**Concrete capabilities (verified by reading + running):**

1. **BM25 design search** (`core.py`) — offline ranked search over CSV knowledge with auto domain-detection (`detect_domain`) across domains: `style, color, chart, landing, product, ux, typography, icons, react, web, google-fonts`. k1=1.5, b=0.75, stdlib-only.
2. **Stack-specific search** (`search_stack`) — 16 stacks: react, nextjs, vue, svelte, astro, swiftui, react-native, flutter, nuxtjs, nuxt-ui, html-tailwind, shadcn, jetpack-compose, threejs, angular, laravel.
3. **Design-system generator** (`design_system.py`) — runs 5 parallel domain searches (product/style/color/landing/typography), applies `ui-reasoning.csv` rules, emits a full recommended design system (pattern + style + colors + typography + effects + anti-patterns + pre-delivery checklist) as ASCII or markdown.
4. **Persistence** — `--persist` writes `design-system/<project>/MASTER.md` + per-page override files (Master+Overrides pattern).
5. **Curated knowledge payload (CSV, ~7,300 rows):** `styles.csv` (84 styles), `colors.csv` (160 palettes), `typography.csv` (73 font pairings), `products.csv` (161 product types), `ux-guidelines.csv` (98 rules), `charts.csv` (25 chart types), `landing.csv` (34 patterns), `google-fonts.csv` (1,923 fonts), `icons.csv`, `react-performance.csv`, `app-interface.csv`, + 16 per-stack guideline CSVs.
6. **Multi-platform installer** (`cli/`) — `npx uipro-cli init --ai <platform>`, plus `update`, `uninstall`, `versions`; 18 platform config templates.
7. **Sub-skills under `.claude/skills/`** — `brand`, `design`, `design-system`, `slides`, `ui-styling` (ships ~40 TTF fonts), `banner-design`. These are largely SKILL.md docs + small `.py`/`.cjs` helper scripts (token generators, color extractors, slide generators).

---

## Section 2 — VECTOR Parity (verified by running)

VECTOR's nearest equivalents live in `districts/design/` (LLM-prompt agents) and `.claude/skills/frontend-ui-engineering/` (a docs skill). Key structural difference: **VECTOR's design capability is LLM-prompt-driven (calls a model at runtime); the repo is a curated-data + offline-BM25 lookup (zero model, zero deps, deterministic).** VECTOR has **no design knowledge data and no design search engine anywhere.**

| # | Repo feature | VECTOR equivalent (real path) | Verdict |
|---|--------------|-------------------------------|---------|
| 1 | BM25 design knowledge search | none — no design CSV/index in `core/`, `districts/`, `.claude/`. `find . -name "*.csv" \| grep -iE "color\|style\|typo\|design"` → **0 hits** | ❌ missing |
| 2 | Curated style DB (84 styles) | none. `districts/design/ui_designer.py` has ONE hardcoded `_VECTOR_DESIGN_TOKENS` dict (10 colors, 1 font pair) for VECTOR's own HUD | ❌ missing |
| 3 | 160-palette color DB | none — same single hardcoded token dict | ❌ missing |
| 4 | 73 font pairings + 1,923 Google Fonts | none | ❌ missing |
| 5 | 161 product-type reasoning rules | none — `ui_designer.py` reasons via live LLM (`vectorcode_llm.chat`), no rule DB | ❌ missing |
| 6 | 98 UX guidelines DB | partial — `districts/design/ux_researcher.py` (232 LOC) is an LLM agent; no searchable guideline DB. `.claude/skills/frontend-ui-engineering/SKILL.md` (328 lines) has prose a11y/perf guidance, not queryable | ⚠️ present but no DB/search |
| 7 | Design-system generator (5-domain + reasoning) | partial — `UIDesigner.generate_css_variables()` emits CSS from one fixed token set; no product→style→color reasoning. **Ran it:** outputs VECTOR-branded `:root{}` (`--color-primary:#6366f1 …`) — works but is a single hardcoded theme, not a generator | ⚠️ stub vs. repo |
| 8 | 16 stack-specific guideline DBs | none | ❌ missing |
| 9 | Multi-platform skill installer (18 tools) | n/a — VECTOR is single-owner; skills live in-tree. No equivalent needed | ❌ missing (n/a) |
| 10 | Design-token persistence (MASTER.md + overrides) | none | ❌ missing |
| 11 | Image-prompt engineering | `districts/design/image_prompt_engineer.py` (215 LOC, LLM agent) — overlaps repo's logo/icon prompt refs conceptually | ⚠️ different approach |

**Run evidence — repo (works ✅):**

```
$ python -X utf8 search.py "SaaS dashboard fintech" --domain style --max-results 1
## UI Pro Max Search Results
**Domain:** style | **Query:** SaaS dashboard fintech | **Found:** 1 results
### Result 1
- Style Category: SaaS Mobile (High-Tech Boutique)
- Primary Colors: Electric Blue #0052FF, Gradient End #4D7CFF
- Best For: B2B SaaS mobile dashboards, fintech apps, developer tools...
- Design System Variables: --bg:#FAFAFA --accent:#0052FF --radius:16px ...

$ python -X utf8 search.py "beauty spa landing page" --design-system -p "TestSpa"
TARGET: TestSpa - RECOMMENDED DESIGN SYSTEM
 PATTERN: Scroll-Triggered Storytelling | STYLE: Soft UI Evolution
 COLORS: Primary #EC4899 / Accent #8B5CF6 / Background #FDF2F8
 TYPOGRAPHY: Playfair Display / Inter  (Google Fonts URL emitted)
 KEY EFFECTS / anti-patterns / pre-delivery checklist ...
```

**Run evidence — VECTOR (works but is a fixed theme ⚠️):**

```
$ python -X utf8 -c "from districts.design.ui_designer import UIDesigner; print(UIDesigner().generate_css_variables()[:400])"
[VECTOR][city] Agent UIDesigner gen 1 born at 500 HP using vector-focus
[VECTOR][ui_designer] initialized
:root {
  /* VECTOR Design System */
  --color-primary: #6366f1;  --color-secondary: #22d3ee; ...
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace; ...
```

VECTOR's `UIDesigner` instantiates and emits CSS — but it is one hardcoded indigo/slate HUD theme. It cannot answer "what style+palette+fonts for a fintech SaaS?" without a live LLM call, and even then has no curated, ranked, deterministic knowledge base behind it.

**Tally:** repo features = 11 · VECTOR ✅ = 0 · ⚠️ = 4 · ❌ = 7.

---

## Section 3 — Frontend → Panel Design

The repo has **no frontend / no UI components / no rendered widgets** to mirror. Its only "visual" output is an ASCII/markdown design-system report printed to stdout, and a marketing website screenshot (`screenshots/website.png`) that is not part of the skill. The `ui-styling` sub-skill ships TTF fonts and the `slides` sub-skill generates HTML slides, but neither is an interactive app.

**No HUD panel spec required.** If VECTOR ever surfaces this engine in its HUD (`frontend/VECTOR.html`), the natural panel would be a **"Design Advisor"** card: a query input + stack dropdown, and a result card rendering the generator's output (pattern, swatch row using the returned hex values, font-pairing preview, anti-pattern list, checklist). Documented only — not built.

---

## Section 4 — Verdict

### **INTEGRATE DIRECTLY — as a VECTOR district, not a CLI skill**

**Runtime rule (user directive 2026-05-31):** VECTOR is provider-agnostic — it may use ANY LLM (Ollama, Claude, GPT, Gemini, …) via `core/inference/provider_client.py` (Ollama-first, cloud fallback). What it can't depend on is the **Claude Code / multi-CLI agent harness** that this repo ships as a *skill* for — VECTOR is its own runtime, not that CLI. So that skill form is discarded; only the **data corpus + BM25 engine + design-system generator** are ported into `districts/design/knowledge/` (Python). BM25 search needs **no LLM at all** (pure stdlib). The design-system *generation* step routes through `provider_client` (whatever provider is configured — local or cloud). End state: a native VECTOR design capability callable by the loop + HUD.

**Gap size: vast.** VECTOR has design *agents* but **zero design knowledge data and zero design search** — features #1–#5, #8, #10 are flat ❌, and the two ⚠️ items (UX guidance, token generation) are prose/single-theme stubs, not the repo's ~7,300-row searchable, ranked, deterministic, offline knowledge base. Reimplementing 84 styles + 160 palettes + 73 font pairings + 161 product reasoning rules + 98 UX rules + 16 stack guides as native Python would be hundreds of hours of *content authoring* (the value is the curated data, not the 263-line BM25 engine).

**Why integrate, not rewrite or delete:**
- The BM25 engine is **pure Python stdlib, zero pip deps** — drops into VECTOR cleanly with no dependency conflicts.
- The value is the **curated CSV corpus** — irreplaceable without manual authoring; rewriting is pointless.
- It is **fully local + deterministic** — aligns with VECTOR Rule 11 (no cloud at runtime), unlike VECTOR's current LLM-call-per-design-decision agents.
- MIT license → safe to vendor.

**Integration seam (recommended, do NOT build here):**
1. Vendor `src/ui-ux-pro-max/{scripts,data}` → `districts/design/knowledge/` (data + `core.py`/`search.py`/`design_system.py`). Pure-stdlib, no `requirements.txt` change.
2. Wire `search()` / `generate_design_system()` into `districts/design/ui_designer.py` so the LLM agent **retrieves from the curated DB first**, then reasons — RAG-style grounding instead of free-form generation. Seam: `UIDesigner.generate_css_variables()` (`districts/design/ui_designer.py:62`) and the agent's main handler.
3. Optionally expose as an MCP tool (`design_search`) in `core/mcp_server.py` alongside existing tools, so any VECTOR agent can query design knowledge.
4. Skip the `cli/` TypeScript installer and the 18 platform templates — single-owner VECTOR installs in-tree (feature #9 is n/a).
5. Skip the `ui-styling` TTF font bundle unless the slides/banner sub-skills are wanted; treat those as separate optional absorptions.
