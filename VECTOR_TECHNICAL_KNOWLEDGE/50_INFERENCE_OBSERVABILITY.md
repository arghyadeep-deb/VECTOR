# 50 — Inference Observability

**Status**: ✅ IMPLEMENTED, completeness pass closed 2026-09-01
**Scope**: Measurement only. Does NOT change provider routing, model selection, retry behavior,
timeouts, prompts, or any decision logic.

**Revision history**:
- 2026-09-01 (initial): Call graph traced, `ollama_safe`/`vectorcode_llm` bypass paths
  instrumented, 14 direct call sites tagged with `caller_id`.
- 2026-09-01 (completeness pass): Closed 4 of 5 previously-documented gaps (tokens/model,
  autonomous/user token sums, raw fallback count, retry count) with measurement-only additions;
  the 5th (streaming token exactness) was fully closed by reading fields the Ollama SDK already
  returns but the code previously discarded. See §6 and §10 for the final per-requirement status.

---

## 1. Purpose

VECTOR makes LLM calls through 27+ providers across ~180 call sites (district agents, governor,
autonomous loop, voice pipeline, API routers, terminal UI). Before this work, there was **no
unified measurement** of that traffic — no answer to "how many calls/day", "what's the token
split between autonomous and user-triggered work", "what's our p95 latency", or "how often do we
fall back to Ollama". `budget_meter.py`, `quota_ledger.py`, and `provider_health.py` each tracked
a narrow slice (cost, per-provider quota, circuit-breaker health) with no cross-cutting view.

This layer adds that cross-cutting view: every LLM call — success or failure, cloud or local,
autonomous or user-triggered — is recorded to one SQLite table (`inference_calls` in
`data/telemetry.db`) with metadata only (never prompt/response content), and exposed via
aggregation queries, a CLI (`scripts/inference_report.py`), and an alert-check function.

**Explicitly out of scope for this pass**: changing which provider gets picked, changing retry/
fallback ordering, changing timeouts, or making any decision based on the collected data. The
owner directive was instrument-first, collect a baseline, decide what (if anything) to optimize
later.

---

## 2. Complete LLM Call Graph

```
                              ┌─────────────────────────────┐
                              │  vectorcode_llm.chat()       │  ← district-agent entry point
                              │  (core/inference/            │    ~112 call sites via
                              │   vectorcode_llm.py)         │    "from vectorcode_llm import chat"
                              └──────────────┬────────────────┘
                                             │
                     ┌───────────────────────┼───────────────────────────┐
                     │                       │                           │
                     ▼                       ▼                           ▼
          explicit provider=       route_policy.decide_route()   domain alignment
          "gemini"/"anthropic"/    (local_only? sensitive?)      (model="domain:X")
          "openrouter"/"ollama"          │                             │
                     │                    ▼                             │
                     │         local_only=True? ──yes──► _try_ollama()  │
                     │                    │ no                          │
                     │                    └─────────────┬───────────────┘
                     │                                  ▼
                     │                    ┌─────────────────────────────┐
                     │                    │  ProviderClient.chat()       │  ★ PRIMARY
                     │                    │  (core/inference/            │    INSTRUMENTATION
                     │                    │   provider_client.py)        │    POINT — records
                     │                    └──────────────┬────────────────┘   to inference_calls
                     │                                  │                    on every success
                     │              ┌────────────────────┼─────────────────┐  AND every
                     │              ▼                    ▼                 ▼  all-providers-
                     │      _call_openai_compat   _call_anthropic   _call_gemini  failed exit
                     │      (Groq/Cerebras/Cloud- (native Anthropic (native Gemini
                     │       flare/GitHub/LLM7/    Messages API)     generateContent)
                     │       Mistral/DeepSeek/
                     │       OpenRouter/Ollama —
                     │       all OpenAI-compat)
                     │                    │
                     │        (raises) ───┘
                     ▼                    ▼
     ┌───────────────────────────────────────────────────────┐
     │  Legacy fallback chain (only reached if ProviderClient  │  ★ SECONDARY
     │  itself raises — rare, e.g. import error, thread-pool   │    INSTRUMENTATION
     │  timeout):                                               │    POINT — _record_usage()
     │    _try_gemini() → _try_openrouter() → _try_ollama()    │    now also writes to
     │  (core/inference/vectorcode_llm.py, module-level fns)   │    inference_calls for
     └──────────────────┬────────────────────────────────────┘    gemini/openrouter legs
                        │                                          (ollama leg delegates
                        ▼                                          below, not double-counted)
              ┌─────────────────────────┐
              │  ollama_safe.chat()      │  ★ TERTIARY INSTRUMENTATION POINT
              │  (core/inference/         │    — direct-call bypass path, ~10 call sites
              │   ollama_safe.py)         │    never touch ProviderClient at all
              └──────────┬──────────────┘
                         │
           ┌─────────────┼──────────────┬───────────────┬────────────────┐
           ▼             ▼              ▼               ▼                ▼
      ollama SDK    AirLLM (70B+     _multi_backend_  circuit breaker  semaphore
      .chat()        models,         fallback():       open → same     timeout →
      (local          layer-         LiteLLM →         fallback         same fallback
      daemon)         streaming)     Apple FM →
                                     Gemma C++
```

