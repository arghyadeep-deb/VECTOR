# VECTOR Repo-Audit MASTER TRACKER

Single source of truth for every gap, bug, patch, integration, and delete-decision
across all audited repos. Nothing gets fixed or deleted until ALL repos are audited.

**Delete-readiness semantics (corrected 2026-05-31):**
- **DELETE-NOW** — all value absorbed + working + zero pending work needing the repo.
- **DELETE-AFTER** — absorbed, but a pending patch uses the repo as reference diff → delete only after that patch lands.
- **KEEP** — repo is a live dependency or integration source we don't reimplement.
- A repo with ANY open ⚠️/❌/harvest is NOT delete-now.

Status legend: 🔴 safety · 🐛 bug · 🔵 patch/harvest · 🟢 integrate · 🎨 panel · ✅ done

---

## A. Standalone VECTOR bugs (independent of any single repo)

| # | Issue | Location | Severity | Status |
|---|---|---|---|---|
| A1 | **Ungated live trade execution** — `create_order()` fires real orders, never routes through permission_gateway (no human-confirm, no kill switch) | `districts/investment/vector_finagent/exchange/place_order.py:84`, `agno_trading/core/auto_trader.py` | 🔴 CRITICAL | OPEN |
| A2 | **IndentationError** — empty `if` body blocks `import districts.investment.vector_backtest` (package top-level) | `districts/investment/vector_backtest/__init__.py:21` | 🐛 HIGH | OPEN |
| A3 | IndentationError in backtest test conftest (flagged by valuecell audit) | `vector_backtest/tests/conftest.py:10` | 🐛 MED | OPEN (verify) |
| A4 | `rag_anything` import typo — dead multimodal-RAG hook (real pkg is `raganything`, also not installed) | `core/memory/obsidian_sync.py:377` | 🐛 LOW | OPEN (only matters if enabling multimodal doc RAG) |
| A5 | `lightrag-hku` NOT declared in requirements.txt — survives only in global site-packages | `requirements.txt` | 🐛 MED | OPEN |
| A6 | `ContextEngine.get_vault_context` missing → LightRAG graph-RAG never feeds session_hydration_prompt() | `core/loop/context_engine.py` | 🔵 | OPEN |
| A7 | `find_public_api` MCP tool silently dead — `api_catalog.py` README source path doesn't exist | `districts/research/api_catalog.py:7` | 🐛 MED | OPEN |
| A8 | postiz modules (analytics_retriever, blog_publisher, post_job) verified working (69 tests) but **zero callers** — not exported in `content/__init__.py`, not wired to any orchestrator | `districts/content/__init__.py:10-17` | 🔵 | OPEN |
| ~~A?~~ | ~~agent_base.py:56 CONFIG[models][focus] crash~~ — **DISPROVEN**: returns 'vector-focus' fine, not a bug (ruflo agent was wrong; likely saw socket-exhaustion error) | — | — | NOT A BUG |

---

## B. Per-repo status

### 1. voicebox-main — PATCH (mostly done)
| Item | Type | Status |
|---|---|---|
| `speak_as` TypeError (profile_name) | 🐛 | ✅ FIXED |
| `FileStorage` LocalDriver bug | 🐛 | ✅ FIXED |
| Voice Studio HUD panel (script → cloned voice) | 🎨 | ✅ BUILT |
| `chatterbox-tts` local cloning engine | dep | ✅ INSTALLED |
| STT refinement feature | 🔵 | OPEN (optional) |
| LLM persona-rewrite feature | 🔵 | OPEN (optional) |
| Record + upload owner reference sample + test cloning | 🔵 | OPEN (user step) |
**Delete-readiness:** DELETE-AFTER (2 optional features + verify cloning produces your voice). Repo still useful as reference for STT-refinement.

### 2. Vibe-Trading-main — PATCH
| Item | Type | Status |
|---|---|---|
| Alpha Zoo — 452 factor files (`agent/src/factors/` + `zoo/`) | 🔵 harvest | OPEN |
| `mootdx` A-share loader | 🔵 harvest | OPEN |
| Order-execution layer (mandate/kill-switch design = reference) | 🔴/🔵 | OPEN (in-scope now) |
**Delete-readiness:** DELETE-AFTER (Alpha Zoo + mootdx + execution-design harvest all need the repo).

### 3. Vane-master — PATCH
| Item | Type | Status |
|---|---|---|
| SearXNG import-blocked by missing `sqlalchemy_utc` dep | 🐛 | OPEN |
| No weather widget | 🔵 | OPEN |
| No answer-engine chat+citations+discover UI | 🎨 | OPEN (panel) |
**Delete-readiness:** DELETE-AFTER (UI panel + small fixes; repo is reference for the answer-engine UX).

