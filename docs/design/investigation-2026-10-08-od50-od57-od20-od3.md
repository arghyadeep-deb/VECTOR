# Investigation: OD-50, OD-57, OD-20, and OD-3

**Date:** 2026-10-08  
**Scope:** Fresh source, import, caller, test, and git-history verification of the four requested backlog items. No production code or disposition was changed.

Caller counts below exclude the implementation's own examples/`__main__` block, documentation, audit scripts, and tests unless stated otherwise. A direct `python -B` import check resolved all five investigated modules at their current paths. The focused `tests/test_vectorcode_remaining_round1_regressions.py` suite also passed (`9 passed`); its permission tests are discussed under OD-3.

## OD-50 — `vectorcode/src/gateway/ws.py`

### What it implements

`ws.py` is a small, independent FastAPI WebSocket adapter, not a WebSocket mode inside `GatewayServer`. `create_ws_route(app, path="/ws")` accepts a socket and constructs `VectorWSHandler`; the handler understands three client messages (`run`, `interrupt`, and `approve`) and emits `token`, `tool_call`, `tool_result`, `done`, `error`, and `approval_request` messages. A run constructs `engine.agent_loop.VectorAgent`, executes its synchronous `run_conversation()` in the default thread executor, then replays the completed response and recorded tool calls over the socket. `request_approval()` creates an in-memory future and rejects after 30 seconds if no matching `approve` message arrives.

Its advertised “real-time streaming” is therefore not real token streaming. The source explicitly says the entire agent run completes first and the full answer is sent as one `token` frame followed by `done`. `interrupt` also cannot cancel the executor work: the receive loop is awaiting `_handle_run()` while the run executes, so it cannot process an interrupt frame concurrently, and the worker itself receives no cancellation signal. The approval facility is similarly only a transport helper; the constructed `VectorAgent` is not given `request_approval()` as its approval callback. The protocol describes a `model` and `session_id`, but it does not retain conversation history between runs, and the client-supplied `session_id` is only echoed in frames rather than used when constructing the agent.

The implementation is compatible with the older synchronous `vectorcode/src/engine/agent_loop.py::VectorAgent` return shape (`response`, `tool_calls`, `iterations`, `session_id`), but its tool-event projection is incomplete: the agent loop records `tool_call_id` and `name` with a result, whereas `ws.py` looks for `id`, `args`, and `output`. Consequently, call IDs/arguments/output can be empty even when tools ran. This is not parity with the current REST gateway, which uses the main `run_agent.AIAgent`, preserves per-session history, exposes session/status/cancel/compact/reset/model operations, and has both synchronous `/run` and SSE `/stream` endpoints.

### Reachability and history

Fresh repository search found **zero production callers/importers** of `create_ws_route`, `VectorWSHandler`, `WSMessage`, or `vectorcode.src.gateway.ws` outside the module itself. The similarly named live `vectorcode/src/tui_gateway/ws.py` and `vectorcode/src/server/ws_bridge.py` are separate implementations; the latter is mounted by `server/api_routes.py` and has its own focused authentication test. They do not reach this file.

The file first appeared on 2026-05-14 (`01d505a4d`), passed through the May 15 de-absorption commit (`122179713`), and last changed in the broad May 30 test commit (`86ca442f1`). There is no recent wiring work. Commit `85f484e62` fixed `gateway/server.py` only: network-accessible REST bindings now require a usable `VECTOR_GATEWAY_KEY`, configured HTTP routes require a constant-time Bearer-token check, and unauthenticated loopback remains explicitly allowed. None of that protects `ws.py`. FastAPI HTTP middleware does not provide the needed WebSocket handshake enforcement, and `create_ws_route()` currently accepts every connection before checking any credential.

### Delete loss versus wiring cost

Deleting this file would lose only an unwired protocol sketch: a one-shot socket wrapper, an unused approval-future mechanism, and its self-test. It would not remove the live TUI WebSocket or server event bridge, and REST `/stream` already covers one-way incremental delivery without a persistent bidirectional client.

