# Unresolved System Questions

**Purpose:** Every important question that remains unclear after the audit  
**Level:** System Level (Level 1)  
**Created:** 2026-08-12  
**Last Updated:** 2026-08-13 (4 questions resolved by cognitive integration audit)

---

## Overview

This document catalogs every significant unresolved question about VECTOR's runtime behavior, architecture, and operational characteristics discovered during the audit. Each question includes what was checked, what is known, what is unknown, and how to verify.

**Categories:**
- **Runtime Paths** — unclear execution flows and initialization order
- **Dead vs Dynamic Code** — code that appears unused but may be dynamically invoked
- **Configuration-Dependent Behavior** — behavior that changes based on env/config in undocumented ways
- **Provider Quota Ambiguity** — free-tier limits that are unclear or unverified
- **Memory Subsystem Ambiguity** — memory layers with unclear interactions
- **Agent Reachability** — agents/districts that may not be reachable via governor routing
- **Undocumented Side Effects** — behaviors discovered but not documented
- **Race Conditions** — concurrency hazards in async/sync boundary code

---

## 1. Runtime Paths

---

### Q1.1: What is the actual initialization order of autonomous_loop coroutines?

**WHY IT MATTERS:** If coroutines start before their dependencies are initialized, silent failures occur. The observe loop senses (screen, face, sound) but those components need GPU/library initialization. A race at startup could mean the first N observe ticks silently fail with no visible error beyond loguru warnings.

**WHAT WAS CHECKED:** `run_vector.py` CLI entry, `autonomous_loop.py` `run_forever()` method, `bootstrap_agents()` call.

**WHAT IS KNOWN:** `run_forever()` calls `asyncio.gather()` on 4 coroutines (observe, think, act, reflect). `bootstrap_agents()` is called inside `run_loop()`. Each coroutine has exception handling that logs and retries with 5s backoff.

**WHAT IS UNKNOWN:** Whether `bootstrap_agents()` completes before the observe loop's first tick attempts to use FaceDetector/ScreenObserver/SoundClassifier. The `asyncio.gather()` starts all 4 concurrently — if observe's first tick is faster than agent bootstrap, the first few sense results will be neutral/empty. No startup synchronization barrier exists.

**HOW TO VERIFY:** Add a startup probe: log timestamps at each initialization step and compare. Check if `_sense_tick()` guards against None-type component references. Run `python run_vector.py loop` and examine the first 30s of logs for component-initialization ordering.

---

### Q1.2: Does `context_engine.session_hydration_prompt()` always complete before the first LLM call in each coroutine?

**STATUS: ⚠️ PARTIALLY RESOLVED (2026-08-13 audit)**

**WHY IT MATTERS:** RULE 1 states session_hydration_prompt() must precede EVERY LLM call. If any district agent makes an LLM call before the context engine is initialized, that call runs with amnesia — violating the core invariant.

**WHAT WAS CHECKED:** `context_engine.py`, `provider_client.py`, `district_llm.py`, `vectorcode_llm.py`.

**WHAT IS KNOWN (corrected by audit):**
- `provider_client.chat()` does NOT call `session_hydration_prompt()` internally — hydration is **caller-responsible**
- `vectorcode_llm.chat()` also does NOT call hydration internally
- 85 files reference `session_hydration_prompt` — callers handle it explicitly
- `district_llm.py` loads the district's `.md` system prompt and calls `vectorcode_llm.chat()` — must handle hydration at district level
- The context engine lazily initializes `_memory` and `_goals` on first use