### 4. ui-ux-pro-max-skill-main — INTEGRATE → KEEP-corpus
| Item | Type | Status |
|---|---|---|
| Vendor 7,300-row design corpus + BM25 → `districts/design/knowledge/` | 🟢 integrate | OPEN |
| Wire into `ui_designer.py:62` as RAG grounding (any LLM via provider_client) | 🟢 | OPEN |
| Optional `design_search` MCP tool | 🔵 | OPEN |
**Delete-readiness:** KEEP corpus (it IS the value); discard only the TS installer after vendoring data.

### 5. valuecell-main — PATCH
| Item | Type | Status |
|---|---|---|
| Gate the 3 execution entry points through permission_gateway RED + kill switch (see A1) | 🔴 | OPEN |
| `pip install ccxt` (7 features need it) | dep | OPEN |
| No finance HUD panel | 🎨 | OPEN (panel) |
| Reference for paper-first/testnet-default guardrail design | 🔵 | keep until A1 done |
**Delete-readiness:** DELETE-AFTER (execution-gating + finance panel; repo is the guardrail reference).

### 6. Understand-Anything-main — DONE
| Item | Type | Status |
|---|---|---|
| `core/knowledge/` absorption (105 tests) | — | ✅ VERIFIED |
| `/knowledge/graph` endpoint | — | ✅ BUILT |
| Code Graph HUD panel | 🎨 | ✅ BUILT |
**Delete-readiness:** ✅ **DELETE-NOW** — nothing pending.

### 7. UI-TARS-desktop-main — DELETE-AFTER
| Item | Type | Status |
|---|---|---|
| `core/vision_control/` port + visual grounding | — | ✅ VERIFIED (exists, grounding real) |
| Add pytest for `core/vision_control/` (smoke moves real mouse today) | 🔵 | OPEN (no repo needed) |
| Optional VLM mobile operator over `phone_controller` | 🔵 harvest | OPEN (repo = reference) |
**Delete-readiness:** DELETE-AFTER VLM-mobile harvest (or DELETE-NOW if you skip the optional mobile operator). Was wrongly marked DELETE-NOW.

### 8. TradingAgents-main — DELETE-AFTER
| Item | Type | Status |
|---|---|---|
| `core/trading/` near-identical port | — | ✅ VERIFIED (runs, HP=500) |
| Crypto `asset_type` mode plumbing (~6 files) | 🔵 harvest | OPEN (repo = reference diff) |
| Refresh `core/trading/llm_clients/model_catalog.py` | 🔵 | OPEN |
**Delete-readiness:** DELETE-AFTER crypto + model-catalog harvest. Was wrongly marked DELETE-NOW.

### 9. system_prompts_leaks-main — PATCH-or-DELETE (user decides)
| Item | Type | Status |
|---|---|---|
| Vendor corpus → `brain/reference/system_prompts/` + `prompt_library.py` loader | 🔵 | OPEN (optional) |
| Wire few-shot into prompt-optimizer + `prompt_library_search` MCP tool | 🔵 | OPEN (optional) |
**Delete-readiness:** DELETE-NOW if skipping prompt-engineering polish; else PATCH then delete. Pure data, CC0.

### 10. superpowers-main — DELETE-NOW
| Item | Type | Status |
|---|---|---|
| 14 Claude-Code skills; runtime capability covered (9✅/5⚠️) | — | ✅ VERIFIED |
| All 14 already in `brain/.claude/skills/` (Ruflo absorption) | — | ✅ redundant clone |
**Delete-readiness:** ✅ **DELETE-NOW** — no Python to port, no frontend; the 5 ⚠️ are interactive build-session disciplines, not missing autonomous capabilities; brain copy is canonical.

### 11. skills-main — DELETE-NOW
| Item | Type | Status |
|---|---|---|
| mattpocock/skills — 29 skills; runtime covered (18✅/7⚠️/4❌) | — | ✅ VERIFIED |
| 19 already installed in `~/.claude/skills/` (this is the source clone) | — | ✅ redundant clone |
| ❌4 are mattpocock-product/TS-only (no VECTOR value) | — | skip |
**Delete-readiness:** ✅ **DELETE-NOW** — zero genuinely-missing runtime capability; global install keeps build-session value; copy nothing into VECTOR.