Wiring it safely would require more than calling `create_ws_route()` from `GatewayServer.build_app()`: WebSocket-specific Bearer/query/subprotocol authentication with `hmac.compare_digest`; the same network-bind/secret policy as `server.py`; origin policy; session ownership and history integration; concurrent receive/run tasks so interrupt and approval can arrive during work; actual cancellation propagation; wiring approval requests into the agent's real permission callback; bounded message/input sizes and connection/session limits; corrected tool-event mapping; cleanup of pending futures/tasks on disconnect; and tests for unauthorized handshake, session isolation, interruption, approvals, and disconnects. A product client that needs bidirectional approvals/interrupts would justify that work. A client that only needs request/response or output streaming should use the existing REST/SSE gateway instead.

**Recommendation:** **Retire `vectorcode/src/gateway/ws.py`**, rather than wiring it opportunistically. It has zero callers, duplicates two live WebSocket surfaces plus REST/SSE, and its differentiating promises (mid-run approval, interrupt, token streaming) are not actually connected. Keep it only if the owner has a concrete external client requiring one persistent bidirectional agent session; in that case replace the sketch with an authenticated route integrated into `GatewayServer` and its canonical session/permission machinery, not a parallel third gateway.

## OD-57 — `SubagentRunner` and `ReliableProvider`

### Current locations and caller counts

The backlog paths are still current after the earlier moves:

- `core/engine/agents/subagent_runner.py`
- `core/engine/providers/reliable_provider.py`

Fresh search found **zero production callers** constructing `SubagentRunner` or calling the `run_subagent()` convenience function. Two focused tests in `tests/test_core_engine_memory_voice_audit_regressions.py` exercise hydration/default-LLM and prompt behavior, and `scripts/audit_wiring.py` constructs it as an audit probe; neither makes it a runtime path.

Fresh search also found **zero production constructors/callers of the `ReliableProvider` class**. However, the file is not wholly dormant: live `core/inference/provider_client.py::_call_with_retry()` imports `is_non_retryable`, `is_rate_limited`, and `parse_retry_after_ms` from it. `core/engine/providers/__init__.py` re-exports the class and `ProviderError`, but no production consumer imports that facade. The correct count is therefore “class: zero; module helper consumer: one,” not “whole file: zero.”

### `SubagentRunner`: actual capability and overlap

`SubagentRunner` builds a hydrated system prompt from `ContextEngine().session_hydration_prompt()`, a named role from `core.engine.agents.roles`, an informational allowed-tools list, and optional parent context. It then makes exactly **one** awaited LLM call under `asyncio.wait_for()` and returns a `SubagentOutcome`. Its default callable directly invokes `ollama_safe.chat()`; injected callables receive `(system_prompt, user_message, allowed_tools)`.

Several advertised fields/capabilities are decorative or overstated. `parent_session_id` is never read. `model_hint` is never read. `max_turns` is never read, and `turns_taken` is always zero. `allowed_tools` is prompt text and a callable argument, not an enforced tool registry or Permission-Gateway boundary. There is no agent loop, tool execution, child-session persistence, retry/fallback routing, interruption, concurrency control, or inherited memory/session state beyond caller-supplied text. It is better described as a role-prompted one-shot completion wrapper than a subagent runner.

The repository already has the genuinely live implementation of this job in `vectorcode/src/tools/delegate_tool.py` plus `run_agent.AIAgent`: `delegate_task` is registered in the main toolsets, creates child agents with isolated context, supports parallel tasks, enforces recursion/depth/concurrency controls, tracks active subagents and lineage, exposes pause/status/interrupt operations to the TUI gateway, maintains file-state coordination, and installs a fail-closed approval callback for subagent tool use. That stack is substantially more capable and actually called. `SubagentRunner` would neither replace nor use it; wiring the former would create a second, weaker delegation model.

