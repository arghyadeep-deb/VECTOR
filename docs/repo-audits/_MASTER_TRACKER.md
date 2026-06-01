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
| A9 | 🔴 **MemoryClient cloud-leak (RULE 11 VIOLATION)** — `vectorcode/src/plugins/memory/mem0/__init__.py:175-176` instantiates `MemoryClient(api_key=...)`. If `MEM0_API_KEY` is set, every conversation turn is sent to `api.mem0.ai`. Fix: replace with self-hosted `Memory` class or delete the file. (Verified: line 60 of code_reviewer.py is NOT a violation — it's a LINT RULE that catches this pattern.) | `vectorcode/src/plugins/memory/mem0/__init__.py:175-176` | 🔴 CRITICAL | OPEN |
| A10 | 🔴 **AutoHedge/Solana ungated execution** — `districts/investment/vector_hedgebot/` has no permission_gateway call. If `CONFIG["vector_hedgebot"]["live_trading"]=True` + `SOLANA_PRIVATE_KEY` set → signed blockchain transaction fires directly to Jupiter with zero owner confirmation, no council, no kill switch. (Verified: grep on vector_hedgebot/ returned 0 gateway hits.) | `districts/investment/vector_hedgebot/` | 🔴 CRITICAL | OPEN (same fix as A1 — add to RED tier + paper mode) |
| A11 | pocketbase: 8 test failures (Windows `WinError 10055` socket exhaustion in asyncio tests — `conftest.py` needs `asyncio.WindowsSelectorEventLoopPolicy()`). Not a logic bug. | `tests/test_collections.py` + `conftest.py` | 🐛 LOW | OPEN (1-line fix) |
| A12 | mem0 (`mem0ai`) not pip-installed — 2 VECTOR files correctly wire it but it will silently degrade if not installed | `requirements.txt` | 🐛 MED | OPEN (add `mem0ai` to requirements) |
| A13 | jcode: trajectory auto-compact trigger missing — `StoredCompactionState` field exists but 80%/95% threshold logic not ported | `core/jcode/session_persistence.py` | 🔵 | OPEN (~60 lines from jcode-master reference) |
| A14 | openfang `OFPNode._init_tls()` `NameError: _C` — needs `_C = CONFIG` alias | `core/network/ofp_protocol.py` | 🐛 LOW | OPEN (1 line) |
| A15 | openfang `TaintTracker.tag()` TypeError on dict label input | `core/security/taint_tracker.py` | 🐛 LOW | OPEN |
| A16 | 🎨 openfang Approvals dashboard (5,411-line Alpine.js, 17 panels) not absorbed — especially the **Approvals panel** (human-in-loop for YELLOW/RED actions). No VECTOR equivalent. Build as HUD panel. | `frontend/` | 🎨 HIGH | OPEN — BUILD NOW |
| A17 | openhuman subconscious loop pattern not harvested — cron LLM-vs-situation-report → act/escalate/noop, proactive reflections | `districts/chief_of_staff/` | 🔵 | OPEN (harvest before deleting repo) |
| ~~A?~~ | ~~agent_base.py:56 CONFIG[models][focus] crash~~ — **DISPROVEN**: returns 'vector-focus' fine, not a bug (ruflo agent was wrong; likely saw socket-exhaustion error) | — | — | NOT A BUG |
| A18 | **`subscribe_to` missing from AgentBase — systemic crash** — 3+ agents call `self.subscribe_to()` in `__init__` but `AgentBase` has no such method; crashes on instantiation (confirmed: ResearchHub, ConsolidationBot). All event-subscribed agents are silently dead. Fix: add `subscribe_to(event)` to AgentBase that registers with `core/event_bus`. | `core/city/agent_base.py` + `districts/research/research_hub.py:64` + `districts/memory_curator/consolidation_bot.py:49` | 🐛 CRITICAL | OPEN |
| A27 | **ZKSteward wrong vault path** — resolves to `C:\Users\Arghyadeep\V.E.C.T.O.R Brain` (doesn't exist); correct path is `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain`. Every `scan_vault_notes()` call silently returns 0. | `districts/personal_growth/zk_steward.py:32` | 🐛 HIGH | OPEN |
| A28 | **Brain vault hooks never fire** — `.claude/settings.json` missing from Brain vault; all 5 lifecycle hooks (SessionStart, UserPromptSubmit, PostToolUse, PreCompact, Stop) are dead | `brain/.claude/settings.json` | 🐛 HIGH | OPEN |
| A29 | **AdsOrchestrator runs platforms sequentially** — `for platform in platforms:` loop instead of `asyncio.gather()` → misses parallel-audit performance target | `districts/marketing/ads/ads_orchestrator.py` | 🐛 MED | OPEN |
| A30 | **No `AdsScorer` class** — weighted scoring formula exists only in reference .md, not as testable Python code | `districts/marketing/` | 🔵 | OPEN |
| A31 | **Ads Wave 2 sub-skills not installed** — `ads-amazon`, `ads-attribution`, `ads-server-side-tracking` not in `~/.claude/skills/` and have no Python agents; critical 2026 channels (Amazon, Consent Mode V2, sGTM/CAPI) | `brain/.claude/skills/` | 🔵 | OPEN |
| A19 | **airllm wrong import path** — `ollama_safe.py:248` does `from core.inference.airllm.airllm_runner import AirLLMRunner` but no `airllm/` subpackage exists; file is at `core/inference/airllm_runner.py`. Crashes on first 70B call. | `core/inference/ollama_safe.py:248` | 🐛 HIGH | OPEN |
| A20 | **airllm `AutoTokenizer` not exported** — `airllm_runner.py:85,190` imports `AutoTokenizer` from `airllm` package; airllm doesn't export this; access via `model.tokenizer` instead. Will crash when `airllm` is pip-installed. | `core/inference/airllm_runner.py:85,190` | 🐛 HIGH | OPEN |
| A21 | **airllm wrong `cache_dir` param** — passes `cache_dir=` to `AutoModel.from_pretrained()` but airllm API uses `layer_shards_saving_path=`. Shards silently land in HF default cache. | `core/inference/airllm_runner.py:94,101,196` | 🐛 MED | OPEN |
| A22 | **airllm commented out in requirements.txt** — `# airllm>=2.10.0` (line 31 comment); it's never installed in fresh venv | `requirements.txt:31` | 🐛 LOW | OPEN (uncomment) |
| A23 | **OpenMythos not installed** — `open-mythos` not in requirements.txt, not pip-installed; `trainer.py` import fails silently. Fix: `pip install open-mythos>=0.5.0` | `requirements.txt` | 🐛 MED | OPEN |
| A24 | **`train.py` is fake** — `core/training/openmythos/train.py` calls `ollama.generate()` in a loop; zero gradient descent. Misleading name alongside real `trainer.py`. Rename to `ollama_modelfile_trainer.py`. | `core/training/openmythos/train.py` | 🐛 LOW | OPEN |
| A25 | **trainer.py wrong OpenMythos repo path** — `trainer.py:37` looks for `GitHub/kyegomez_OpenMythos/repo`; actual path is `GitHub/OpenMythos-main` | `core/training/openmythos/trainer.py:37` | 🐛 LOW | OPEN |
| A26 | **trainer.py MythosTokenizer API mismatch** — calls `.encode(batch)` but it only has `.encode(str)`; batch tokenization will crash at training time | `core/training/openmythos/trainer.py` | 🐛 MED | OPEN |

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

### 16. public-apis-master — DELETE-NOW
| Item | Type | Status |
|---|---|---|
| Curated free-API catalog (this checkout is a gutted partial — README/catalog missing) | — | this dir adds nothing |
| `docs/public_apis.md` = VECTOR's own hand-curated ~50-API district shortlist (NOT derived from repo) | — | ✅ separate |
| `districts/research/api_catalog.py` scans full public-apis README → but source path missing (A7) | 🐛 | OPEN |
**Delete-readiness:** **DELETE-NOW** the audited dir (gutted partial, zero VECTOR references, not the scanner's source path). Separately, A7: fix/restore the catalog source to revive `find_public_api`.

### 17. postiz-app-main — DELETE-AFTER
| Item | Type | Status |
|---|---|---|
| 3 modules absorbed (analytics_retriever, blog_publisher, post_job) — 69 tests | — | ✅ VERIFIED (`69 passed in 1.12s`) |
| A8: export + wire the 3 modules (zero callers today) | 🔵 | OPEN |
| `content_scheduler.py` orchestrator (post_job→publishers→analytics) | 🟢 | OPEN (worth building — user does content) |
| Content-scheduler HUD panel (calendar + composer + analytics) | 🎨 | OPEN (worth building) |
| Missing: persistent scheduling, unified social fan-out, more analytics platforms | 🔵 | OPEN |
**Delete-readiness:** DELETE-AFTER (TS/AGPL repo unused; but wire A8 + build scheduler/panel first — "organs but no body"). Repo is reference for the scheduler UX.

### 21. jcode-master — DELETE-AFTER
| Item | Type | Status |
|---|---|---|
| 5 modules absorbed + wired: AmbientScheduler, SessionPersistence in autonomous_loop.py; multiedit/apply_patch/CacheTracker in coding_tools.py | — | ✅ VERIFIED (grep confirmed wiring) |
| Trajectory auto-compact trigger NOT ported — `StoredCompactionState` field exists but 80%/95% threshold logic missing | 🔵 | OPEN (~60 lines needed in `session_persistence.py`) |
**Delete-readiness:** DELETE-AFTER auto-compact trigger patch. Repo is the reference for that logic.

### 22. openhuman-main — DELETE-AFTER
| Item | Type | Status |
|---|---|---|
| 14/15 claimed items absorbed + verified (OAuthRegistry 119 providers, MemoryTree, TokenJuice, 16 agent roles, ParallelResearcher, telemetry, Sentry, OFP, ElevenLabsTTS…) | — | ✅ VERIFIED (OAuthRegistry.count()=119) |
| "JARVIS dashboard → dashboard/" — FALSE. `dashboard/` doesn't exist. VECTOR's `frontend/` is its own original HUD. | 🐛 doc | corrected |
| `TokenJuice` parity shallow — openhuman has 10-file rule engine with JSON overlays; VECTOR has 263-line hardcoded regex | 🔵 | OPEN (optional upgrade) |
| **Subconscious loop** — cron-driven LLM-vs-situation-report → act/escalate/noop, proactive reflections. No VECTOR equivalent. | 🔵 | OPEN (harvest → chief_of_staff district before delete) |
**Delete-readiness:** DELETE-AFTER harvesting subconscious loop pattern into chief_of_staff. 98.2% claim = overstated (really ~24% of Rust module count, but all Python-portable value absorbed).

### 23. openfang-main — DELETE-NOW + 3 fixes
| Item | Type | Status |
|---|---|---|
| MerkleChain, BudgetMeter, RateLimiter, PromptInjection, SSRF, KnowledgeGraph(105 tests), LoopGuard, VectorSandbox, PeerDiscovery, VectorMigrator, 28 LLM providers, 9 Hands, 5 channel adapters | — | ✅ VERIFIED (all ran live) |
| `OFPNode._init_tls()` — `NameError: _C` (missing `_C = CONFIG` alias) | 🐛 | OPEN (1 line) |
| `TaintTracker.tag()` — TypeError on dict input | 🐛 | OPEN (small) |
| **openfang 5,411-line Alpine.js dashboard NOT absorbed** — 17 panels incl. **Approvals** (human-in-the-loop for YELLOW/RED actions). Critical missing panel. | 🎨 | OPEN — BUILD NOW |
**Delete-readiness:** **DELETE-NOW** (Rust source non-importable by Python; all valuable logic verified in VECTOR). Dashboard must be built regardless (can't import Rust UI). Fix OFPNode + TaintTracker bugs separately.

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
| public-apis | NOW (gutted partial, unused) |
| postiz | after wiring A8 + scheduler/panel |
| jcode | after auto-compact trigger patch (A13) |
| openhuman | after subconscious loop harvest (A17) |
| **openfang** | NOW (Rust non-importable; build Approvals panel separately) |
| AutoHedge | NOW (absorption verified; DO NOT enable live_trading until A10 fixed) |
| nango | NOW (39/40 tests; 1 fail = Windows socket, not code) |
| OpenWA | NOW (50/50 pass, WebhookSigner verified) |
| hermes-agent | NOW (35 channel adapters, all absorbed; save React pages as design ref) |

**Genuinely DELETE-NOW: Understand-Anything, superpowers, skills, Scrapling, LightRAG-clone, public-apis, pocketbase*, mem0-clone, AutoHedge-clone, openfang, nango, OpenWA, hermes-agent (13).** Everything else has pending work.
*pocketbase: 8 failing tests (Windows socket only) — optional conftest.py fix first.
⚠️ AutoHedge: delete clone safely; but keep `live_trading=False` and DO NOT set `SOLANA_PRIVATE_KEY` until A10 gated.

### 18. mem0-main — DELETE-NOW clone + KEEP pip + PATCH
| Item | Type | Status |
|---|---|---|
| 2 VECTOR files correctly use self-hosted `Memory` (Rule 11 compliant) | — | ✅ VERIFIED |
| A9: `MemoryClient` cloud-leak in `vectorcode/src/plugins/memory/mem0/__init__.py:175-176` | 🔴 | OPEN |
| A12: `mem0ai` not pip-installed | 🐛 | OPEN |
**Delete-readiness:** **DELETE-NOW the clone** — VECTOR uses it as a pip dep. PATCH A9+A12.

### 19. AutoHedge-main — DELETE-NOW + PATCH A10
| Item | Type | Status |
|---|---|---|
| 5 agents + Jupiter tools absorbed into `districts/investment/vector_hedgebot/` — all import clean | — | ✅ VERIFIED |
| A10: Solana execution completely ungated (zero permission_gateway calls in vector_hedgebot/) | 🔴 | OPEN |
**Delete-readiness:** **DELETE-NOW the clone** (absorption real). BUT A10 must be patched before enabling live trading. Currently safe only because `live_trading=False` by default — DO NOT set `SOLANA_PRIVATE_KEY` until A10 is fixed.

### 26. OpenCLI-main — PATCH VECTOR
| Item | Type | Status |
|---|---|---|
| `OpenCLIAdapter` instantiates cleanly, fallback HN/GitHub scrapers working | — | ✅ VERIFIED |
| A18: `ResearchHub` crashes on instantiation (`subscribe_to` missing from AgentBase) — silently dead in autonomous loop | 🐛 HIGH | OPEN |
| G2: `research_hub.py:78` calls `self.request_agent_help()` — also missing from AgentBase | 🐛 MED | OPEN |
| G3: No network intercept (fetch/XHR monkey-patch) → can't scrape SPAs (Twitter, LinkedIn, Bilibili) | ❌ | OPEN |
| G4: DOM pruner missing Shadow DOM, iframe, paint-order occlusion, incremental diff | ❌ | OPEN (optional) |
| G5: No article extraction pipeline (Readability + Markdown chunking) | ❌ | OPEN |
| G8: 130+ site adapters (LinkedIn/Amazon/etc.) — TypeScript npm only, no Python equivalent | ❌ | OPEN (needs npm bridge or native port) |
| TypeScript npm bridge (`@jackwener/opencli`) not installed in VECTOR | ⚠️ | OPEN (optional: `npm install @jackwener/opencli`) |
**Delete-readiness:** DELETE-AFTER (fix A18/G2; rest are optional). OpenCLI npm tool can be kept as optional external dep.

### 25. airllm-main — INTEGRATE DIRECTLY (pip dep, delete clone)
| Item | Type | Status |
|---|---|---|
| Layer-streaming 70B inference library — real PyPI package; streams weights layer→GPU→evict; Llama/Qwen/Mistral/Mixtral; 4-bit/8-bit via bitsandbytes | — | ✅ VERIFIED (library is real) |
| A18: wrong import path in `ollama_safe.py:248` (`core.inference.airllm.airllm_runner` → `core.inference.airllm_runner`) | 🐛 HIGH | OPEN |
| A19: `AutoTokenizer` not exported from airllm — use `model.tokenizer` instead | 🐛 HIGH | OPEN |
| A20: `cache_dir=` → `layer_shards_saving_path=` | 🐛 MED | OPEN |
| A21: `airllm>=2.10.0` commented out in requirements.txt | 🐛 LOW | OPEN |
| 4-bit/8-bit compression param not exposed in wrapper | 🔵 | OPEN (optional upgrade) |
**Delete-readiness:** ✅ **DELETE-NOW the clone** — use pip. Fix A18/A19/A20/A21 before enabling.

### 24. OpenMythos-main — INTEGRATE DIRECTLY (pip install)
| Item | Type | Status |
|---|---|---|
| OpenMythos RDT library: real PyPI package (`open-mythos>=0.5.0`), working train.py (DDP/FSDP, FineWeb-Edu, cosine LR) | — | ✅ VERIFIED (1B model runs) |
| `open-mythos` missing from requirements.txt | 🐛 | OPEN — add `open-mythos>=0.5.0` |
| `open_mythos` not pip-installed (ModuleNotFoundError) | 🐛 | OPEN — `pip install open-mythos` |
| `core/training/openmythos/train.py` is a FAKE trainer — calls `ollama.generate()` in a loop, zero gradient descent. Misleading filename. | 🐛 HIGH | OPEN — either delete or rename to `ollama_modelfile_trainer.py` |
| `trainer.py:37` wrong repo path `GitHub/kyegomez_OpenMythos/repo` (should be `GitHub/OpenMythos-main`) | 🐛 | OPEN |
| `trainer.py` calls `MythosTokenizer` as batch tokenizer but it only has `.encode(str)` — will crash at training time | 🐛 MED | OPEN |
**Delete-readiness:** KEEP as pip dependency. Fix G1/G2/G3/G4/G5. `pip install open-mythos` replaces the clone.

### 20. pocketbase-master — DELETE-NOW (after 1-line conftest fix)
| Item | Type | Status |
|---|---|---|
| 47/55 passed (8 fail = Windows socket exhaustion, not logic); CollectionEngine OK | — | ✅ VERIFIED |
| A11: `asyncio.WindowsSelectorEventLoopPolicy()` in conftest.py | 🐛 LOW | OPEN |
| Realtime SSE, MFA/OTP, admin UI — not reimplemented (not needed for single-owner) | — | by design |
**Delete-readiness:** **DELETE-NOW** (all needed features absorbed and working). Optional: fix A11 for clean test suite first.

---

## D. Audit progress
- Batch 1 ✅: voicebox, Vibe-Trading, Vane
- Batch 2 ✅: ui-ux-pro-max-skill, valuecell, Understand-Anything
- Batch 3 ✅: UI-TARS, TradingAgents, system_prompts_leaks
- Batch 4 ✅: superpowers, skills, Scrapling
- Batch 5 ✅: ruflo, LightRAG, RAG-Anything
- Batch 6 ✅: public-apis, postiz
- Batch 7 ✅: mem0, AutoHedge, pocketbase
- Batch 8 ✅: jcode, openhuman, openfang
- Batch 9 ✅: nango, OpenWA, hermes-agent
- Batch 10 ⏳: OpenCLI, OpenMythos, airllm (in progress)
- Batch 11 ⏳: obsidian-mind, claude-ads, FinceptTerminal (in progress)
- Batch 12+: ECC, GitNexus, AI-Trader, ai-financial-agent, daily_stock_analysis → then frontend repos → then skill-collections → then MCP/tooling
- **Rule: finish auditing ALL repos → then fix/harvest/delete in one pass.**
- **26 repos audited; 50 remain. ~76 total.**

## E. Remaining repo queue (~50)
### Priority 1 — prior-absorption verify (running or queued)
- ⏳ OpenCLI, OpenMythos, airllm (batch 10)
- ⏳ obsidian-mind, claude-ads, FinceptTerminal (batch 11)
- ⬜ ECC, GitNexus, AI-Trader, ai-financial-agent, daily_stock_analysis

### Priority 2 — repos with own frontend (panel candidates)
- ⬜ open-webui, LibreChat, ComfyUI-master, ComfyUI-Manager
- ⬜ openclaude, openclaw, mistral-vibe, ai-website-cloner
- ⬜ glif-mcp, NotFair, iii, hyperframes

### Priority 3 — skill/data collections (quick DELETE-NOW candidates)
- ⬜ agent-skills, awesome-agent-skills, awesome-claude-skills, awesome-skills
- ⬜ andrej-karpathy-skills, Anthropic-Cybersecurity-Skills, obsidian-skills, gsap-skills, open-skills

### Priority 4 — MCP/tooling/infra
- ⬜ fastmcp, modelcontextprotocol, playwright-mcp, firecrawl-mcp
- ⬜ ClawRouter, codebuff, get-shit-done, humanlayer, markitdown
- ⬜ camel, camofox-browser, autoresearch, agentic-inbox, Open-Generative-AI

### Uncategorized
- ⬜ agency-agents, code-review-graph, gstack, karpathy-main, llm-council-master