### 12. Scrapling-main — DELETE-NOW
| Item | Type | Status |
|---|---|---|
| Scrapling 0.4.8 fully vendored → `core/scraper/` (same version) | — | ✅ VERIFIED (parser ran live) |
| Native `VectorScraper` wrapper on top | — | ✅ bonus |
**Delete-readiness:** ✅ **DELETE-NOW** — same-version vendored copy, working, zero pending. Clone is redundant.

### 13. ruflo-main — DELETE-AFTER (near-NOW)
| Item | Type | Status |
|---|---|---|
| Neural RL (A2C/DQN/PPO/SARSA/Q/DecisionTransformer), FlashAttention, MoE, ReasoningBank(57 entries), GNNRouter, swarm(8 topologies), claims, guidance | — | ✅ VERIFIED — 22 ran live |
| GOAP Goal-Planner frontend (`v3/goal_ui`) not absorbed | 🎨 | OPEN (decide: build panel or skip) |
| Tracker metadata wrong: Ruflo is **TS** (claude-flow v3.10.26) not Rust; **366** skills not 282; router is **3-layer** not 4 | 🐛 doc | note only |
**Delete-readiness:** DELETE-AFTER deciding on the GOAP planner panel (or DELETE-NOW if skipping it). Capability absorption verified real — "100%" true for capabilities.

### 14. LightRAG-main — DELETE-NOW clone + KEEP pip + PATCH
| Item | Type | Status |
|---|---|---|
| `lightrag-hku` v1.4.16 pip-installed (global site-packages), consumed via `core/memory/obsidian_sync.py` (Ollama backends) | — | ✅ wrapper exists, used in ~50 districts |
| A5: declare `lightrag-hku` in requirements.txt | 🐛 | OPEN |
| A6: implement `get_vault_context` so RAG feeds hydration | 🔵 | OPEN |
| RAG knowledge-graph WebUI → optional HUD panel (complementary to Code Graph) | 🎨 | OPEN (optional) |
**Delete-readiness:** **DELETE-NOW the clone** (VECTOR uses the pip package, never the clone). KEEP pip package. PATCH A5+A6.

### 15. RAG-Anything-main — DELETE-AFTER / DROP
| Item | Type | Status |
|---|---|---|
| Multimodal doc RAG (PDF/image/table/equation → KG) | — | ❌ NOT in VECTOR (text-only RAG today) |
| `obsidian_sync.py:377` hook is DEAD (A4 typo + pkg not installed) | 🐛 | OPEN |
| To enable: fix import name + `pip install raganything mineru` + route via provider_client | 🔵 | OPEN (only if multimodal doc RAG wanted) |
**Delete-readiness:** DELETE-AFTER (clone unused at runtime). Honest rec: **DROP** the dead hook unless a district genuinely needs PDF figure/table RAG. Revisit on demand.

---

## C. Delete-readiness summary

| Repo | When deletable |
|---|---|
| Understand-Anything | ✅ NOW |
| superpowers | ✅ NOW (redundant skill clone) |
| skills (mattpocock) | ✅ NOW (redundant skill clone) |
| Scrapling | ✅ NOW (same-version vendored) |
| system_prompts_leaks | NOW (if skipping optional corpus) |
| UI-TARS | after optional VLM-mobile (or now if skipped) |
| TradingAgents | after crypto + model-catalog harvest |
| voicebox | after optional features + cloning verify |
| Vibe-Trading | after Alpha Zoo + execution harvest |
| Vane | after UI panel + fixes |
| valuecell | after execution-gating + finance panel |
| ui-ux-pro-max-skill | KEEP corpus (vendor data, discard installer) |
| ruflo | after GOAP panel decision (or now if skipped) |
| LightRAG | NOW (clone) — keep pip package, patch A5/A6 |
| RAG-Anything | NOW (clone unused) — drop dead hook or wire multimodal |

**Genuinely DELETE-NOW today: Understand-Anything, superpowers, skills, Scrapling, LightRAG-clone (5).** Everything else has pending work.

---

## D. Audit progress
- Batch 1 ✅: voicebox, Vibe-Trading, Vane
- Batch 2 ✅: ui-ux-pro-max-skill, valuecell, Understand-Anything
- Batch 3 ✅: UI-TARS, TradingAgents, system_prompts_leaks
- Batch 4 ✅: superpowers, skills, Scrapling
- Batch 5 ✅: ruflo, LightRAG, RAG-Anything
- Batch 6+ ⏳: awaiting more repo paths
- **Rule: finish auditing ALL repos → then fix/harvest/delete in one pass.**
- **15 repos audited so far.**