Git history agrees with a carried port, not an in-flight replacement. The file says it was ported from `vector`'s Rust subagent runner, was introduced in May (`ea72a1d58`/`23d009b9f6`), and had no feature development after the May test batch until an October 7 hydration/default-LLM correctness fix (`9b79488c9`). That recent fix made dormant code compliant and testable; it did not add a caller.

### `ReliableProvider`: actual capability and overlap

The class is a direct OpenAI-compatible HTTP wrapper. It prepends an optional system message, posts to `/chat/completions`, parses text/token usage into its own `CallResult`, retries with exponential or parsed `Retry-After` delay, rotates a round-robin key on rate limits, and walks a caller-supplied model fallback chain. It classifies context-limit, ordinary non-retryable 4xx, upstream-unhealthy, rate-limit, and quota-shaped errors.

The live `core/inference/provider_client.py::ProviderClient` already performs the durable runtime job and goes far beyond this wrapper: governed route selection, sensitive/local-only and free-tier policy, rate limiting, model-pool/provider cooldown, API-key pooling/rotation, per-provider model selection, retry/backoff, fallback across providers, context compaction, optional personality handling, tool-call normalization, and inference observability. Its `_call_with_retry()` deliberately reuses three classifiers from `reliable_provider.py`, so those small pure helpers complement the live implementation. The class itself would be a regression if substituted: it bypasses `ProviderClient`'s routing policy, hydration expectations at the call site, budget/privacy gates, provider catalog, telemetry, and established key pool.

The class was introduced under `core/openhuman/providers/` in `d3dd9c3e9` (2026-05-17), moved to `core/engine/providers/` during the May 21 cleanup, and has had no substantive post-May evolution. The live `ProviderClient` later absorbed the useful retry-classification helpers rather than adopting the wrapper. This is evidence of partial supersession, not a missing reliability layer.

**Recommendation:** **Retire `SubagentRunner` and its focused tests**; the live `delegate_task`/`AIAgent` stack already supplies the real capability, while this class supplies only a one-shot prompt wrapper with unenforced tool claims. For `ReliableProvider`, **do not delete the module wholesale** because three helper functions have one live production consumer. Move/fold those pure classifiers into the canonical inference layer (or keep a narrowly named helper module), then retire the unused `ReliableProvider`, `CallResult`, and `ProviderError` API and remove the stale re-export. Do not wire the class beside `ProviderClient`.

## OD-20 — `core/trading/graph/checkpointer.py`

### What is persisted in practice

`get_checkpointer()` opens a per-ticker plain `sqlite3` database under `<data_cache_dir>/checkpoints/<TICKER>.db`, applies ordinary pragmas, and passes that connection to LangGraph's `SqliteSaver`, which owns the `checkpoints`/`writes` schema and serializer. The thread ID is a truncated SHA-256 of ticker plus trade date. The helper code reads only LangGraph metadata such as `step`, but LangGraph persists the graph's state/channel values and pending writes, not merely that metadata.

The state originates in `Propagator.create_initial_state()` and is progressively enriched by every graph node. A resumable failed run can therefore contain:

- `messages`: the initial ticker message plus LangChain `AIMessage`/tool-call/tool-result history. This can include model output, public market/news/social/fundamental API results returned through tools, tool names/arguments/IDs, and error text.
- `company_of_interest` and `trade_date`.
- `past_context`: text loaded from `TradingMemoryLog`, including prior same-ticker decisions/outcomes and cross-ticker lessons.
- `market_report`, `fundamentals_report`, `sentiment_report`, and `news_report`: generated analyses derived from price/indicator data, company filings/fundamentals, news, Reddit, and StockTwits content.
- `investment_debate_state`: full bull/bear history, current response, judge decision, and round count; plus the resulting `investment_plan` once produced.
- `trader_investment_plan`: a generated buy/sell/hold transaction proposal. Its typed schema explicitly permits position-sizing text such as “5% of portfolio.”
- `risk_debate_state`: full aggressive/conservative/neutral histories and current responses, final judge text, speaker, and count.
- `final_trade_decision` and `sender` once those nodes run.
- LangGraph checkpoint metadata, version/channel bookkeeping, pending sends/writes, parent/config identifiers, and serialized message objects needed to resume at the next node.

