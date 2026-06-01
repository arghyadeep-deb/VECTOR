# VECTOR Repo-Audit MASTER TRACKER

Single source of truth for every gap, bug, patch, integration, and delete-decision
across all audited repos. Nothing gets fixed or deleted until ALL repos are audited.

## RULE UPDATE — 2026-06-01 (FINAL)
**Three-way decision for every absorbed or pending repo:**

| Situation | Action |
|-----------|--------|
| Python absorption **works well** (verified running, no stubs) | ✅ Keep Python version. Done. |
| Python absorption **broken/stub/wrong** | ❌ Delete the broken Python code. Integrate the **original** repo directly (compile binary / npm install / run as sidecar). |
| Feature **skipped** because "can't convert from other language" | 🟢 Now integrate the original directly — don't skip anymore. |

**How to integrate non-Python repos locally:**
- **Rust/Go/C++ binary** → `cargo build --release` / `go build`, call via `asyncio.create_subprocess_exec`, run as sidecar
- **Node.js / TypeScript service** → `npm install && node dist/`, call via HTTP/WS from VECTOR's FastAPI
- **Electron app** → launch as child process, control via IPC or Playwright CDP  
- **npm CLI tool** → `npm install -g <tool>`, thin Python subprocess wrapper
- **Python lib with bugs** → fix the bugs (it's already Python, just broken)

**NOT in scope:** External cloud services that need API keys — that's a different concern. This rule is about **local services in the repos you already have on disk**.

If the original non-Python version is **better than the Python port** AND the Python port has bugs → replace the broken Python port with a proper integration of the original.

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
| A12 | mem0 (`mem0ai`) not pip-installed — fixed, now active in requirements.txt | `requirements.txt` | 🐛 MED | ✅ FIXED |
| A13 | jcode: trajectory auto-compact trigger missing — `StoredCompactionState` field exists but 80%/95% threshold logic not ported | `core/jcode/session_persistence.py` | 🔵 | OPEN (~60 lines from jcode-master reference) |
| A14 | openfang `OFPNode._init_tls()` `NameError: _C` — needs `_C = CONFIG` alias | `core/network/ofp_protocol.py` | 🐛 LOW | OPEN (1 line) |
| A15 | openfang `TaintTracker.tag()` TypeError on dict label input | `core/security/taint_tracker.py` | 🐛 LOW | OPEN |
| A16 | 🎨 openfang Approvals dashboard (5,411-line Alpine.js, 17 panels) not absorbed — especially the **Approvals panel** (human-in-loop for YELLOW/RED actions). No VECTOR equivalent. Build as HUD panel. | `frontend/` | 🎨 HIGH | OPEN — BUILD NOW |
| A17 | openhuman subconscious loop pattern not harvested — cron LLM-vs-situation-report → act/escalate/noop, proactive reflections | `districts/chief_of_staff/` | 🔵 | OPEN (harvest before deleting repo) |
| ~~A?~~ | ~~agent_base.py:56 CONFIG[models][focus] crash~~ — **DISPROVEN**: returns 'vector-focus' fine, not a bug (ruflo agent was wrong; likely saw socket-exhaustion error) | — | — | NOT A BUG |
| A18 | **`subscribe_to` missing from AgentBase — systemic crash on 4+ agents** — LLMCouncil (governance!), ResearchHub, ConsolidationBot all crash at `__init__`. Fixed: added `def subscribe_to(self, event_type: str): pass` to `core/city/agent_base.py`. Verified: all 3 now instantiate. | `core/city/agent_base.py` | 🐛 CRITICAL | ✅ FIXED |
| A27 | **ZKSteward wrong vault path** — resolves to `C:\Users\Arghyadeep\V.E.C.T.O.R Brain` (doesn't exist); correct path is `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain`. Every `scan_vault_notes()` call silently returns 0. | `districts/personal_growth/zk_steward.py:32` | 🐛 HIGH | OPEN |
| A28 | **Brain vault hooks never fire** — `.claude/settings.json` missing from Brain vault; all 5 lifecycle hooks (SessionStart, UserPromptSubmit, PostToolUse, PreCompact, Stop) are dead | `brain/.claude/settings.json` | 🐛 HIGH | OPEN |
| A29 | **AdsOrchestrator runs platforms sequentially** — `for platform in platforms:` loop instead of `asyncio.gather()` → misses parallel-audit performance target | `districts/marketing/ads/ads_orchestrator.py` | 🐛 MED | OPEN |
| A30 | **No `AdsScorer` class** — weighted scoring formula exists only in reference .md, not as testable Python code | `districts/marketing/` | 🔵 | OPEN |
| A32 | **Communications district crashes on import** — `__init__.py` imports `StyleModel` and `CommunicationsAdapter` which don't exist; entire district broken until fix. Fixed: removed dead imports. | `districts/communications/__init__.py` | 🐛 CRITICAL | ✅ FIXED |
| A33 | **`_FINCEPT_BASE` wrong path** — `finagent_agent.py:27` resolves to `parent.parent.parent.parent / "core" / "vector_finagent"` (points outside repo). Correct: `Path(__file__).parent / "vector_finagent"`. Investor persona config loading fails silently. | `districts/investment/finagent_agent.py:27` | 🐛 HIGH | OPEN |
| A33 | **FinceptTerminal investor personas hardcoded to OpenAI** — 7 AI personas (Buffett, Graham, Lynch, etc.) call OpenAI API directly instead of routing via `provider_client.py` (VECTOR Rule: all LLM calls must use provider_client, Ollama-first) | `districts/investment/vector_finagent/agents/` | 🐛 HIGH | OPEN |
| A34 | **1,423 analytics scripts not Governor-routable** — `vector_finagent/` scripts exist but only 7 routes wired to Governor; remaining scripts unreachable from autonomous loop | `districts/investment/vector_finagent/` | 🔵 | OPEN |
| A35 | **743 cybersecurity skills uninstalled** — `Anthropic-Cybersecurity-Skills-main` has 754 SKILL.md files; only 11 in brain; 743 not yet installed. Also has MITRE ATT&CK Navigator JSON, NIST CSF mappings, OWASP maps → valuable for ThreatScout/MalwareHunter grounding | `brain/.claude/skills/` + `districts/security/data/` | 🔵 harvest | OPEN |
| A31 | **Ads Wave 2 sub-skills not installed** — `ads-amazon`, `ads-attribution`, `ads-server-side-tracking` not in `~/.claude/skills/` and have no Python agents; critical 2026 channels (Amazon, Consent Mode V2, sGTM/CAPI) | `brain/.claude/skills/` | 🔵 | OPEN |
| A19 | **airllm wrong import path** — `ollama_safe.py:248` does `from core.inference.airllm.airllm_runner import AirLLMRunner` but no `airllm/` subpackage exists; file is at `core/inference/airllm_runner.py`. Crashes on first 70B call. | `core/inference/ollama_safe.py:248` | 🐛 HIGH | OPEN |
| A20 | **airllm `AutoTokenizer` not exported** — `airllm_runner.py:85,190` imports `AutoTokenizer` from `airllm` package; airllm doesn't export this; access via `model.tokenizer` instead. Will crash when `airllm` is pip-installed. | `core/inference/airllm_runner.py:85,190` | 🐛 HIGH | OPEN |
| A21 | **airllm wrong `cache_dir` param** — passes `cache_dir=` to `AutoModel.from_pretrained()` but airllm API uses `layer_shards_saving_path=`. Shards silently land in HF default cache. | `core/inference/airllm_runner.py:94,101,196` | 🐛 MED | OPEN |
| A22 | **airllm in requirements.txt** — fixed, now active | `requirements.txt:31` | 🐛 LOW | ✅ FIXED |
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

### 7. UI-TARS-desktop-main — INTEGRATE (multi-language rule)
| Item | Type | Status |
|---|---|---|
| `core/vision_control/` port + visual grounding | — | ✅ VERIFIED (exists, grounding real) |
| **REVISED (multi-language rule):** UI-TARS Electron app can be run as sidecar for full VLM grounding + phone operator; no need to rewrite in Python | 🟢 | OPEN |
| Electron desktop app → run via `subprocess` / Playwright bridge | 🟢 | OPEN (integrate, not rewrite) |
**Delete-readiness:** KEEP — integrate the Electron app directly as a PC control sidecar.

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

### 37. Web-Tools Batch (5 repos)
| Repo | Verdict | Action | Priority |
|---|---|---|---|
| ai-website-cloner-template-master | INTEGRATE | Install `/clone-website` skill into `~/.claude/skills/`; add `extract_design_tokens()` to `dom_pruner.py` | MED |
| glif-mcp-server-main | INTEGRATE | Build + add to `.mcp.json` as MCP sidecar; `GLIF_API_TOKEN` in `.env` | MED |
| **NotFair-main** | **INTEGRATE + PATCH** | Wire `NotFair-GoogleAds` + `NotFair-MetaAds` remote MCP servers; build `geo_optimizer_agent.py`; expand SEO router | HIGH |
| iii-main | DELETE engine / PATCH SDK | Harvest Python SDK trigger patterns → `core/event_bus/`; do NOT run Rust engine | LOW |
| **hyperframes-main** | **INTEGRATE + PATCH** | Build producer sidecar on port 7421; add `render_via_hyperframes()` to `vector_composer.py`; install skills | HIGH |

**Key gaps (W-series):**
| # | Issue | Location | Priority |
|---|---|---|---|
| W5 | Add NotFair-GoogleAds + NotFair-MetaAds remote MCP servers to `.mcp.json` | `.mcp.json` | HIGH |
| W9 | Build `geo_optimizer_agent.py` — GEO score 0-100 for ChatGPT/Claude/Perplexity/Gemini citation | `districts/marketing/` | HIGH (2026 traffic) |
| W10 | Expand `seo.py` from 1-endpoint stub to full router | `core/api/routers/seo.py` | MED |
| W13 | Build `@hyperframes/producer` sidecar on port 7421 | `run_vector.py` | HIGH |
| W14 | `render_via_hyperframes()` in `vector_composer.py` with fallback to `html_renderer.py` | `core/video/` | HIGH |
| W1-W4, W6-W8, W11-W12, W15-W17 | See `web-tools-batch.md` for full list | various | MED/LOW |

### 36. Frontend-UI Batch (5 repos)
| Repo | Verdict | Action |
|---|---|---|
| **ComfyUI-master** | INTEGRATE DIRECTLY | `comfyui_adapter.py` ✅ working; gap: no auto-start sidecar; add to `run_vector.py` / `install_service.ps1` on port 8188 |
| ComfyUI-Manager-main | INTEGRATE DIRECTLY | `git clone` into `ComfyUI/custom_nodes/` — zero VECTOR code change; gives browser UI for 1,400+ custom nodes |
| openclaude-main | ✅ DELETE-NOW | TypeScript Claude Code fork; VECTOR's 27-provider + MoE routing + ReasoningBank is strictly more capable |
| openclaw-main | PATCH VECTOR | 2 gaps: `ImageGenProviderRegistry`/`VideoGenProviderRegistry` (VECTOR hardcodes ComfyUI/SadTalker) + per-channel DM security policy (pairing codes, allowlists) |
| mistral-vibe-main | PATCH VECTOR | 3 gaps: `ask_user_question` tool (structured multi-option in-task questions); tree-sitter bash AST safety guard; named permission profiles (plan/accept-edits/auto-approve → GREEN/YELLOW/RED) |

**Gaps:**
| # | Issue | Location | Type | Status |
|---|---|---|---|---|
| A41 | ComfyUI not auto-started as sidecar — adapter ready but ComfyUI process not launched by VECTOR | `run_vector.py` / `scripts/install_service.ps1` | 🔵 | OPEN |
| A42 | No image/video gen provider registry — hardcoded ComfyUI/SadTalker; no cloud fallback (Replicate, Stability, etc.) | `districts/content/` | 🔵 | OPEN |
| A43 | No `ask_user_question` tool — VECTOR can't ask structured multi-option questions mid-task | `core/mcp_server.py` | 🔵 | OPEN |
| A44 | No tree-sitter bash AST safety guard — bash commands checked by LLM-based injection scanner only; no deterministic AST analysis | `core/loop/permission_gateway.py` | 🐛 MED | OPEN |

### 35. Tooling Batch (5 repos)
| Repo | Verdict | Action |
|---|---|---|
| codebuff-main | ✅ DELETE-NOW | Full parity: `core/code_conductor/` is Python port (code_map.py, orchestrator.py, etc.) |
| get-shit-done-main | ✅ DELETE-NOW | Archived repo; VECTOR has `vectorcode/src/gsd_loop.py` + brain commands |
| humanlayer-main | PATCH (low) | SDK already wired to `permission_gateway.py`; repo pivoted to Go daemon. Build `core/engine/approval_daemon.py` (~80 LOC) to eliminate 30s timeout fallback |
| **markitdown-main** | INTEGRATE (already used) | Uncomment `markitdown[all]>=0.0.1` in requirements.txt; add `convert_to_markdown` MCP tool |
| **code-review-graph-main** | INTEGRATE (enhance adapter) | `districts/coding/code_review_graph/__init__.py` exists but: 3 functions not exposed as MCP tools; no watch-mode trigger; refactor analysis not wired |

**Gaps:**
| # | Issue | Location | Type | Status |
|---|---|---|---|---|
| A39 | `markitdown` commented out in requirements.txt — used in production but won't install in fresh venv | `requirements.txt:27` | 🐛 MED | OPEN |
| A40 | code-review-graph functions not in MCP — adapter exists but `analyze_graph`, `get_refactor_suggestions`, `watch_mode` not exposed as MCP tools | `core/mcp_server.py` | 🔵 | OPEN |

### 34. MCP/Infra Batch (5 repos)
| Repo | Verdict | Action |
|---|---|---|
| fastmcp-main | ✅ DELETE-NOW | pip package v3.2.4 already installed, VECTOR uses it |
| modelcontextprotocol-main | DELETE-AFTER | Actually Perplexity MCP — add 4 tools (search/ask/research/reason) to `core/mcp_server.py` as thin wrapper |
| **playwright-mcp-main** | **INTEGRATE DIRECTLY** | `npx @playwright/mcp@latest --headless --port 8931` sidecar; 25+ browser tools (navigate, click, type, snapshot); wire to `core/browser/` |
| **firecrawl-mcp-server-main** | **INTEGRATE DIRECTLY** | 15 tools: structured scrape, recursive crawl, URL discovery, LLM extraction, autonomous research agent; fills WebScout's DuckDuckGo-only gap; wire to `districts/research/` |
| ClawRouter-main | PATCH CONFIG | `npx @blockrun/clawrouter` — 10 free NVIDIA models (no key), 55+ paid; add to `core/config.py` as Ollama fallback |

**Gaps from this batch:**
| # | Issue | Location | Type | Status |
|---|---|---|---|---|
| A36 | No structured web extraction — `WebScout` only parses DDG HTML; no full-page extraction, no LLM extraction, no recursive crawl | `districts/research/web_scout.py` | 🟢 integrate | OPEN — wire firecrawl-mcp |
| A37 | Playwright MCP not running — 25+ browser automation tools available via `npx @playwright/mcp` but not wired to VECTOR's autonomous loop | `core/mcp_server.py` | 🟢 integrate | OPEN |
| A38 | No zero-cost LLM fallback beyond Ollama — ClawRouter provides 10 free NVIDIA models as `http://localhost:8787` OpenAI-compat endpoint | `core/config.py` | 🔵 patch | OPEN |

### 32. ECC-main — SAFE TO DELETE (3 targeted extractions first)
| Item | Status |
|---|---|
| 63 agents, 249 skills, 47 hooks — Claude Code harness plugin, not VECTOR-relevant Python | — |
| VECTOR already has 371 brain skills > ECC's 249 | ✅ |
| Copy 8 language-reviewer agents to `brain/.claude/agents/` (python-reviewer, fastapi-reviewer, go-reviewer, rust-reviewer, typescript-reviewer, silent-failure-hunter, tdd-guide, harness-optimizer) | 🔵 OPEN |
| Port 2 Python hooks (~30 lines each): SessionStart context injection + compact-suggestion at 40 tool calls | 🔵 OPEN |
| Continuous learning v2 instinct pipeline → defer Year 2 | — |
**Delete-readiness:** DELETE-AFTER copying 8 agent .md files + writing 2 hooks.

### 33. AI-Trader-main — INTEGRATE AS AGENT (don't absorb code)
| Item | Status |
|---|---|
| StockAnalyst, TechnicalBot, FundamentalsBot, SentimentBot — all ✅ verified | ✅ |
| AI-Trader is a **hosted social paper-trading network** at ai4trade.ai — not local code to absorb | — |
| VECTOR should **register as an agent** at ai4trade.ai for community leaderboard/copy-trading | 🟢 OPEN |
| Market hours gate (`is_market_open()` with ZoneInfo ET) — VECTOR lacks this | 🔵 OPEN |
| Alpha Vantage NEWS_SENTIMENT structured snapshot (ETF flows, macro signals) | 🔵 OPEN (low) |
| Leaderboard recharts pattern for future `dashboard/src/` | 🔵 OPEN (low, when dashboard built) |
| Copy-trading / challenges / team missions → single-user VECTOR doesn't need this | — skip |
**Delete-readiness:** DELETE-AFTER registering VECTOR as agent + porting market hours gate.

### 30. Skill-Collections Batch (6 repos) — DELETE-NOW
| Repo | Verdict | Notes |
|---|---|---|
| agent-skills-main | ✅ DELETE-NOW | 23 addyosmani skills already in brain |
| awesome-agent-skills-main | ✅ DELETE-NOW | Index-only, zero content |
| awesome-claude-skills-master | ✅ DELETE-NOW | 27 Composio skills already in brain |
| awesome-skills-main | ✅ DELETE-NOW | 371 skills already in brain |
| andrej-karpathy-skills-main | ✅ DELETE-NOW | Karpathy curriculum already in brain |
| obsidian-skills-main | ✅ DELETE-NOW | 5 skills already in brain |
| **Anthropic-Cybersecurity-Skills-main** | **KEEP → HARVEST** | 754 skills (743 not yet installed) + MITRE ATT&CK/NIST CSF/OWASP Navigator JSON maps |
**Action:** Copy 743 uninstalled skills → `brain/.claude/skills/`; copy `mappings/` → `districts/security/data/` for ThreatScout/MalwareHunter.

### 29. FinceptTerminal-main — PATCH (absorbed, critical path bug)
| Item | Type | Status |
|---|---|---|
| 361 analytics scripts in `districts/investment/vector_finagent/` (1:1 mirror of 360 FinceptTerminal entries) | — | ✅ VERIFIED (directory confirmed) |
| FinAgentAgent, BacktestAgent, HedgeBotAgent, FundamentalsBot, TechnicalBot, SentimentBot all instantiate | — | ✅ VERIFIED |
| A32: `_FINCEPT_BASE` wrong path — resolves outside repo; investor persona config loading silently fails | 🐛 HIGH | OPEN |
| A33: Investor personas (Buffett/Graham/Lynch/etc.) hardcoded to OpenAI instead of `provider_client.py` | 🐛 HIGH | OPEN |
| A34: 1,423 analytics scripts present but only 7 routes wired to Governor | 🔵 | OPEN |
| No absorption tests exist for the 1,423 scripts | 🔵 | OPEN |
| Qt C++ build incomplete (no .exe produced) — not needed for autonomous VECTOR | — | by design |
**Delete-readiness:** DELETE-AFTER (fix A32/A33; build absorption tests; repo has the analytics scripts and Qt UI as reference).

### 27. claude-ads-main — PATCH (mostly done)
| Item | Type | Status |
|---|---|---|
| Core Python agents instantiate: AdsOrchestratorAgent, GoogleAdsAgent, MetaAdsAgent, SEOSpecialist, CompetitorIntelAgent, CROAgent | — | ✅ VERIFIED |
| 13/22 command routes covered autonomously; 25/26 reference files + 12 industry templates present | — | ✅ VERIFIED |
| A29: AdsOrchestrator runs platforms sequentially instead of `asyncio.gather()` | 🐛 | OPEN |
| A30: No `AdsScorer` Python class (scoring formula is markdown-only) | 🔵 | OPEN |
| A31: Wave 2 sub-skills (ads-amazon, ads-attribution, ads-server-side-tracking) not installed/built | 🔵 | OPEN |
| Zero pytest coverage for ads routing/scoring | 🔵 | OPEN |
**Delete-readiness:** DELETE-NOW (Claude Code skill repo — its Python value is in VECTOR as districts/marketing/; skill .md files are in ~/.claude/skills/; repo is redundant). Fix A29/A30/A31 in VECTOR separately.

### 28. obsidian-mind-main — PATCH (70% done)
| Item | Type | Status |
|---|---|---|
| ZKSteward, PatternFinder, JournalWriter, ObsidianSync — all real working Python agents | — | ✅ VERIFIED |
| A18 (systemic): ConsolidationBot crashes on `self.subscribe_to("memory_stored")` | 🐛 CRITICAL | OPEN |
| A27: ZKSteward vault path wrong → 0 notes returned | 🐛 HIGH | OPEN |
| A28: Brain vault `.claude/settings.json` missing → all 5 lifecycle hooks dead | 🐛 HIGH | OPEN |
| 12/18 obsidian-mind slash commands missing from Brain vault | 🔵 | OPEN |
**Delete-readiness:** DELETE-AFTER (fix A18/A27/A28; install missing 12 commands). Repo is the reference for command content.

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
| TypeScript npm bridge (`@jackwener/opencli`) not installed — **multi-language rule: just install it** | 🟢 | OPEN (`npm install -g @jackwener/opencli`, wire via subprocess) |
| G3: Network intercept for SPAs — integrate npm tool directly instead of reimplementing | 🟢 | OPEN |
**Delete-readiness:** DELETE-AFTER (fix A18/G2 + wire npm tool). Rule changed: no need to reimplement 130+ site adapters in Python.

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

### 30. open-webui-main — INTEGRATE DIRECTLY
| Item | Type | Status |
|---|---|---|
| SvelteKit + Python FastAPI (uvicorn) — run on port 8080 | 🟢 | OPEN (run `pip install -e backend/ && uvicorn open_webui.main:app --port 8080`) |
| Proxy via HUD "KNOWLEDGE" iframe button | 🎨 | OPEN |
| Wire Ollama: `OLLAMA_BASE_URL=http://localhost:11434` already default | — | ready |
| RAG pipeline: VECTOR agents call `POST http://localhost:8080/api/chat/completions` to leverage knowledge bases | 🟢 | OPEN |
| G1: No conversation-level RAG in VECTOR | ❌ | filled by Open WebUI |
| G2: No model evaluation leaderboard | ❌ | filled by Open WebUI evaluations |
| G3: No prompt library UI | ❌ | filled by Open WebUI workspace/prompts |
| G4: No in-UI Ollama model management | — | filled by Open WebUI workspace/models |
| G5: `get_vault_context` missing (pre-existing A6) | 🐛 | still OPEN in VECTOR core |
**Delete-readiness:** KEEP — run as sidecar service. Do not copy backend into VECTOR.

### 31. LibreChat-main — INTEGRATE DIRECTLY
| Item | Type | Status |
|---|---|---|
| Node.js/Express + React — run on port 3080 | 🟢 | OPEN (MongoDB Docker + `node api/server/index.js`) |
| Wire to Ollama + VECTOR API keys in `librechat.yaml` | 🟢 | OPEN |
| Wire VECTOR MCP server (`http://localhost:8765`) as LibreChat MCP server — exposes all 14+ VECTOR tools in chat | 🟢 | HIGH VALUE |
| Proxy via HUD "CHAT" iframe button | 🎨 | OPEN |
| G1: No in-chat Artifacts sandbox (live React/HTML) | ❌ | filled by LibreChat |
| G2: No chain-of-thought display UI | ❌ | filled by LibreChat Reasoning UI |
| G3: No conversation branching | ❌ | filled by LibreChat fork feature |
| G4: No prompt library | ❌ | filled by LibreChat |
| G5: No conversation search | ❌ | filled by LibreChat |
| G6: No dynamic MCP server management | ❌ | filled by LibreChat MCP config |
| MongoDB required: `docker run -d -p 27017:27017 mongo` | dep | OPEN |
**Delete-readiness:** KEEP — run as sidecar service. Do not port Node.js to Python.


### 35. Web-Tools Batch (5 repos) — 2026-06-01
| Repo | Verdict | Notes |
|------|---------|-------|
| `ai-website-cloner-template-master` | INTEGRATE DIRECTLY | Install `/clone-website` skill into `~/.claude/skills/`. No Python needed. Uses existing Playwright MCP. |
| `glif-mcp-server-main` | INTEGRATE DIRECTLY | `npm install && npm run build`, add to `.mcp.json` as Node.js MCP sidecar. Add `GLIF_API_TOKEN` to `.env`. |
| `NotFair-main` | INTEGRATE DIRECTLY + PATCH VECTOR | `/plugin install notfair@nowork-studio`; wire `NotFair-GoogleAds` + `NotFair-MetaAds` remote MCP servers; absorb policy rules into Python agents. |
| `iii-main` | SAFE TO DELETE (engine) + harvest SDK patterns | Do not run Rust engine. Harvest `TriggerHandler`/`TriggerConfig` into `core/event_bus/` (W11). |
| `hyperframes-main` | INTEGRATE DIRECTLY + PATCH VECTOR | Run `@hyperframes/producer` sidecar on port 7421. Install skills. Wire as fallback render backend. |

**Gaps (W-series):**
| # | Issue | Location | Type | Status |
|---|---|---|---|---|
| W1 | Install `/clone-website` skill | `~/.claude/skills/clone-website/` | 🟢 | OPEN |
| W2 | Add `extract_design_tokens(url)` to `core/browser/dom_pruner.py` | `core/browser/dom_pruner.py` | 🔵 | OPEN |
| W3 | Build glif-mcp-server + add to `.mcp.json` + `GLIF_API_TOKEN` in `.env` | `.mcp.json` | 🟢 | OPEN |
| W4 | `districts/content/glif_workflow_agent.py` — glif MCP wrapper | `districts/content/` | 🔵 | OPEN |
| W5 | Add NotFair-GoogleAds + NotFair-MetaAds to `.mcp.json` | `.mcp.json` | 🟢 | OPEN |
| W6 | Install NotFair plugin skills into `brain/.claude/skills/notfair/` | `brain/.claude/skills/` | 🟢 | OPEN |
| W7 | Extend `google_ads_agent.py`: GAQL fan-out + change-event + business-context.json | `districts/marketing/google_ads_agent.py` | 🔵 | OPEN |
| W8 | Extend `meta_ads_agent.py`: Learning Phase + frequency fatigue + CBO/ABO/Advantage+ | `districts/marketing/meta_ads_agent.py` | 🔵 | OPEN |
| W9 | Build `geo_optimizer_agent.py` — GEO score 0-100 for AI search citation (net-new) | `districts/marketing/` | 🟢 new | OPEN |
| W10 | Expand `core/api/routers/seo.py` stub to full action router | `core/api/routers/seo.py` | 🔵 | OPEN |
| W11 | Harvest iii-SDK trigger abstractions into `core/event_bus/` | `core/event_bus/` | 🔵 | OPEN |
| W12 | Add unit tests for `core/loop/cron_jobs.py` | `tests/test_cron_jobs.py` | 🔵 | OPEN |
| W13 | Build `@hyperframes/producer` + add sidecar startup on port 7421 | `run_vector.py` | 🟢 | OPEN |
| W14 | Add `render_via_hyperframes()` to `core/video/vector_composer.py` | `core/video/vector_composer.py` | 🔵 | OPEN |
| W15 | Install hyperframes skills (`npx skills add heygen-com/hyperframes`) | `~/.claude/skills/` | 🟢 | OPEN |
| W16 | Harvest chunk-based streaming encode from hyperframes `chunkEncoder.ts` | `core/video/video_encoder.py` | 🔵 | OPEN |
| W17 | Add extraction cache to `core/video/html_renderer.py` | `core/video/html_renderer.py` | 🔵 | OPEN |

**Delete-readiness:** ai-website-cloner KEEP · glif-mcp KEEP · NotFair KEEP · iii DELETE-AFTER W11/W12 · hyperframes KEEP

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
- Batch 10 ✅: OpenCLI, OpenMythos, airllm
- Batch 11 ✅: obsidian-mind, claude-ads, FinceptTerminal
- Batch 12 ⏳: ECC, GitNexus, AI-Trader
- Batch 13 ⏳: ai-financial-agent, daily_stock_analysis
- Batch 14 ✅: open-webui (INTEGRATE DIRECTLY, port 8080), LibreChat (INTEGRATE DIRECTLY, port 3080)
- Batch 15 ⏳: skill-collections (7 repos), misc-collections (6 repos)
- Batch 16 ⏳: frontend-ui (ComfyUI×2, openclaude, openclaw, mistral-vibe)
- Batch 17 ✅: web-tools (ai-website-cloner, glif-mcp, NotFair, iii, hyperframes) — see Section 35
- Batch 18 ⏳: MCP-infra (fastmcp, modelcontextprotocol, playwright-mcp, firecrawl-mcp, ClawRouter)
- Batch 19 ⏳: tooling (codebuff, get-shit-done, humanlayer, markitdown, code-review-graph)
- Batch 20 ⏳: AI-agents (camel, camofox, autoresearch, agentic-inbox, Open-Generative-AI)
- **ALL ~76 repos now assigned to agents. Awaiting results.**
- **Rule: finish auditing ALL repos → then fix/harvest/delete in one pass.**
- **32 audited + 44 in-flight = 76 total.**