**WHAT IS STILL UNKNOWN:** Whether district agents that bypass `district_llm.py` and call `provider_client.py` or `ollama_safe.py` directly still get hydration. Some agents (e.g., in the investment district's `vector_finagent`, `vector_hedgebot` subdirectories) may use their own LLM calling patterns from absorbed repos that skip hydration entirely.

**HOW TO VERIFY:** Grep all `districts/` for direct `httpx.post` calls to LLM endpoints, direct `ollama` imports, or `openai.Anthropic()` calls that bypass `provider_client.py`. Each such call is a RULE 1 violation candidate.

---

### Q1.3: What happens when `run_vector.py loop` starts but Ollama is not running?

**WHY IT MATTERS:** Ollama is the terminal fallback for every LLM call chain. If Ollama is down AND cloud keys are exhausted/unconfigured, the system should degrade gracefully. But the exact failure mode is unclear — does it enter a retry loop, or does it crash the think coroutine?

**WHAT WAS CHECKED:** `ollama_safe.py`, `provider_client.py`, `route_policy.py`.

**WHAT IS KNOWN:** `ollama_safe.py` wraps Ollama calls with error handling. `route_policy.py` always includes `ollama` as the final fallback. The autonomous loop catches all exceptions per-coroutine.

**WHAT IS UNKNOWN:** Whether `ollama_safe.py` has a maximum retry count or retries indefinitely. If it retries indefinitely with no backoff, a dead Ollama could cause the think loop to hang (each tick waiting 60s for an Ollama timeout). The `asyncio.timeout(60)` on the think loop would catch this, but the resulting behavior (rapid retry every 60s vs graceful backoff) is undocumented.

**HOW TO VERIFY:** Stop Ollama (`ollama stop` / kill process), start VECTOR, and observe logs. Check if think loop enters a tight retry cycle or backs off. Check `ollama_safe.py` for retry logic and max attempts.

---

### Q1.4: Is there a circular import risk between `core.memory` and `core.city`?

**WHY IT MATTERS:** The `_RECALL_STOPWORDS` in `episodic.py` was explicitly duplicated from `governor.py` to avoid a circular import. This suggests the dependency graph has cycles. Other modules may have similar latent issues that surface only under specific import orders.

**WHAT WAS CHECKED:** `episodic.py` stopword duplication comment, import chains.

**WHAT IS KNOWN:** `episodic.py` line 42 comment explicitly states: "kept local to this module (rather than importing core.city.governor's copy) to avoid a core.memory <-> core.city circular import."

**WHAT IS UNKNOWN:** How many other such latent circular dependencies exist. Whether `from core.loop.context_engine import context_engine` inside `provider_client.py` (a lazy import inside a function) masks other cycles. Whether refactoring imports could trigger cascading failures.

**HOW TO VERIFY:** Run `python -c "import core.loop.autonomous_loop"` with Python's import verbosity (`-v`) to trace import order. Use `pydeps` or `importlab` to generate the full dependency graph and detect cycles.

---

## 2. Dead-Looking but Possibly Dynamic Code

---

### Q2.1: Are the `vector_finagent`, `vector_backtest`, and `vector_hedgebot` subdirectories actually reachable at runtime?

**WHY IT MATTERS:** These are large absorbed codebases (~thousands of lines) inside `districts/investment/`. If they're unreachable dead code, they inflate the codebase and create a maintenance burden. If they ARE reachable, they may bypass RULE 1 (hydration), RULE 3 (permission gateway), and RULE 11 (free-tier only).

**WHAT WAS CHECKED:** `config/agent_manifest.yaml`, governor routing table, API router imports.

**WHAT IS KNOWN:** `agent_manifest.yaml` references `hedgebot_agent.HedgeBotAgent` and `finagent_agent.FinAgentAgent`. The governor routes `solana_order`, `solana_execute`, `solana_holdings` to `investment` district. `core/api/routers/investment.py` dynamically loads `HedgeBotAgent`.

**WHAT IS UNKNOWN:** Whether the inner sub-packages (`vector_finagent/agno_trading/`, `vector_backtest/src/agent/`, `vector_hedgebot/tools/`) are imported by the top-level agents or are fully orphaned. The `CryptoAgentWrapper` in `vector_hedgebot/experimental/` and `RLTradingAgent` in `vector_finagent/ai_quant_lab/qlib_rl.py` may be invoked by the agent classes or may be completely dead.

**HOW TO VERIFY:** Trace imports from `hedgebot_agent.py` and `finagent_agent.py` — which sub-modules do they actually import? Grep for `from districts.investment.vector_hedgebot` and `from districts.investment.vector_finagent` across the entire codebase. Any imports found must then be checked for RULE compliance.

---

### Q2.2: Is the smart_routing module (`core/inference/smart_routing/`) actively used or is it dead code?

**WHY IT MATTERS:** This module contains 10+ files including wallet generation (BIP-39/BIP-44), x402 USDC micropayment protocol, proxy routing, balance tracking, and partner management. If active, it represents a crypto-payment pathway that has security implications. If dead, it's ~2000+ lines of unmaintained code.

**WHAT WAS CHECKED:** File listing, `__init__.py` exports, grep for imports.

**WHAT IS KNOWN:** The module contains `wallet.py` (HD wallet generation for EVM/Solana), `payment.py` (x402 USDC protocol), `balance.py`, `partners.py`, `proxy.py`, `request_cache.py`, `response_store.py`, `compressor.py`, `classifier.py`, `fallback_chain.py`, `model_catalog.py`, `stats.py`. The docstring says "Python port of ClawRouter" — an external project.

**WHAT IS UNKNOWN:** Whether any active code path imports from `smart_routing`. The wallet and payment modules suggest a crypto-micropayment pathway that could interact with the `hedgebot_agent.py` Solana execution path. The `model_catalog.py` and `classifier.py` may shadow or conflict with the active `core/inference/model_catalog.py`.

**HOW TO VERIFY:** `grep -r "from core.inference.smart_routing" --include="*.py"` and `grep -r "import smart_routing" --include="*.py"` across the entire codebase. If zero imports found outside the module itself, it's dead code.

---

### Q2.3: Are the `alpha_zoo/`, `akshare_fetcher.py`, and `mootdx_fetcher.py` files in investment/ reachable?

**WHY IT MATTERS:** These appear to be Chinese market data fetchers (AkShare, MootDX) and an "Alpha Zoo" quantitative library. If active, they introduce external data dependencies and potential SSRF vectors. If dead, they're ~1000+ lines of orphan code.

**WHAT WAS CHECKED:** File listing of `districts/investment/`.

**WHAT IS KNOWN:** These files exist in the investment district. AkShare and MootDX are Chinese stock market data libraries. `alpha_zoo/` appears to be a quantitative analysis toolkit.

**WHAT IS UNKNOWN:** Whether any agent imports these. Whether they're referenced in the agent manifest. Whether they were absorbed from an external repo and never wired in.

**HOW TO VERIFY:** Grep for `akshare`, `mootdx`, `alpha_zoo` across all Python imports in the codebase. Check `config/agent_manifest.yaml` for any agent that references these modules.

---

### Q2.4: Does the `home_assistant/` district have any active runtime path?

**WHY IT MATTERS:** This district appears in the directory listing but is not mentioned in any rules, planning docs, or the phase_status tracker. If it has agents that get loaded, they consume resources. If not, it's dead weight.

**WHAT WAS CHECKED:** District listing, phase_status.md, rules/districts.md.

**WHAT IS KNOWN:** `districts/home_assistant/` exists as a directory. It is NOT listed in the 33 planned districts in rules/districts.md. It is NOT mentioned in phase_status.md.

**WHAT IS UNKNOWN:** Whether it contains agent files. Whether `bootstrap_agents()` or the governor discovers it via directory scanning. Whether it has an `__init__.py` that registers agents.

**HOW TO VERIFY:** `ls districts/home_assistant/` to see contents. Check if any agent manifest entry references it. Check if the governor's routing table includes any keywords that route to it.

---

### Q2.5: Are `predictive_analytics/`, `science/`, `growth/`, and `emergency/` districts active?

**WHY IT MATTERS:** These directories exist but are NOT in the official 33-district list in rules/districts.md. They may be orphan directories from earlier development, or they may contain agents that are loaded but undocumented.

**WHAT WAS CHECKED:** District listing vs. rules/districts.md official list.

**WHAT IS KNOWN:** Official districts per rules: governance, security, coding, time_calendar, communications, memory_curator, research, intelligence, skills, languages, interview_prep, learning, finance, health, reflection, startups, investment, content, agency, karpathy_lab, projects, relationships, privacy, pattern_detective, news_trends, calls, ops, data_analytics, personal_growth, documentation, qa, chief_of_staff, marketing, design. Extra directories found: `home_assistant`, `predictive_analytics`, `science`, `growth`, `emergency`, `intelligence`.

**WHAT IS UNKNOWN:** Whether these extra directories contain loaded agents. Whether `bootstrap_agents()` does filesystem discovery (which would auto-load them) vs. manifest-only loading.

**HOW TO VERIFY:** Check `bootstrap_agents()` implementation — does it scan `districts/` or read from manifest only? List contents of each undocumented district. Check for `__init__.py` with agent registration code.

---

## 3. Configuration-Dependent Behavior

---

### Q3.1: What is the actual behavior when SQLCipher is not installed?

**STATUS: ✅ RESOLVED (2026-08-13 audit)**

**WHY IT MATTERS:** Rule 7 states "SQLCipher for main DB — always go through `core.memory.episodic.get_db_connection()`." But `episodic.py` falls back to plain `sqlite3` when SQLCipher is unavailable. This means the "encrypted" database may silently be unencrypted, violating the security model.

**WHAT WAS CHECKED:** `episodic.py` import logic, CONFIG handling.

**WHAT IS KNOWN (resolved by audit):**
- `episodic.py` has a 3-stage fallback chain: `sqlcipher3` → `pysqlcipher3` → plain `sqlite3` (fail-OPEN)
- When SQLCipher is active but no key is set: **RuntimeError raised** (fail-CLOSED for key misconfiguration)
- Uses `PRAGMA journal_mode=WAL`, `busy_timeout=5000`, `cipher_page_size=4096`
- The fallback is fail-OPEN: if SQLCipher is not installed, the DB silently runs unencrypted
- Whether the fallback is actually triggered depends on whether `sqlcipher3` is pip-installed on the system

**REMAINING CONCERN:** The fail-open behavior means if SQLCipher is accidentally uninstalled, VECTOR continues running with an unencrypted DB. No startup warning is emitted. Consider adding a `_USE_SQLCIPHER` check at startup that warns the owner.

**HOW TO VERIFY:** Run `python -c "import sqlcipher3; print('ok')"` to check. Check `_USE_SQLCIPHER` value at runtime.

---

### Q3.2: What happens when multiple free-tier providers hit quota simultaneously?

**WHY IT MATTERS:** The quota_ledger deprioritizes providers at >=90% saturation. If all cloud providers are simultaneously near quota (e.g., at end of UTC day when limits reset, or during heavy usage), the system could fall through to Ollama for every call — dramatically reducing quality with no warning.

**WHAT WAS CHECKED:** `quota_ledger.py`, `route_policy.py`, `provider_health.py`.

**WHAT IS KNOWN:** QuotaLedger tracks per-provider usage in `~/.vector_ca/metering/provider_quota.json`. At >=90% saturation, providers are deprioritized (moved after fresh options). Unknown limits = saturation 0 (never deprioritized). Mistral uses per-minute sliding window. The system never hard-blocks.

**WHAT IS UNKNOWN:** Whether there's a global "all cloud providers exhausted" state that triggers owner notification. Whether the system can detect when it's been running on Ollama exclusively for N hours. Whether there's a daily quota summary report. The interaction between quota_ledger (daily counts) and provider_health (reactive error tracking) — do they conflict?

**HOW TO VERIFY:** Check logs for "quota" or "deprioritized" messages during heavy usage. Check if `provider_health.py` has an escalation path when all cloud providers fail. Review `budget_meter.py` for any notification mechanism.

---

### Q3.3: What is the actual effect of `VECTOR_DOMAIN_ROUTING=0` kill switch?

**WHY IT MATTERS:** The models rule states domain routing has a kill switch: `VECTOR_DOMAIN_ROUTING=0`. If enabled, all domain-specific model chains collapse to a single default path. The behavior degradation is undocumented.

**WHAT WAS CHECKED:** `models.md` rule, `vectorcode_llm.py`.

**WHAT IS KNOWN:** Domain routing maps work domains (content.script, coding.review, etc.) to 3-4 model cloud chains + ollama terminal. Kill switch: `VECTOR_DOMAIN_ROUTING=0`. When disabled, falls back to... what? The default `model_pool` routing? Plain `route_policy.decide_route()`?

**WHAT IS UNKNOWN:** The exact fallback behavior when domain routing is disabled. Whether quality degrades silently (wrong model for the task) or whether the system still functions correctly with generic routing.

**HOW TO VERIFY:** Read `vectorcode_llm.py` for the `VECTOR_DOMAIN_ROUTING` env var handling. Check what code path executes when it's 0. Test with the flag set and observe routing decisions in logs.

---

### Q3.4: How does the system behave when `.env` is missing or has partial keys?

**WHY IT MATTERS:** `key_pool.py` calls `load_dotenv()` to load `.env`. If the file is missing, pydantic CONFIG validation should catch it — but the actual error behavior (crash vs. degraded vs. silent) is unclear.

**WHAT WAS CHECKED:** `key_pool.py`, `config.py`.

**WHAT IS KNOWN:** `key_pool.py` calls `load_dotenv()` at import time with exception handling. `config.py` uses Pydantic with SecretStr. The `.env` file is auto-loaded but keys don't need to be system-wide env vars.

**WHAT IS UNKNOWN:** Whether Pydantic CONFIG raises on missing optional keys (like `GEMINI_API_KEY`) or silently sets them to empty/None. Whether the system gracefully handles 0 configured cloud providers (all routing falls to Ollama). Whether there's a startup check that warns "no cloud keys configured."

**HOW TO VERIFY:** Rename `.env` to `.env.bak`, run `python run_vector.py smoke`, observe behavior. Check Pydantic model for `Optional` vs. required fields. Check if `doctor` mode reports missing keys.

---

## 4. Provider Quota Ambiguity

---

### Q4.1: What are the ACTUAL current free-tier limits for each provider?

**WHY IT MATTERS:** `model_catalog.yaml` encodes free-tier limits, but these change frequently (providers raise/lower limits). If the catalog is stale, VECTOR may over-rely on a provider that has already reduced its free tier, causing unexpected 429 errors.

**WHAT WAS CHECKED:** `model_catalog.yaml`, `quota_ledger.py`.

**WHAT IS KNOWN:** The catalog lists per-provider free models and limits. Groq = requests/day/model, Cerebras = tokens/day (1M/day), Cloudflare = neurons/day, Mistral = per-minute TPM/RPS. The quota_ledger tracks usage against these limits.

**WHAT IS UNKNOWN:** Whether the limits in `model_catalog.yaml` are current as of 2026-08. GitHub Models free tier has changed multiple times. Cerebras may have adjusted their 1M tok/day limit. Many providers have "free tier" that is actually "free trial with credit card" — the actual limits may differ from documented ones.

**HOW TO VERIFY:** Cross-reference each provider's current free-tier documentation (August 2026). Test by sending requests until 429 and comparing actual limit to catalog value. Add a periodic "limit probe" that tests remaining quota.

---

### Q4.2: Does the quota_ledger correctly track tokens vs. requests per provider?

**WHY IT MATTERS:** Different providers count usage differently (Groq = requests/day, Cerebras = tokens/day, Cloudflare = neurons/day). If the ledger conflates these units, quota tracking is meaningless — a provider could be at 200% of its real limit while the ledger shows 10%.

**WHAT WAS CHECKED:** `quota_ledger.py` docstring and structure.

**WHAT IS KNOWN:** The ledger tracks `{requests, tokens}` per provider per bucket per day. The docstring explains per-provider units. Mistral uses a sliding in-memory minute window.

**WHAT IS UNKNOWN:** Whether the `_call_*` functions in `provider_client.py` actually report token counts back to the ledger. Whether response usage metadata (which varies by provider API format) is correctly parsed. Whether the ledger's token counting matches the provider's actual counting method (e.g., does Cloudflare count "neurons" the same way the ledger counts tokens?).

**HOW TO VERIFY:** Check each `_call_*` function for `usage` field extraction and ledger reporting. Compare ledger's token count for a known request against the provider's dashboard. Check if prompt_tokens + completion_tokens matches provider-reported usage.

---

### Q4.3: What happens at UTC midnight when quota resets — is there a thundering herd?

**WHY IT MATTERS:** All quotas reset at UTC midnight. If VECTOR has been deferring tasks to Ollama all day because cloud providers were saturated, at midnight they all become fresh simultaneously. The routing system might rapidly fire many cloud requests in succession, hitting rate limits.

**WHAT WAS CHECKED:** `quota_ledger.py` reset logic.

**WHAT IS KNOWN:** The ledger is keyed by UTC date string (`_today()`). At midnight UTC, a new date key is created with zero usage. All providers appear fresh.

**WHAT IS UNKNOWN:** Whether there's any rate-limiting on the "fresh" transition. Whether the round-robin key pool (`key_pool.py`) and the provider routing (`route_policy.py`) both reset simultaneously, creating a burst. Whether Mistral's per-minute sliding window creates a different reset pattern.

**HOW TO VERIFY:** Monitor logs around UTC midnight for burst patterns. Check if there's any "warm-up" logic that gradually reintroduces cloud providers after reset.

---

## 5. Memory Subsystem Ambiguity

---

### Q5.1: What is the interaction between episodic memory, LightRAG, semantic memory, and the collections engine?

**WHY IT MATTERS:** VECTOR has 4+ memory stores: episodic (SQLite FTS5), LightRAG (nano-vectordb), semantic memory (SQLite), and collections engine (dynamic tables). The memory rules say "never mix the two stores" (episodic vs. LightRAG), but the actual boundaries are unclear.

**WHAT WAS CHECKED:** `episodic.py`, `obsidian_sync.py` (LightRAG integration), `semantic.py`, `collections/`.

**WHAT IS KNOWN:** Episodic memory = SQLite FTS5 (5 sacred tables). LightRAG = semantic memory for District 7 research (nano-vectordb internal). Collections = dynamic schema tables in separate namespace (`_collections` / `col_<name>`). The memory rule says internal memories use SQLite FTS5, LightRAG is for external knowledge.

**WHAT IS UNKNOWN:** Whether `semantic.py` writes to the same DB as `episodic.py` or a separate file. Whether the collections engine can accidentally write to the 5 sacred tables. Whether `memory/router.py` (which exists) arbitrates between stores — and if so, what its routing logic is. Whether `memory/tiering.py` moves data between stores (hot → cold → archive).

**HOW TO VERIFY:** Read `memory/router.py` and `memory/tiering.py` to understand inter-store routing. Check `semantic.py`'s DB path — is it the same `vector_memory.db`? Check `db_registry.py` for the authoritative store mapping. List all `.db` files in the data directory.

---

### Q5.2: Is `memory/decay.py` actively decaying memories, and what is the decay function?

**WHY IT MATTERS:** Memory decay is critical for a system that runs 24/7 — without decay, the episodic store grows unboundedly, degrading search quality and consuming disk. But the decay function and its parameters are undocumented.

**WHAT WAS CHECKED:** File listing shows `core/memory/decay.py` exists.

**WHAT IS KNOWN:** `decay.py` exists in the memory module. It presumably implements some form of memory strength decay over time (Ebbinghaus-style or custom).

**WHAT IS UNKNOWN:** Whether decay is actually invoked by the autonomous loop (in reflect?) or is dead code. What the decay function is (exponential, linear, power-law). What the half-life is. Whether decay deletes records or just reduces search ranking. Whether it interacts with the 2AM reflect cycle.

**HOW TO VERIFY:** Read `decay.py` to understand the function. Grep for `decay` in `autonomous_loop.py` and `cron_jobs.py` to see if it's invoked. Check the reflect cycle for decay calls.

---

### Q5.3: What is `memory/external_mirror.py` and does it create a shadow copy of data?

**WHY IT MATTERS:** A module named "external_mirror" suggests it mirrors memory to an external store. If active, it could be sending data to a cloud service — violating the local-first rule. If it's mirroring to the Obsidian vault, it's benign but should be documented.

**WHAT WAS CHECKED:** File listing shows `core/memory/external_mirror.py` exists.

**WHAT IS KNOWN:** The file exists. Its name suggests it mirrors internal memory to an external location.

**WHAT IS UNKNOWN:** What it mirrors, where it mirrors to, whether it's active, whether it respects the privacy enforcer's cloud-vs-local rules.

**HOW TO VERIFY:** Read `external_mirror.py`. Check for any cloud URLs, file paths, or API calls. Grep for `external_mirror` across the codebase to see if anything imports it.

---

### Q5.4: Does `memory/shared_facts.py` create a cross-agent knowledge store, and how is consistency maintained?

**WHY IT MATTERS:** If multiple agents can write shared facts concurrently, consistency is a concern. SQLite WAL mode handles concurrent reads but only one writer at a time. If two agents try to write simultaneously, one will block or fail.

**WHAT WAS CHECKED:** File listing shows `core/memory/shared_facts.py` exists.

**WHAT IS KNOWN:** The module exists. It presumably maintains a set of facts shared across agents/districts.

**WHAT IS UNKNOWN:** Whether it uses the same SQLite DB (and thus the same write lock). Whether it has its own consistency model (CRDT, last-write-wins, append-only). Whether facts can conflict (agent A asserts X, agent B asserts not-X).

**HOW TO VERIFY:** Read `shared_facts.py`. Check its DB connection — does it use `get_db_connection()` from episodic? Check for locking mechanisms. Check the reflect cycle for conflict resolution.

---

### Q5.5: Is `memory/session_buffer.py` buffering writes and could this cause data loss on crash?

**WHY IT MATTERS:** A session buffer suggests writes are batched and flushed periodically. If VECTOR crashes between buffer and flush, recent memories are lost. The buffer size and flush interval determine the data-loss window.

**WHAT WAS CHECKED:** File listing shows `core/memory/session_buffer.py` exists.

**WHAT IS KNOWN:** The module exists. It likely buffers memory writes in memory and flushes to disk periodically or on trigger.

**WHAT IS UNKNOWN:** Buffer size limit. Flush interval. Whether flush is synchronous (crash-safe) or async (data loss risk). Whether the autonomous loop's crash-recovery replays the buffer.

**HOW TO VERIFY:** Read `session_buffer.py`. Check flush logic and trigger conditions. Check if `run_vector.py` has a shutdown hook that flushes the buffer.

---

## 6. Agent Reachability

---

### Q6.1: Which of the 133+ agents are actually reachable via governor routing?

**WHY IT MATTERS:** The governor has 180 routing rules, but many agents may never receive tasks because their district's keywords don't match any common query pattern. Unreachable agents consume memory (if loaded) but provide no value.

**WHAT WAS CHECKED:** Governor routing table in `governor.py`, agent manifest.

**WHAT IS KNOWN:** The governor has regex patterns, embedding matchers, and LLM classification. 180 routing rules map keywords to districts. Districts contain agents. But the district→agent mapping within a district is unclear — does the governor pick a specific agent, or does the district's `__init__.py` handle internal routing?

**WHAT IS UNKNOWN:** How many of the 133+ agents have ever received a task in production. Whether agents like `ui_designer.py`, `ux_researcher.py`, `image_prompt_engineer.py` (design district) are ever routed to. Whether the `home_assistant`, `predictive_analytics`, `science`, `growth`, `emergency` district agents are reachable.

**HOW TO VERIFY:** Check episodic memory for `event_type="agent_task"` and count unique agents that have been invoked. Alternatively, add a metric to `agent_registry.py` that tracks "tasks received per agent" and run for 24 hours.

---

### Q6.2: Does the LLM Council actually convene, and do HP>700 agents exist?

**WHY IT MATTERS:** The LLM Council (vector-reasoning + vector-r1 + qwen3:30b-a3b + vector-chairman) is the governance mechanism for high-stakes decisions. But it requires agents with HP > 700. If no agents have ever reached 700 HP (because the HP system is newly implemented or agents die too quickly), the council is dead code.

**WHAT WAS CHECKED:** `agent_base.py` HP system, `llm_council.py`, `governor.py`.

**WHAT IS KNOWN:** HP system is 0-1000. Council requires HP > 700. Agents gain HP for successful tasks (+30 to +100) and lose HP for failures (-30 to -100). Agent registry handles death at 0 HP and successor spawning.

**WHAT IS UNKNOWN:** The current HP distribution across all agents. Whether any agents have reached 700+ HP. Whether the council has ever been invoked in production. Whether HP inflation occurs (agents always gain, rarely lose).

**HOW TO VERIFY:** Query `agent_history` table: `SELECT name, hp FROM agents WHERE hp > 700`. Check episodic memory for `event_type="council_session"`. Check if `llm_council.py` has invocation logs.

---

### Q6.3: Are the marketing and design district agents wired into the governor?

**WHY IT MATTERS:** These were added as "Bonus Districts" from agency-agents alignment. If the governor's routing table wasn't updated to include their keywords, they're unreachable despite existing.

**WHAT WAS CHECKED:** Governor routing keywords (partial), district listing.

**WHAT IS KNOWN:** Marketing district has 5 agents (seo_specialist, growth_hacker, social_media_strategist, content_creator, ai_citation_strategist). Design district has 3 agents (ui_designer, ux_researcher, image_prompt_engineer).

**WHAT IS UNKNOWN:** Whether the governor's 180 routing rules include keywords for "SEO", "growth hack", "social media", "UI design", "UX research". The governor's `_regex_classify` patterns were not fully enumerated.

**HOW TO VERIFY:** Read the full routing table in `governor.py` and check for marketing/design keywords. Test by sending a marketing-related query and observing which district receives it.

---

## 7. Undocumented Side Effects

---

### Q7.1: Does the 2AM reflect cycle modify or delete episodic memories?

**WHY IT MATTERS:** The reflect cycle "prunes old episodic memories" per the context definition. If it aggressively deletes memories, it could destroy data that the counterfactual memory, causal graph, or meta-cognition modules need. The pruning criteria are undocumented.

**WHAT WAS CHECKED:** `autonomous_loop.py` reflect cycle description, memory rules.

**WHAT IS KNOWN:** The reflect cycle runs at 2AM daily. It "summarizes the day, updates semantic memory, extracts patterns, and prunes old episodic memories." Memory rules say "NEVER delete agent_history rows — only mark is_dead=1." But episodic memory pruning rules are not specified.

**WHAT IS UNKNOWN:** The pruning criteria (age? relevance? count?). Whether pruning is a DELETE or a soft-delete (mark as archived). Whether pruned memories are summarized into semantic memory before deletion. Whether the causal graph's nodes reference pruned episodic memories (creating dangling references).

**HOW TO VERIFY:** Read the reflect cycle implementation in `autonomous_loop.py`. Check for DELETE statements vs. UPDATE statements on episodic_memory. Check if `decay.py` is called during reflect. Count episodic_memory rows before and after a reflect cycle.

---

### Q7.2: Does the Obsidian sync write to the vault without owner review?

**WHY IT MATTERS:** `obsidian_sync.py` writes to the Obsidian vault (Daily/, Reflections/, Council/, etc.). If it writes incorrect or low-quality content, the owner's knowledge base is polluted. The sync direction (one-way vs. two-way) and quality gates are unclear.

**WHAT WAS CHECKED:** `obsidian_sync.py` description, memory rules.

**WHAT IS KNOWN:** Obsidian vault is at `C:\Users\Arghyadeep\V.E.C.T.O.R Brain\`. VECTOR writes to Daily/, Reflections/, Council/, Agent HP/, Research/, Interviews/. The watchdog ingests vault changes within 30s (read direction).

**WHAT IS UNKNOWN:** What triggers writes (reflect cycle? real-time?). Whether writes go through the permission gateway (YELLOW tier for file writes?). Whether there's a quality gate or review step. Whether VECTOR can overwrite existing vault files. Whether the two-way sync (VECTOR writes → vault, vault changes → VECTOR reads) creates race conditions.

**HOW TO VERIFY:** Read `obsidian_sync.py` for write triggers and content generation. Check if it calls `permission_gateway` before writing. Check the watchdog's handling of VECTOR-generated files vs. owner-generated files.

---

### Q7.3: Does the evolution engine's `cull_bottom()` actually kill agents, and what are the criteria?

**WHY IT MATTERS:** `evolution_engine.py` has `cull_bottom()` which presumably kills the lowest-performing agents. If this runs too aggressively, it could kill agents that are still useful. If it never runs, the Darwinian model is incomplete.

**WHAT WAS CHECKED:** `evolution_engine.py` description, phase_status.md.

**WHAT IS KNOWN:** `evolution_engine.py` implements "Cross-gen lesson inheritance, cull_bottom()." The agent registry handles death at 0 HP and successor spawning with ghost memory.

**WHAT IS UNKNOWN:** What triggers `cull_bottom()` (periodic? manual? reflect cycle?). What percentile is culled. Whether culled agents' ghost memory is preserved. Whether culling happens alongside HP-based death (double-kill risk). Whether it has ever fired in production.

**HOW TO VERIFY:** Read `evolution_engine.py` for `cull_bottom()` implementation. Grep for `cull_bottom` in `autonomous_loop.py` and `cron_jobs.py`. Check agent_history for cause-of-death patterns.

---

### Q7.4: What side effects does the `ponytail_guard.py` have on LLM calls?

**WHY IT MATTERS:** The ponytail guard injects a "decision ladder" into every `coding.*`/`saas.*` LLM call. This modifies the prompt sent to the model. The exact injection point and effect on output quality is undocumented.

**WHAT WAS CHECKED:** `ponytail_guard.py` existence, models rule description.

**WHAT IS KNOWN:** `ponytail_guard.py` injects the ponytail decision ladder into coding/saas LLM calls via `vectorcode_llm.chat()`. It's described as "vendored at `ponytail/`" and is "wired into VECTOR runtime (not just Claude)." Intensity is `full` by default.

**WHAT IS UNKNOWN:** How many tokens the injection adds to each call (cost impact on free-tier quota). Whether it affects non-coding domains accidentally. Whether it can be toggled per-call vs. globally. Whether the injection happens before or after `session_hydration_prompt()`.

**HOW TO VERIFY:** Read `ponytail_guard.py` for injection logic. Measure prompt length with and without the guard. Check if it uses `VECTOR_DOMAIN_ROUTING` or a separate flag.

---

## 8. Race Conditions

---

### Q8.1: Can the event bus and autonomous loop create a deadlock?

**WHY IT MATTERS:** The event bus publishes events that handlers process. If a handler in the observe loop publishes an event that the think loop handles, and the think loop publishes an event that the observe loop handles, a circular dependency could deadlock the asyncio event loop.

**WHAT WAS CHECKED:** `event_bus/base.py`, `event_bus/worker_pool.py`, `autonomous_loop.py`.

**WHAT IS KNOWN:** The event bus has handlers that are called with `await handler(data)`. The worker pool suggests async event processing. The autonomous loop has 4 concurrent coroutines. Event types include `observe.tick`, `think.tick`, `act.tick`, `reflect.tick`.

**WHAT IS UNKNOWN:** Whether handlers are awaited inline (blocking the publisher) or dispatched to the worker pool (non-blocking). If inline, a slow handler blocks the publishing coroutine. If the worker pool has a bounded queue, it could fill up and block publishers. Whether there's a circuit breaker on the event bus.

**HOW TO VERIFY:** Read `event_bus/bus.py` for publish semantics (inline vs. dispatched). Read `event_bus/worker_pool.py` for queue bounds and overflow behavior. Check `event_bus/circuit_breaker.py` for trip conditions.

---

### Q8.2: Can `multi_db_manager.py`'s sync queue lose writes during crash?

**WHY IT MATTERS:** `MultiDBManager` writes to local SQLite first, then queues cloud sync. The sync queue is a `deque(maxlen=10000)` in memory. If VECTOR crashes with 5000 unsynced writes in the queue, those writes are lost to the cloud stores — creating a consistency gap between local and cloud.

**WHAT WAS CHECKED:** `multi_db_manager.py` structure.

**WHAT IS KNOWN:** The sync queue is an in-memory `deque` with max 10,000 entries. Last-write-wins based on `updated_at` timestamp. Local SQLite is always written first.

**WHAT IS UNKNOWN:** Whether the queue is persisted to disk (survives crash) or is purely in-memory (lost on crash). Whether there's a replay mechanism on startup. Whether the cloud stores can detect and fill the gap. Whether 10,000 is enough buffer for heavy usage.

**HOW TO VERIFY:** Read `multi_db_manager.py` for queue persistence logic. Check if there's a startup "sync catch-up" routine. Check if `run_vector.py` has a shutdown hook that flushes the queue.

---

### Q8.3: Can concurrent SQLite writes from multiple threads corrupt the database?

**STATUS: ✅ RESOLVED (2026-08-13 audit)**

**WHY IT MATTERS:** Multiple modules create their own SQLite connections: `episodic.py`, `counterfactual.py`, `causal_graph.py`, `person_model.py`, `meta_cognition.py`. Some use `threading.RLock`, some use `threading.Lock`, some use class-level locks. If two modules write to the same database file from different threads without coordinating, SQLite's locking may not be sufficient.

**WHAT WAS CHECKED:** Module-level lock patterns across memory modules.

**WHAT IS KNOWN (resolved by audit):**
- SQLite WAL mode + `busy_timeout=5000` (5 seconds) handles concurrent readers + single writer correctly
- `episodic.py` has `get_db_write_lock()` — a **module-level** lock shared across all callers
- `counterfactual.py`, `causal_graph.py`, `person_model.py` all use their own `threading.RLock()`/`Lock()`
- `provider_health.py` has a dedicated `_lock` protecting `_meta` + `_disabled` dicts
- The audit verified thread safety across provider_health, quota_ledger, model_pool, semantic.py
- `semantic.py` routes all writes through `get_temp_cursor()` context manager which holds `_write_lock`

**RESOLUTION:** The locking is **adequate for the current workload**. WAL mode allows concurrent reads while one writer holds the lock. `busy_timeout=5000` means writers wait up to 5s instead of failing immediately. Each module has its own lock, and the main DB uses `get_db_write_lock()` which is shared.

**REMAINING CONCERN:** If two modules both hold their own locks and try to write to the same DB file simultaneously, SQLite's internal file locking handles it (WAL allows one writer). The `busy_timeout` ensures they wait rather than fail. This is safe but could cause latency under heavy concurrent write load.

**HOW TO VERIFY:** Stress test with concurrent writes from multiple modules — verify no "database is locked" errors.

---

### Q8.4: Can the key pool's round-robin cause a thundering herd on a single key?

**WHY IT MATTERS:** `KeyPool` does round-robin across multiple keys per provider. If a key is benched (429/401) and then un-benched after cooldown, all pending requests may hit it simultaneously — causing another 429 and re-benching.

**WHAT WAS CHECKED:** `key_pool.py` structure.

**WHAT IS KNOWN:** `KeyPool` uses round-robin with `_idx` counter. Benched keys are skipped. Cooldown is 300s (5 min) by default. A `threading.Lock` protects the pool.

**WHAT IS UNKNOWN:** Whether un-benching is gradual (one request at a time) or immediate (all at once). Whether there's exponential backoff on repeated benching. Whether the cooldown is per-key or global.

**HOW TO VERIFY:** Read `key_pool.py` for un-bench logic. Check if `_benched` dict uses timestamps and whether keys are lazily un-benched on `next_key()` call. Check for backoff multiplier on repeated failures.

---

## 9. Cross-Cutting Questions

---

### Q9.1: What is the total token cost per day of running VECTOR autonomously?

**WHY IT MATTERS:** The owner decision is "free-tier only at runtime." But free tiers have limits. If VECTOR's autonomous loop generates more LLM calls per day than the free tiers allow, it silently degrades to Ollama — potentially reducing quality below acceptable levels without any visible alert.

**WHAT WAS CHECKED:** Quota ledger, autonomous loop cadence, model routing.

**WHAT IS KNOWN:** Observe loop runs every 0.5s (172,800 ticks/day). Think loop is event-driven. Not every tick generates an LLM call — many are handled by regex/embedding classification. But the think loop, reflect cycle, hypothesis engine (every 4h), synthesis bridge (every 30min), and council sessions all generate LLM calls.

**WHAT IS UNKNOWN:** The actual number of LLM calls per day in production. The average token count per call. Whether the total daily token usage fits within the combined free-tier limits. Whether there's a daily cost report.

**HOW TO VERIFY:** Check `~/.vector_ca/metering/provider_quota.json` for yesterday's usage across all providers. Sum up requests and tokens. Compare against each provider's free-tier limit. If possible, add a daily summary log entry.

---

### Q9.2: Is the LoRA-fine-tuned qwen3:8b intent classifier actually loaded and working?

**STATUS: ✅ RESOLVED (2026-08-13 audit)**

**WHY IT MATTERS:** The governor's Stage 3 classification uses a LoRA-fine-tuned qwen3:8b model. If the LoRA adapter isn't correctly loaded (wrong path, incompatible base model, OOM), Stage 3 silently fails and all classification falls through to Stage 4 (LLM fallback, 3-12s latency) — dramatically slowing response times.

**WHAT WAS CHECKED:** `core/training/lora_trainer.py`, intent classifier integration.

**WHAT IS KNOWN (resolved by audit):**
- `lora_trainer.py` has `_should_simulate()` which returns True unless `VECTOR_TRAINING_REAL=1`
- **All training is SIMULATED by default** — no actual LoRA weights are produced
- The fine-tuning pipeline exists as infrastructure but does not produce real model weights at runtime
- The BERT classifier (Phase 2) had 9.5% accuracy on the original (district, task_type) multi-class problem
- A fix plan exists to simplify BERT to district-only classification (38 classes) + LLM data augmentation
- Task #85 (integrate into governor) and #86 (test and verify) are still pending

**RESOLUTION:** The LoRA-fine-tuned classifier is NOT loaded because training is simulated. The governor falls through to Stage 4 (LLM fallback) for Stage 3 classification. This is acceptable because:
1. Phase 1 (embedding similarity) achieves 90% accuracy at 100-300ms latency
2. Stage 4 LLM fallback works correctly, just with higher latency (3-12s)
3. The fix plan (district-only BERT + data augmentation) should bring Phase 2 to 90-95% accuracy

**HOW TO ACTIVATE:** Set `VECTOR_TRAINING_REAL=1` env var to enable real LoRA training. Requires GPU, training data, and proper Ollama model paths.

---

### Q9.3: Does the NSSM Windows service correctly restart after a crash, and what state is lost?

**WHY IT MATTERS:** VECTOR is installed as a Windows service via NSSM with `AppExit Default Restart` and `AppRestartDelay 5000`. On crash, NSSM restarts it after 5 seconds. But the in-memory state (event bus subscriptions, sync queue, quota ledger minute-window, sense cache) is lost.

**WHAT WAS CHECKED:** `scripts/install_service.ps1`, NSSM configuration.

**WHAT IS KNOWN:** NSSM is configured with `AppStopMethodConsole=1` (graceful CTRL+C), `AppRestartDelay 5000`, `AppExit Default Restart`. The service uses the `.venv` Python.

**WHAT IS UNKNOWN:** What happens to in-flight actions when the service crashes mid-execution. Whether the `deque` sync queue's pending cloud writes are lost. Whether the quota ledger's minute-window tracking (Mistral TPM) resets correctly. Whether the event bus needs re-subscription on restart. Whether `loop_state.py` has checkpoint/restore.

**HOW TO VERIFY:** Read `loop_state.py` for checkpoint logic. Check if `multi_db_manager.py` persists its sync queue. Force-kill the service and observe restart behavior. Check logs for "restarting from checkpoint" or similar messages.

---

### Q9.4: Can the `cloud_router.py` route to providers that have been removed from the catalog?

**WHY IT MATTERS:** `cloud_router.py` exists alongside `route_policy.py` and `model_catalog.py`. If it has a hardcoded provider list that's separate from the YAML catalog, removing a provider from the catalog won't stop `cloud_router.py` from trying to use it.

**WHAT WAS CHECKED:** File listing shows `core/inference/cloud_router.py` exists.

**WHAT IS KNOWN:** The active routing path is `route_policy.py` → `model_catalog.yaml` → `provider_client.py`. But `cloud_router.py` also exists and may be an older routing implementation.

**WHAT IS UNKNOWN:** Whether `cloud_router.py` is actively imported by any code path. Whether it has its own provider list. Whether it conflicts with `route_policy.py`.

**HOW TO VERIFY:** Grep for `cloud_router` imports across the codebase. If imported, check its provider list. If not imported, it's dead code.

---

### Q9.5: Is the `provider_health.py` module actually monitoring provider availability?

**WHY IT MATTERS:** `provider_health.py` presumably tracks provider error rates and availability. If it's not actively used, the system has no proactive provider monitoring — it only discovers failures when a call fails.

**WHAT WAS CHECKED:** File listing shows `core/inference/provider_health.py` exists.

**WHAT IS KNOWN:** The file exists. The quota_ledger docstring mentions "unknown limits mean saturation 0 (purely reactive handling via provider_health)" — suggesting provider_health IS the reactive failure tracker.

**WHAT IS UNKNOWN:** Whether it's actively imported and used. What metrics it tracks (error rate, latency, availability). Whether it triggers provider rotation or just logs. Whether it feeds into the routing decision.

**HOW TO VERIFY:** Grep for `provider_health` imports. Read the module for its tracking logic. Check if `route_policy.py` or `provider_client.py` consults it before routing.

---

## Summary of Priority

### Highest Priority (blocks autonomous operation)
| Q# | Question | Impact | Status |
|----|----------|--------|--------|
| Q1.2 | Session hydration before every LLM call | RULE 1 violation risk | ⚠️ PARTIALLY RESOLVED — caller-responsible, but bypass risk in absorbed code |
| Q8.3 | Concurrent SQLite writes | Database corruption risk | ✅ RESOLVED — WAL+busy_timeout+locks adequate |
| Q3.1 | SQLCipher fallback behavior | Security model violation | ✅ RESOLVED — fail-open chain, but no startup warning |
| Q9.2 | LoRA classifier integration | Governor accuracy degradation | ✅ RESOLVED — simulated by default, Phase 1 at 90% |

### High Priority (quality/reliability impact)
| Q# | Question | Impact |
|----|----------|--------|
| Q2.1 | Investment sub-directory reachability | RULE compliance risk |
| Q4.1 | Actual free-tier limits | Unexpected Ollama fallback |
| Q5.1 | Memory store interaction boundaries | Data consistency |
| Q8.2 | Sync queue crash safety | Cloud-local consistency gap |
| Q9.1 | Daily token cost | Free-tier exhaustion |

### Medium Priority (operational awareness)
| Q# | Question | Impact |
|----|----------|--------|
| Q1.1 | Initialization order | Startup race condition |
| Q1.3 | Ollama-down behavior | Degraded mode clarity |
| Q3.2 | All-cloud-providers-exhausted | Silent quality drop |
| Q5.2 | Memory decay activation | Unbounded memory growth |
| Q6.1 | Agent reachability | Wasted resources |
| Q7.1 | Reflect cycle pruning | Data loss risk |
| Q9.3 | NSSM restart state loss | In-flight action loss |

### Lower Priority (code cleanliness)
| Q# | Question | Impact |
|----|----------|--------|
| Q1.4 | Circular import risk | Latent crash on refactor |
| Q2.2 | Smart routing alive/dead | Maintenance burden |
| Q2.3-2.5 | Undocumented districts | Codebase bloat |
| Q3.3-3.4 | Config edge cases | Undocumented degradation |
| Q4.2-4.3 | Quota tracking accuracy | Monitoring gap |
| Q5.3-5.5 | Memory module internals | Unknown behavior |
| Q6.2-6.3 | Council/HP verification | Governance verification |
| Q7.2-7.4 | Side effects documentation | Operational surprise |
| Q8.1, Q8.4 | Deadlock/thundering herd | Latency spikes |
| Q9.4-9.5 | Dead routing/health code | Maintenance burden |

---

## How to Use This Document

1. **Before each build session**: Scan for questions in the category you're working on
2. **When discovering new behavior**: Check if a question already covers it before adding
3. **When resolving a question**: Update the WHAT IS KNOWN / WHAT IS UNKNOWN sections and move to "Resolved" below
4. **Quarterly review**: Re-prioritize based on what's become more/less important

---

## Resolved Questions

### Resolved by 46_COGNITIVE_INTEGRATION_AUDIT.md (2026-08-13)

**Q1.2 (PARTIALLY RESOLVED):** Session hydration is caller-responsible — `provider_client.chat()` and `vectorcode_llm.chat()` do NOT call `session_hydration_prompt()` internally. 85 files reference hydration and handle it explicitly. Remaining risk: absorbed code in `districts/investment/vector_finagent/` and `vector_hedgebot/` may bypass hydration.

**Q3.1 (RESOLVED):** SQLCipher fallback chain is: `sqlcipher3` → `pysqlcipher3` → plain `sqlite3` (fail-OPEN). When SQLCipher is active but no key is set, RuntimeError is raised (fail-CLOSED). Uses WAL mode + busy_timeout=5000. Concern: fail-open means no startup warning if SQLCipher is accidentally missing.

**Q8.3 (RESOLVED):** Concurrent SQLite writes are safe. WAL mode + `busy_timeout=5000` handles concurrent reads + single writer. Each module has its own lock. `episodic.py` has module-level `get_db_write_lock()` shared across callers. `semantic.py` routes writes through `get_temp_cursor()` with lock. No corruption risk under current workload.

**Q9.2 (RESOLVED):** LoRA training is simulated by default (`VECTOR_TRAINING_REAL=1` required for real training). No actual LoRA weights are produced at runtime. Governor falls through to Stage 4 LLM fallback. Phase 1 embedding similarity achieves 90% accuracy at 100-300ms.

---

_Last updated: 2026-08-13_