The checkpoint is opt-in (`checkpoint_enabled` defaults to `False`) and is cleared after a successful run. Its main exposure window is precisely an interrupted/crashed run, which is when the richest partial state remains on disk indefinitely until resumed or manually cleared.

### Sensitivity finding

No code path in this graph imports a brokerage account, holdings, cash balance, real order, account identifier, or trading credential into `AgentState`. Data-source API keys configure the clients but are not placed in graph state. The market/fundamental/news/social inputs are public third-party data, and the system is analysis-only. There is therefore no evidence that the checkpoint intentionally stores PII, authentication secrets, or actual account balances/positions.

“Zero sensitive data” is nevertheless too strong. The stored state includes private research history, inferred investment intent, ticker/date watch activity, full model/tool transcripts, prior decision/outcome context, and generated entry/exit and portfolio-percentage guidance. A percentage is normally hypothetical because the graph knows no real balance, but it can still reveal the owner's strategy and intended exposure. Tool/error text is also an open-ended serialization boundary: today the tools return public data, but any future tool added to the graph can place its result in `messages` without changing `checkpointer.py`.

There is an important scope caveat. Successful final state is already written as plaintext JSON under `results_dir`, and final decisions/past lessons are written to the plaintext trading memory Markdown file. Encrypting only crash checkpoints would protect transient full transcripts and unfinished deliberations, but would not make trading analysis at rest generally confidential. Conversely, leaving the checkpoint plaintext because LangGraph owns the schema is an implementation-convenience argument, not a data-classification argument: `SqliteSaver` receives a caller-provided DB-API connection, so schema ownership does not by itself preclude a SQLCipher-compatible connection. Compatibility and migration still need proof with the installed LangGraph serializer/schema before changing it.

Commit `49daef532` did not modify this file; it encrypted five other stores holding direct PII, correspondence, secrets/audit payloads, or schedules. The checkpoint's relevant history is the October 1 resume/correctness fix (`4a15657c5`), which confirms that full node state is intentionally durable and operationally used. Its plaintext status was a scope choice, not evidence that only harmless step counters are stored.

**Recommendation:** **Do not keep the “zero sensitive data / harmless plaintext” rationale. Classify the checkpoint as lower than PII/credentials but still financially sensitive.** Encrypt it if the owner wants local-at-rest protection for trading strategy, and do so as one scoped trading-storage task covering checkpoint DBs, result JSON, and `trading_memory.md`; encrypting only this DB would leave the same decisions exposed elsewhere. If the owner's policy intentionally encrypts only PII/secrets and accepts plaintext local research artifacts, leaving it plaintext is defensible because there is no real account data today—but record that as an explicit policy exception, keep checkpointing opt-in, and add a state-field review gate before any broker/account tool is introduced.

## OD-3 — `vectorcode/src/permissions/__init__.py`

### Reachability, including individual utilities

Fresh search found **zero production imports** of the package, `PermissionSystem`, `PermissionMode`, `PermissionResult`, `_matches_any`, `check_write`, or `check_bash`. No caller imports an individual function/class as a utility. The only Python consumer is `tests/test_vectorcode_remaining_round1_regressions.py`, which imports `PermissionSystem` and verifies three October regression cases; the file's own `__main__` assertions are otherwise self-contained. The TypeScript `vectorcode/packages/core/src/permissions/system.ts` used by the TypeScript agent loop is a different implementation and does not import or execute this Python module.

The passing tests show that the dormant implementation behaves as written; they do not establish production reachability. The focused test file passed in this investigation (`9 passed`, including its three permission tests).