### 2a. Direct callers of `ollama_safe.chat()` (bypass `ProviderClient` entirely)

These never go through `route_policy`, `provider_client`, quota ledger, or provider health —
they hit the local Ollama daemon (or its multi-backend fallback) directly. All 10 are now
tagged with a distinct `caller_id` for attribution in `inference_calls`:

| File | Function | `caller_id` tag |
|------|----------|-----------------|
| `core/city/agent_base.py` | `AgentBase.vchat()` | `agent_{self.name}` |
| `core/city/governor.py` | `Governor._llm_classify()` local fallback | `governor_classify_local` |
| `core/inference/model_router.py` | `TaskClassifier._classify_with_llm()` | `model_router_classify` |
| `core/voice/realtime.py` | `_classify_intent_llm()` local fallback | `voice_intent` |
| `core/runtime/missions.py` | `MissionPlanner._call_model()` | `runtime_missions_planner` |
| `core/ui/web_ui.py` | `POST /chat` | `web_ui_chat` |
| `core/ui/web_ui.py` | `WS /ws/chat` (via `chat_stream()`) | `web_ui_ws_chat` |
| `core/ui/web_ui.py` | `POST /tasks/submit` | `web_ui_task` |
| `core/ui/chat.py` | `_chat_with_vector()` (terminal REPL) | `terminal_ui_chat` |
| `core/ui/chat.py` | `/bg` command background task | `terminal_ui_bg_task` |
| `core/engine/channels/runtime.py` | channel-adapter governor-dispatch fallback | `channel_runtime_fallback` |
| `core/api/routers/tasks.py` | `POST /tasks/submit` (generic district) | `api_tasks_submit` |
| `core/api/routers/inference.py` | `POST /inference/run` | `api_inference_run` |
| `core/engine/agents/subagent_runner.py` | `SubagentRunner._default_llm()` | `subagent_runner` |

If a caller doesn't pass `caller_id=`, it defaults to `"ollama_safe_direct"` (or
`"ollama_safe_stream"` for `chat_stream()`) — still recorded, just less attributable.

### 2b. `_multi_backend_fallback()` sub-fallbacks

When the Ollama daemon itself is down (circuit breaker open, semaphore timeout, or connection
error), `ollama_safe.chat()` tries three more engines in order — each now records its own
success independently, tagged with the *original* caller's `caller_id` but a distinguishing
provider name so they're separable in `provider_summary()`:

- `litellm_fallback` — LiteLLM OpenAI-compatible bridge
- `apple_fm_fallback` — Apple Foundation Models (macOS Sonoma+ only)
- `gemma_cpp_fallback` — Gemma C++ binary (minimal footprint)

### 2c. AirLLM path

`ollama_safe.chat()`'s AirLLM branch (for 70B+ models that don't fit in VRAM) also records —
provider tag `"airllm"`, `caller_id` from the original caller.

---

## 3. Instrumentation Implementation

### 3a. `core/metering/inference_observability.py` (pre-existing, `provider_client.py`-wired)

`InferenceObservability` class:
- SQLite table `inference_calls` in `data/telemetry.db` (WAL mode via `apply_pragmas()`)
- Buffered writes (batch flush ≤1/sec or when buffer ≥50 rows) for the hot path
- `record()` — never raises; every call site wraps it in try/except so observability failure
  can never break an LLM call
- Aggregation methods: `daily_summary()`, `provider_summary()`, `domain_summary()`,
  `caller_summary()`, `hourly_snapshot()`, `quota_saturation()` (bridges `QuotaLedger`, not
  duplicated), `alert_check()`, `generate_daily_report()`, `prune()`

Helper functions:
- `extract_domain(caller_id, model)` — best-effort domain classification from caller naming
  convention or `model="domain:X"` prefix