### Capability comparison with the real Permission Gateway

The two systems are not interchangeable implementations of one contract.

The dormant `PermissionSystem` is a synchronous policy predicate over four modes. Reads always pass; read-only blocks all writes/bash; cautious makes writes/bash require approval; standard auto-allows writes but asks for bash; autonomous auto-allows both; destructive/high/critical always require approval. It adds configurable path allow/deny globs using normalized `fnmatch` plus suffix matching, and configurable bash rules using case-insensitive deny-substring and allow-prefix matching. It returns “requires_approval” but has no approval channel, execution path, audit log, action identity, durable pending state, or capability token.

The canonical `core/loop/permission_gateway.py` instead classifies named actions through configured GREEN/YELLOW/RED/FORBIDDEN tiers, performs real async owner/council approval, fails closed for unknown actions, executes explicit handlers, writes durable audit/pending state, preserves provenance, and issues scoped control receipts/tokens. For shell execution it applies `_check_bash_ast()`, which tokenizes POSIX and Windows forms and blocks catastrophic disk/root/system deletion, fetch-piped-to-interpreter RCE, registry-hive deletion, and drive-root ACL takeover. That parser is much more capable than the dormant module's default single `"rm -rf"` substring and does not pretend an allow-prefix makes arbitrary trailing shell safe.

The real gateway does **not** cover 100% of the dormant matcher API. It has no general configurable `allow_write_paths`/`deny_write_paths` fnmatch layer, no arbitrary bash allow-prefix/deny-substring configuration, and no global cautious/standard/autonomous/read-only mode with identical semantics. Its path defenses are capability-specific instead: for example, `safe_vault_note_path()` confines note writes, while file/code/control implementations enforce their own boundaries after a named gateway action is approved. Thus the dormant module contains a genuinely distinct *policy shape*—generic path globs and operator-configurable command patterns.

That difference does not make this module needed. Its generic policy is detached from every real write/shell call, so it protects nothing; wiring it as a second decision point would violate the repository rule that the Permission Gateway is the only authority and would create conflicting outcomes. Its matcher is also not safe enough to promote as-is: allow-bash uses `startswith`, deny-bash is substring-only, paths are string-normalized rather than resolved/confined against an authorized root, reads are unconditionally allowed, unknown modes silently become `standard`, and `standard` auto-allows all non-denied write paths. If configurable path policy is desired, its behavior should be redesigned inside the canonical gateway/tool boundary with resolved-path tests; this file is not a ready missing layer.

### Provenance and intent

Git history identifies a legacy absorbed subsystem, not a planned replacement. The file originated on 2026-05-13 under `agents/districts/coding/vectorcode/permissions/` (`1d007d045`), was bulk-absorbed with Hermes on May 14 (`facd4bd3b`), and moved/debranded in the May 15 absorption cleanup (`122179713`). By contrast, the real Permission Gateway predates it in this repository (introduced April 30 in `641f7d2fc`) and has dozens of subsequent production/security changes through October 7, including recent authorization-boundary fixes. There is no commit connecting the Python `PermissionSystem` to the gateway or describing it as its successor.

The only recent change to the dormant file is `d75eab9d7` on 2026-10-06, a broad “remaining-small-dirs round1” audit that made unknown risk levels fail closed, preserved explicit empty deny lists, and normalized Windows path matching; it added the current regression coverage. That is maintenance of an absorbed compatibility artifact, not evidence of active replacement work.

**Recommendation:** **Retire the Python `vectorcode/src/permissions/__init__.py` module and its three dedicated regression tests. It is not needed directly or indirectly.** Do not wire a second permission authority. Before deletion, record the one potentially useful product idea—configurable, resolved-path write scopes—as a separate enhancement candidate for the canonical gateway/file-tool enforcement layer; do not copy the current suffix matcher or bash allow-prefix logic. Keep the unrelated live TypeScript permission system unless it is separately investigated.