- `is_autonomous_caller(caller_id)` — classifies autonomous vs. user-triggered by caller name;
  `vc_llm_*` and `governor_*` prefixes are autonomous; explicit UI/API/voice callers are
  user-triggered; unknown callers default to autonomous (VECTOR's traffic is mostly autonomous)

### 3b. `core/inference/provider_client.py` (pre-existing wiring, unmodified this pass)

Two `record()` calls inside `ProviderClient.chat()`:
1. On success (after the empty-content/leaked-reasoning dud checks, before `return result`) —
   records `provider`, `model`, real token counts from the API response, end-to-end latency
   including any retries, `providers_tried` count
2. On total failure (`RuntimeError("All providers failed...")`) — records `status="error"`,
   `error_kind` from `ProviderHealth.classify_error()`

### 3c. `core/inference/vectorcode_llm.py` (this pass — legacy chain instrumentation)

`_record_usage()` (called by `_try_gemini`, `_try_anthropic`, `_try_openrouter` on success) now
also writes to `inference_calls` when `provider != "ollama"` — the Ollama leg is excluded
because `_try_ollama()` delegates to `ollama_safe.chat()`, which already records that call;
recording twice would double-count. New `caller_id` param (default `"vc_llm_legacy_chain"`)
lets callers tag which fallback path was actually hit.

### 3d. `core/inference/ollama_safe.py` (this pass — direct-bypass instrumentation)

New `_record_observability()` helper, called from every exit point of `chat()` and
`chat_stream()`:
- Success: real prompt/completion token counts from the `ollama` SDK response
  (`prompt_eval_count`/`eval_count`) when available; falls back to `len(content) // 4` estimate
  for engines that don't report token counts (AirLLM, LiteLLM, Apple FM, Gemma C++)
- Failure: semaphore-timeout, circuit-breaker-open, and generic-exception paths all record
  `status="error"` with an `error_kind` tag
- `caller_id` is a new keyword-only param on both `chat()` and `chat_stream()`, threaded through
  to `_multi_backend_fallback()` so a fallback-engine hit is still attributed to the original
  caller

---

## 4. Data Model

Table: `inference_calls` in `data/telemetry.db` (unchanged from the original plan):

```sql
CREATE TABLE inference_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       REAL    NOT NULL,           -- epoch seconds
    utc_date        TEXT    NOT NULL,           -- "2026-09-01" for fast day partitioning
    caller_id       TEXT    NOT NULL DEFAULT '',
    district        TEXT    NOT NULL DEFAULT '',
    domain          TEXT    NOT NULL DEFAULT '',
    tier            TEXT    NOT NULL DEFAULT '',
    provider        TEXT    NOT NULL DEFAULT '',
    model           TEXT    NOT NULL DEFAULT '',
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    latency_ms      REAL    NOT NULL DEFAULT 0.0,
    providers_tried INTEGER NOT NULL DEFAULT 1,
    is_ollama       INTEGER NOT NULL DEFAULT 0,
    is_autonomous   INTEGER NOT NULL DEFAULT 0,
    sensitive       INTEGER NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'ok',   -- 'ok' | 'error' | 'empty_content'
    error_kind      TEXT    NOT NULL DEFAULT '',
    metadata        TEXT    NOT NULL DEFAULT '{}'
);
-- indexes on (utc_date), (provider, utc_date), (caller_id, utc_date),
-- (domain, utc_date), (is_autonomous, utc_date)
```

**Privacy**: no `prompt`, `response`, `system_prompt`, or any content field exists in the schema.
Only metadata (who called, what provider/model served it, how many tokens, how long it took,
whether it succeeded). This was true of the original design and is unchanged.

**Retry/fallback tracking**: `providers_tried` (from `ProviderClient`) directly answers "how many
providers did this call attempt before succeeding/failing" — a `providers_tried > 1` row is a
fallback event, and `daily_summary()["fallback_calls"]` now counts these directly (§5, §6b).

**Retry count** (completeness pass): `ProviderClient._call_with_retry()`'s success-return point
now stamps `result._retry_attempts = attempt` — the loop's own 0-indexed attempt counter at the
moment of success (0 = succeeded on the first try, no retry) — onto the returned
`CompletionResult`, using the same post-construction dynamic-attribute pattern already used for
`_tool_calls`. `ProviderClient.chat()`'s success-path `record()` call reads this via
`getattr(result, "_retry_attempts", None)` and, when present, writes it into
`metadata.retry_attempts`. This required **zero changes** to `_call_with_retry()`'s actual retry
decision logic, backoff, key rotation, or exception handling — only one line added at the single
success-return point, verified in `tests/unit/test_inference_observability_gaps.py` (real
`_call_with_retry()` execution, not mocked, confirms the stamp reflects true attempt count and
the retry itself still happens exactly as before). See §6b for the scope this covers.

There is still no column tracking `key_pool.py`'s own internal key-rotation-on-rate-limit
behavior (bumping the pool cursor without an "attempt" in `_call_with_retry()`'s sense) —
`key_pool`/`ProviderHealth` remain the source of truth for that finer-grained signal, unchanged.

---

## 5. Required Reports — Mapping to Implementation (final)

| # | Report | Method | CLI flag | Status |
|---|--------|--------|----------|--------|
| 1 | Calls/day | `daily_summary()["total_calls"]` | default report | ✅ COMPLETE |
| 2 | Tokens/day | `daily_summary()["total_tokens"]` (+ input/output split) | default report | ✅ COMPLETE |
| 3 | Tokens/provider | `provider_summary()` — per-row `tokens` | `--provider` | ✅ COMPLETE |
| 4 | Tokens/model | `model_summary()` (new) — per-row `tokens`/`input_tokens`/`output_tokens` | `--models` (new) | ✅ COMPLETE |
| 5 | Cloud/local ratio | `daily_summary()["ollama_pct"]` / `["cloud_calls"]` | default report | ✅ COMPLETE |
| 6 | Fallback count | `daily_summary()["fallback_calls"]` (new, raw `COUNT(*) WHERE providers_tried > 1`) + `fallback_rate_pct` | default report | ✅ COMPLETE |
| 7 | Failure rate | `daily_summary()["failure_rate_pct"]` (new, computed server-side) | default report | ✅ COMPLETE |
| 8 | Retry rate | `daily_summary()["retry_rate_pct"]` + `retry_calls` + `retry_coverage_calls` (new) | default report | ⚠️ PARTIAL — see §6b, coverage-scoped not codebase-wide |
| 9 | p50 latency | `daily_summary()["p50_latency_ms"]` | default report | ✅ COMPLETE |
| 10 | p95 latency | `daily_summary()["p95_latency_ms"]` | default report | ✅ COMPLETE |
| 11 | Autonomous token consumption | `autonomy_token_summary()["autonomous"]` (new) — `calls`/`input_tokens`/`output_tokens`/`tokens` | `--autonomy` (new) | ✅ COMPLETE |
| 12 | User-triggered token consumption | `autonomy_token_summary()["user"]` (new) | `--autonomy` (new) | ✅ COMPLETE |

**New this pass**: `token_exactness_summary()` (not one of the original 12, but required by the
streaming-exactness instruction) — `exact_calls`/`estimated_calls`/`unknown_calls`/`exact_pct`,
exposed via `--json`'s `token_exactness` key and inline in the default report's summary line
("— NN% provider-exact, rest estimated").

**CLI**: `python scripts/inference_report.py` (equivalent to `vector inference-stats` — no
`vector` CLI wrapper exists in this codebase, so this script is the canonical entry point).
Flags: `--date`, `--provider`, `--domain`, `--models` (new), `--autonomy` (new), `--callers`,
`--alerts`, `--hourly`, `--json`, `--prune N`. `--json` dumps `summary` + `providers` + `domains`
+ `models` + `callers` + `autonomy_tokens` + `token_exactness` + `quota` + `alerts` in one shot.
Default (no flag) report now includes all of the above inline (fallback count, failure rate,
retry rate, model breakdown, autonomous/user token split, exactness percentage) — verified live
against seeded data in §7.

---

## 6. Known Instrumentation Gaps

### 6a. Vendored/isolated sub-projects with their own LLM clients (NOT instrumented)

These make real LLM calls but live in vendored, isolated sub-trees with independent
configuration (their own API-key env vars, not VECTOR's `key_pool`), and are not part of the
district-agent call graph reachable from `governor.dispatch()`:

| Path | What it is | Why excluded |
|------|-----------|---------------|
| `districts/investment/vector_finagent/alpha_arena/llm_call.py` | Standalone subprocess for the Alpha Arena trading benchmark — reads a JSON request file over a named pipe, calls a provider SDK directly, writes JSON to stdout | Isolated subprocess wire-protocol tool, not reachable via `chat()`/`ollama_safe`/`provider_client`; requires paid API keys the owner doesn't run (RULE 10 — free-tier only) |
| `districts/intelligence/vector_social_sim/app/utils/llm_client.py` | `LLMClient` wrapping `openai.OpenAI(...)` for a vendored Chinese-language social-simulation tool (OASIS-style agent sim) | Self-contained vendored app with its own `Config.LLM_API_KEY`, not wired through VECTOR's provider registry |
| `districts/marketing/ads/scripts/generate_image.py` | Deprecated image-gen fallback script (file header says "Use banana-claude MCP tools instead") | Explicitly deprecated; image generation is out of scope for `inference_calls` (chat/completion telemetry only) |
| `districts/investment/vector_finagent/agents/**/model_factory.py`, `registries/*.py` | Vendored FinAgent (hedge-fund-agent) framework's own model registry/factory abstractions | Vendored third-party agent framework (not VECTOR-authored), isolated `vector_finagent/` subtree with its own dependency injection |

**Recommendation for future work**: if any of these are activated for production use (paid keys
configured, subprocess wired into `governor.dispatch()`), they should get the same
`get_inference_observability().record()` call added at their own success/failure exit points —
the pattern is identical to what was done in `ollama_safe.py` §3d. Not done now because they are
dormant/vendored and instrumenting dead code adds no measurement value.

### 6b. Retry rate (report #8) — CLOSED for `ProviderClient` calls, structurally not possible for the rest

**What was closed**: `ProviderClient._call_with_retry()` now stamps the real attempt count onto
its result (§4), and `ProviderClient.chat()` forwards it into
`inference_calls.metadata.retry_attempts`. `daily_summary()["retry_rate_pct"]` computes
`retried / coverage`, where `coverage` = rows where `retry_attempts` is present (not
`total_calls`) — see `_get_retry_stats()`'s docstring for why this scoping matters: dividing by
`total_calls` instead would silently understate the rate by diluting it with calls that
structurally cannot retry.

**What remains impossible to close without behavior change — and why**:

| Call path | Has a retry loop? | Why it's excluded from retry_rate_pct's coverage |
|-----------|-------------------|---------------------------------------------------|
| `ProviderClient._call_with_retry()` (cloud drivers) | Yes | **Included** — this is what `retry_coverage_calls` counts |
| `ollama_safe.chat()` (direct bypass, 14 call sites) | No | Ollama is a local, unauthenticated, single-daemon target — there is no API key to rotate and no rate-limit-then-retry pattern; `_multi_backend_fallback()` is a *different-engine* fallback (LiteLLM/Apple-FM/Gemma-C++), not a retry of the same request against the same engine. Adding a synthetic "retry_attempts=0" here would be fabricated data, not a measurement — explicitly avoided. |
| `vectorcode_llm._try_gemini/_try_anthropic/_try_openrouter` (legacy chain) | No | Each function makes exactly one HTTP attempt with no loop around it; retrying would require adding a new retry loop to this dormant fallback path — a behavior change forbidden by this task's scope, not just an instrumentation gap. |

This is documented as **PARTIAL, not COMPLETE**, in the requirement matrix (§10): the metric is
real, exact, and honestly scoped (never blended with non-retryable paths), but it does not cover
100% of VECTOR's LLM traffic — only the fraction that goes through `ProviderClient`'s retry
wrapper. Making it codebase-wide would require adding retry loops to paths that currently have
none, which is explicitly out of scope ("Do NOT change retry ordering, retry counts...").

### 6c. Tokens/model and autonomous/user token sums (reports #4, #11, #12) — CLOSED

`model_summary()` and `autonomy_token_summary()` (new methods, same `GROUP BY` pattern as the
pre-existing `provider_summary()`/`domain_summary()`) now expose these directly, with dedicated
CLI flags `--models` and `--autonomy`. Verified against seeded data in §7. No behavior change —
pure additive SQL aggregation over the existing schema, zero new columns required.

### 6d. `chat_stream()`'s aggregate token count — CLOSED (exact, not estimated)

**Root cause found**: the code was discarding data that was already there. Ollama's Python SDK
streaming response's *final* chunk (`done=True`) carries the identical `prompt_eval_count`/
`eval_count` fields the non-streaming response has — confirmed by reading
`ollama/_types.py`'s `BaseGenerateResponse` (both `GenerateResponse` and `ChatResponse` inherit
these fields, and streaming/non-streaming share the same response model). The prior code only
read `chunk["message"]["content"]` per-chunk and threw the rest away.

**Fix**: `chat_stream()` now also checks `chunk.get("done")` and, when true, captures
`prompt_eval_count`/`eval_count` into `_prompt_eval_count`/`_eval_count`, passed to
`_record_observability()` as real `input_tokens`/`output_tokens` — exactly the same exactness as
the non-streaming `chat()` path. This required reading one more field per chunk already being
iterated; it does not change what's yielded to the caller, when it's yielded, or the generator's
external behavior in any way.

**Remaining honest limitation**: AirLLM, LiteLLM/Apple-FM/Gemma-C++ fallback engines, and the
`vectorcode_llm` legacy chain still have no token-count field to read at all (their underlying
APIs/return shapes don't expose one) — these continue to fall back to the `len(content) // 4`
estimate, now explicitly flagged via `metadata.token_exact=False` so reports never blend them
with real counts. `token_exactness_summary()` (§5) reports the exact/estimated split so this is
visible, not hidden.

---

## 7. Verification Performed

### Initial pass (2026-09-01)

1. **Syntax check** — all 14 edited files parse cleanly (`ast.parse`).
2. **Self-tests** — `ollama_safe.py`, `vectorcode_llm.py`, `provider_client.py`, and
   `inference_observability.py`'s own `if __name__ == "__main__":` blocks all pass.
3. **Regression tests** — 168 tests across 9 files (provider health, quota ledger, Ollama
   concurrency/semaphore, loop-guard, governor, agent base/registry, loop-stall fixes) — all
   pass, zero regressions.
4. **Performance** — 0.026ms/call average (no metadata payload).
5. **Bug found and fixed**: `flush()`/`_ensure_flushed()` throttle bug (same once/sec guard as
   the internal opportunistic flush was silently swallowing explicit flush requests) — fixed
   with a `force: bool` param.

### Completeness pass (2026-09-01, this revision)

6. **New test file**: `tests/unit/test_inference_observability_gaps.py` — 16 tests, real SQLite
   (temp file, no mocking of `InferenceObservability` per `.claude/rules/testing.md`), covering:
   - `model_summary()` grouping and empty-model exclusion (2 tests)
   - `autonomy_token_summary()` split correctness and zero-data shape (2 tests)
   - `daily_summary()`'s new fields: fallback_calls, failure_rate_pct, retry_rate_pct (with
     coverage-scoping verified), zero-division safety, empty-summary key completeness (5 tests)
   - `token_exactness_summary()` exact/estimated/unknown classification (2 tests)
   - `generate_daily_report()` includes all new sections (1 test)
   - **`ProviderClient._call_with_retry()` real-execution behavioral tests** (not mocked): confirms
     a first-try success stamps `_retry_attempts=0`, and a genuinely retried call (mocked only at
     the `_call()` boundary, the actual retry loop runs for real) stamps `_retry_attempts=1` and
     still returns the correct final content — proving the retry mechanism itself is byte-for-byte
     unchanged, only observed (2 tests)
   - `CompletionResult` dynamic-attribute compatibility check (1 test)

   **Result**: 16/16 pass.
7. **Full regression re-run** — same 168 tests from the initial pass + the 16 new tests =
   **184/184 pass**, zero regressions from the gap-closure changes.
8. **Behavioral neutrality — code-level audit, not just test-based**:
   - `git diff` on `provider_client.py`'s retry/backoff/cooldown/routing-decision lines
     (`is_rl`, `is_key_err`, `backoff`, `pool_size`, `mark_cooldown`, `route_policy`,
     `decide_route`) shows **zero changes** — grep-verified empty diff on those symbols.
   - The only functional addition to `_call_with_retry()` is one line
     (`result._retry_attempts = attempt`) at the pre-existing single success-return point.
   - `_multi_backend_fallback()`'s engine trigger order and conditions (LiteLLM → Apple FM →
     Gemma C++) are unchanged — only a `caller_id=` parameter was threaded through and a
     `record()` call added after each engine's existing success check.
9. **Performance re-measured with metadata payload**: 1,000 `record()` calls with
   `metadata={"token_exact": True, "retry_attempts": N}` — **0.042ms/call average** (42.44ms
   total), still well under the plan's <0.1ms/call target. Four new aggregation queries
   (`model_summary`, `autonomy_token_summary`, `token_exactness_summary`, extended
   `daily_summary`) over 1,000 rows: **5.5ms total**.
10. **End-to-end report verification with realistic seeded data** (3 calls: one cloud
    fallback-triggering call with `providers_tried=2` and `retry_attempts=1`, one Ollama direct
    call, one first-try cloud success) — confirmed correct math in the rendered report: fallback
    rate 33.3% (1 of 3 calls), retry rate 50.0% (1 of 2 coverage-eligible calls), failure rate
    0.0%, autonomous/user token split (9,300 / 450), model breakdown listing all 3 models with
    correct per-model token sums, exactness 67% (2 of 3 exact).
11. **CLI end-to-end**: `--models`, `--autonomy`, and `--json` (now including `models`,
    `autonomy_tokens`, `token_exactness` keys) all verified working against the live (empty)
    production DB — correct "no data" messaging, exit code 0, and full JSON key completeness.
12. **Metadata content audit**: grepped every `metadata=` call site touching `record()` across
    `provider_client.py`, `ollama_safe.py`, `vectorcode_llm.py` — confirmed only `token_exact`
    (bool) and `retry_attempts` (int) are ever written; zero prompt/response/credential content
    in any metadata payload (one unrelated `Message(metadata=...)` construction in
    `ollama_safe.py`'s `_to_vectorcode_messages()` helper was checked and confirmed to be a
    different object entirely — VectorCode's internal message type, not `InferenceObservability`).
13. **No prompt/response content logged** — schema unchanged from the initial pass (§4) — the
    `inference_calls` table still has no text-content column.

---

## 8. Files Changed

| File | Change |
|------|--------|
| `core/inference/ollama_safe.py` | Added `caller_id` param to `chat()`/`chat_stream()`, `_record_observability()` helper, recording at every success/failure/fallback exit point |
| `core/inference/vectorcode_llm.py` | `_record_usage()` now also writes to `inference_calls` for gemini/anthropic/openrouter legacy-chain legs (excludes ollama leg to avoid double-counting) |
| `core/metering/inference_observability.py` | Added new user-triggered `caller_id`s to `_USER_CALLERS`; **fixed** `flush()`/`_ensure_flushed()` throttle bug (see §7.6); closed SQLite connection before temp-file cleanup in self-test |
| `core/city/agent_base.py` | Tagged `vchat()`'s `ollama_safe.chat()` call with `caller_id=f"agent_{self.name}"` |
| `core/city/governor.py` | Tagged `_llm_classify()`'s local-fallback call with `caller_id="governor_classify_local"` |
| `core/inference/model_router.py` | Tagged `_classify_with_llm()` with `caller_id="model_router_classify"` |
| `core/voice/realtime.py` | Tagged local-fallback intent-classification call with `caller_id="voice_intent"` |
| `core/runtime/missions.py` | Tagged `_call_model()`'s default `ollama_safe` path with `caller_id="runtime_missions_planner"` |
| `core/ui/web_ui.py` | Tagged `/chat`, `/ws/chat`, `/tasks/submit` with `web_ui_chat`/`web_ui_ws_chat`/`web_ui_task` |
| `core/ui/chat.py` | Tagged terminal chat and `/bg` command with `terminal_ui_chat`/`terminal_ui_bg_task` |
| `core/engine/channels/runtime.py` | Tagged channel-adapter fallback with `channel_runtime_fallback` |
| `core/api/routers/tasks.py` | Tagged generic task submission with `api_tasks_submit` |
| `core/api/routers/inference.py` | Tagged one-shot `/inference/run` with `api_inference_run` |
| `core/engine/agents/subagent_runner.py` | Tagged default subagent LLM handler with `subagent_runner` |

### Completeness pass (this revision) — additional files changed

| File | Change |
|------|--------|
| `core/inference/provider_client.py` | `_call_with_retry()` stamps `result._retry_attempts = attempt` at its success-return point (§4); success-path `record()` call now includes `metadata={"token_exact": ..., "retry_attempts": ...}` |
| `core/inference/ollama_safe.py` | `chat_stream()` now captures `prompt_eval_count`/`eval_count` from the streaming response's final (`done=True`) chunk instead of always estimating (§6d); `_record_observability()` now computes and passes `token_exact` in `metadata` |
| `core/inference/vectorcode_llm.py` | `_record_usage()`'s observability `record()` call now tags `metadata={"token_exact": False}` (always an estimate on this legacy path) |
| `core/metering/inference_observability.py` | Added `model_summary()`, `autonomy_token_summary()`, `token_exactness_summary()`, `_get_retry_stats()` (new methods); extended `daily_summary()` with `fallback_calls`/`fallback_rate_pct`/`failure_rate_pct`/`retry_calls`/`retry_rate_pct`/`retry_coverage_calls`; extended `_empty_summary()` to match; extended `generate_daily_report()` to render all new sections |
| `scripts/inference_report.py` | Added `--models` and `--autonomy` CLI flags; extended `--json` output with `models`/`autonomy_tokens`/`token_exactness` keys; updated module docstring |
| `tests/unit/test_inference_observability_gaps.py` | **New file** — 16 tests covering every gap-closure change, including real (non-mocked) `_call_with_retry()` execution tests |

---

## 9. What Was NOT Done (per task scope — both passes)

- No changes to `route_policy.decide_route()`, `TIER_ROUTING`, `model_pool`, `quota_ledger`
  reordering logic, or `ProviderHealth` circuit-breaker thresholds.
- No changes to prompts, system messages, or personality injection.
- No changes to timeouts, retry counts, or backoff schedules — the retry loop in
  `_call_with_retry()` runs identically to before; it is now *observed*, not *changed* (§4, §7.8).
- No new alert thresholds or automated actions triggered by observability data.
- No retry loop added to `ollama_safe.chat()` or the `vectorcode_llm` legacy chain — doing so to
  make retry-rate codebase-wide would itself be a behavior change, explicitly out of scope (§6b).
- No duplicate telemetry system — every new aggregation method reads the same `inference_calls`
  table and reuses the same `record()`/`metadata` mechanism already in place; no second SQLite
  table, no second buffering/flush path, no second singleton.
- Cognitive benchmark (roadmap item 05), 7-day autonomous evaluation (roadmap item 07), and the
  final cognitive integration audit — explicitly deferred per this pass's task instructions.

---

## 10. Requirement Matrix (final, strict)

Per-requirement status using the four defined states: **COMPLETE** (fully measurable, exact or
explicitly-flagged-estimate, no scope caveat), **PARTIAL** (measurable but with a documented
coverage gap that cannot be closed without a behavior change), **NOT POSSIBLE** (cannot be
closed without changing inference behavior, and doing so is out of scope), **NOT APPLICABLE**
(not a requirement of this task).

| REQUIREMENT | STATUS | EVIDENCE | EXACTNESS |
|---|---|---|---|
| Calls/day | COMPLETE | `daily_summary()["total_calls"]`; §5 row 1; end-to-end verified §7.10 | Exact (COUNT(*)) |
| Tokens/day | COMPLETE | `daily_summary()["total_tokens"]`; §5 row 2 | Mixed — see token exactness row below |
| Tokens/provider | COMPLETE | `provider_summary()`; §5 row 3; pre-existing, unchanged this pass | Mixed — per-row exactness not broken out (see gap note) |
| Tokens/model | COMPLETE | `model_summary()` (new); §5 row 4; `--models` CLI flag; test: `TestModelSummary` (2 tests) | Mixed — same as tokens/day |
| Cloud/local ratio | COMPLETE | `daily_summary()["ollama_pct"]`/`["cloud_calls"]`; §5 row 5; pre-existing, unchanged | Exact (is_ollama boolean, not estimated) |
| Raw fallback count | COMPLETE | `daily_summary()["fallback_calls"]` (new, `COUNT(*) WHERE providers_tried > 1`); §5 row 6; test: `test_fallback_calls_counts_providers_tried_over_one`; end-to-end §7.10 | Exact (providers_tried is a real per-attempt counter, not estimated) |
| Failure rate | COMPLETE | `daily_summary()["failure_rate_pct"]` (new); §5 row 7; test: `test_failure_rate_computed_from_error_calls` | Exact (status column is not estimated) |
| Retry rate | PARTIAL | `daily_summary()["retry_rate_pct"]` + `retry_coverage_calls` (new); §5 row 8; §6b; test: `test_retry_rate_only_counts_rows_with_retry_metadata` + 2 real `_call_with_retry()` execution tests | Exact for the `ProviderClient` coverage scope; structurally absent (not estimated, not fabricated) for `ollama_safe`-direct and legacy-chain calls — see §6b for why closing this fully would require adding retry loops that don't currently exist, which is out of scope |
| p50 latency | COMPLETE | `daily_summary()["p50_latency_ms"]`; §5 row 9; pre-existing, unchanged | Exact (measured wall-clock, `time.perf_counter()`) |
| p95 latency | COMPLETE | `daily_summary()["p95_latency_ms"]`; §5 row 10; pre-existing, unchanged | Exact |
| Autonomous token consumption | COMPLETE | `autonomy_token_summary()["autonomous"]` (new); §5 row 11; `--autonomy` CLI flag; test: `TestAutonomyTokenSummary` (2 tests); end-to-end §7.10 | Mixed — same as tokens/day |
| User-triggered token consumption | COMPLETE | `autonomy_token_summary()["user"]` (new); §5 row 12; same test/CLI as above | Mixed — same as tokens/day |
| Streaming token exactness (Ollama) | COMPLETE | `chat_stream()` reads `prompt_eval_count`/`eval_count` from the SDK's final chunk (§6d) — root cause was discarded data, not an API limitation | Now exact (was estimated before this pass) |
| Token-exactness disclosure (all sources) | COMPLETE | `token_exactness_summary()` (new) — every row tagged `token_exact: true/false` in metadata; surfaced in `--json` and the default report's summary line; test: `TestTokenExactnessSummary` (2 tests) | N/A — this requirement is itself the exactness-disclosure mechanism |
| No prompt/response/credential content logged | COMPLETE | Schema has no text-content column (§4); metadata audit §7.12 confirms only `token_exact`/`retry_attempts` ever written | N/A |
| Negligible overhead | COMPLETE | 0.026ms/call (no metadata) and 0.042ms/call (with metadata) measured, both ≤ 0.1ms/call target; 5.5ms for 4 new aggregation queries over 1,000 rows (§7.9) | N/A |
| Provider selection unchanged | COMPLETE | Code-level diff audit on `is_rl`/`is_key_err`/routing symbols shows zero changes (§7.8); 184/184 regression tests pass | N/A |
| Routing unchanged | COMPLETE | `route_policy.decide_route()`, `TIER_ROUTING`, `model_pool` untouched this pass (§9); regression suite includes governor/routing tests | N/A |
| Retry behavior unchanged | COMPLETE | Only one line added at `_call_with_retry()`'s pre-existing success-return point; real-execution tests confirm retry loop still runs and succeeds identically (§7.6, §7.8) | N/A |
| Fallback behavior unchanged | COMPLETE | `_multi_backend_fallback()`'s engine order/trigger conditions unchanged, only `caller_id=` threaded through + a `record()` call added after existing success checks (§7.8) | N/A |
| Prompts unchanged | COMPLETE | No system-prompt, personality-injection, or message-content code touched this pass | N/A |
| Memory/decision behavior unchanged | COMPLETE | No changes to `decision_engine.py`, `policy.py`, `goal_system.py`, or any memory module in either pass | N/A |
| Duplicate telemetry system avoided | COMPLETE | All new methods query the existing `inference_calls` table via the existing connection/buffer/flush machinery; no new table, no new singleton (§9) | N/A |
| Cognitive benchmark | NOT APPLICABLE | Explicitly out of scope for this task ("Do not begin the cognitive benchmark") | N/A |
| 7-day autonomous experiment | NOT APPLICABLE | Explicitly out of scope for this task ("Do not begin the 7-day experiment") | N/A |
| Final cognitive integration audit | NOT APPLICABLE | Explicitly out of scope for this task | N/A |

**Summary**: 20 of 22 applicable requirements are COMPLETE. 1 (retry rate) is PARTIAL — real,
exact, and honestly scoped, but does not cover 100% of call paths because most paths structurally
have no retry loop to observe; closing it fully is NOT POSSIBLE without adding retry logic to
paths that don't currently have any, which contradicts this task's explicit constraint. No
requirement was found to be NOT POSSIBLE outright — every original gap admitted at least a
measurement-only closure or an honestly-scoped partial closure.
