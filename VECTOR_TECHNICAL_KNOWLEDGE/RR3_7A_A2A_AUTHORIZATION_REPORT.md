# RR-3.7A A2A AUTHORIZATION REPORT

## 1. Executive Result

1. RR-3.6's A2A bypass finding is **independently reproduced from source**, item by item (Section 7), not merely trusted.
2. **A significant severity correction, discovered this mission**: every currently-materializable agent reachable through `vectorcode.src.agents.registry` (the registry A2A reads from — a DISTINCT registry from the real district-agent `core.city.agent_registry` Governor/PermissionGateway route through) resolves to either a nonexistent Python class (`coding.yaml`'s 5 definitions — `CoderAgent`/`ReviewerAgent`/`TesterAgent`/`DebuggerAgent`/`ArchitectAgent` are not importable anywhere in this codebase) or one of `agent_types.py`'s ~60 dynamically-generated wrapper classes, **none of which override `AgentBase.run()`** (the trivial base stub: `return {"status": "ok", "agent": self.name, "task": task}` — no real side effect at all). Today's gap was therefore **latent, not live-dangerous**. The architectural hole itself — no authorization boundary at all before `instance.run()` — was still real, and would have become immediately exploitable the moment any real capability was ever registered into this registry.
3. **Fixed**, with a deliberately different shape than `/command`/`/ws/command` (per the mission's own instruction not to blindly copy them): a deterministic `action_type` is extracted from the request (never guessed via an LLM); if none can be extracted, the request fails closed with zero Gateway/execution reached. Where an action_type IS extracted, `PermissionGateway.execute()` becomes the sole authorization+execution boundary — `instance.run()` is never called afterward, eliminating double-dispatch by construction.
4. Both mounted A2A endpoints (`/districts/{name}/invoke` and `/sessions/{id}/messages`) are fixed via the same shared `_dispatch()` function — neither was left behind.
5. 22 new tests, 18 independently confirmed via git-stash to fail on the pre-fix code, including explicit confused-deputy coverage. All 33 pre-existing A2A tests remain green. Zero new regressions across a 13-file broad regression.
6. Production validation: a real, successful, fully-observed GREEN invocation completed end-to-end (HTTP → real action-identity extraction → real `PermissionGateway._classify()` → real execution → honest result), confirmed directly in the server's own log.
7. All 12 adversarial claims (Section 20) survive falsification attempts: **PROVEN**.
8. Post-fix endpoint inventory: `/command`, `/ws/command`, and both A2A endpoints are all SAFE CANONICAL. The ~50-endpoint structured-dispatch class remains, unchanged, explicitly out of this mission's scope (RR-3.7B).
9. VECTOR is stopped, confirmed terminated.

## 2. Starting Integrity

- HEAD: `5de36e5a76fe10530fa3c5d17d5ba43e4ce8e372` — confirmed exact match.
- Branch: `production-hardening-complete`.
- VECTOR confirmed not running before any work.
- Tracked modifications at start: `data/models/neural_policy.{meta.json,pt}` — same real, legitimate artifacts disclosed in every prior mission's report.
- Untracked files: the known, pre-existing set from RG-B through RR-3.6 — none touched.

## 3. A2A Endpoint Inventory

| Method | Path | Auth | Caller-controlled agent? | Caller-controlled task type? | Caller-controlled params? | Direct `instance.run`? | Governor? | PermissionGateway? | Side effect possible? | Response contract |
|---|---|---|---|---|---|---|---|---|---|---|
| GET | `/a2a/.well-known/agent.json` | Bearer (non-loopback) | No | No | No | No | No | No | No | Static discovery manifest |
| GET | `/a2a/agents` | Bearer | No | No | No | No | No | No | No | Registry listing (read-only) |
| GET | `/a2a/districts/{name}` | Bearer | No (path lookup only) | No | No | No | No | No | No | Single-agent manifest |
| **POST** | **`/a2a/districts/{name}/invoke`** | Bearer | **Yes** (path param) | **Yes** (`task`) | **Yes** (`params`) | **Yes (pre-fix) → No (post-fix)** | Only via Gateway's own internal delegation, post-fix | **No (pre-fix) → Yes (post-fix)** | **Yes** | `InvokeResponse{task_id, agent, status, output, error}` |
| GET | `/a2a/districts/{name}/tasks/{id}` | Bearer | No | No | No | No | No | No | No | In-memory task status lookup |
| POST | `/a2a/sessions` | Bearer | Yes (session owner) | No (no task field) | No | No | No | No | No (creation only, no dispatch) | `{session_id, agent}` |
| **POST** | **`/a2a/sessions/{id}/messages`** | Bearer | No (fixed at session creation) | **Yes** (message text, but see Section 8 — no structured field possible) | No | **Yes (pre-fix) → No (post-fix)** | Only via Gateway's own internal delegation, post-fix | **No (pre-fix) → Yes (post-fix)** | **Yes (theoretically) → effectively No (schema has no structured action field)** | `{reply}` or `{ok}` |
| GET | `/a2a/events` (SSE) | Bearer | No | No | No | No | No | No | No | Live task-status stream |

## 4. Authentication Boundary

`/a2a/*` is mounted with no `_PUBLIC_PATHS` exemption (`core/api/middleware.py`), so it is subject to the same `VECTOR_API_KEY` bearer-token gate as `/command`/`/ws/command` — confirmed by direct read of the middleware's `_PUBLIC_PATHS` set and the successful production validation (Section 19), which required the real API key. This is **authentication only** (who is calling) — kept explicitly separate from authorization per mission Section 9. An authenticated caller (any holder of the API key) still needed, pre-fix, zero per-action authorization to reach `instance.run()`.

## 5. Authorization Boundary

Pre-fix: none. Post-fix: `PermissionGateway.execute()`, identical to `/command` and `/ws/command`.

## 6. Pre-Fix Call Graph

`POST /a2a/districts/{name}/invoke` → `invoke_agent(name, body)` → `_dispatch(name, body.task, body.params)` → [0] registry existence check (404 if absent) → [1] optional `vectorcode.src.a2a.client.A2AClient.invoke` (not installed/wired in this repo — confirmed the import always raises, falls through) → [2] `_materialize_agent(defn)` (dynamic class lookup + instantiation) → `instance.run(task_payload)` **directly**. `POST /a2a/sessions/{id}/messages` → `session_message()` → the same `_dispatch()` call, `task=body.message` (a bare string). Neither `Candidate`, `DecisionEngine`, nor `PermissionGateway` appeared anywhere in this call graph.

## 7. RR-3.6 Finding Verification (A–L)

| Item | Verdict | Evidence |
|---|---|---|
| A. A2A router mounted | **PROVEN** | `core/api/app.py:397` `app.include_router(a2a.router)`; prefix `/a2a` |
| B. Externally reachable | **PROVEN** | Standard FastAPI route, subject only to the bearer-token auth middleware |
| C. Caller controls agent identity | **PROVEN** | `name: str` path parameter, no allowlist |
| D. Caller controls task payload | **PROVEN** | `InvokeRequest.task: dict | str`, `params: dict` — fully free-form |
| E. Selected agent comes from real AgentRegistry | **PROVEN** | `vectorcode.src.agents.registry.get_registry()`, confirmed the real, live singleton (not a stub) |
| F. Endpoint directly calls `instance.run()` | **PROVEN** (pre-fix) | `a2a.py` (pre-fix) `:355` `result = instance.run(task_payload)` |
| G. PermissionGateway absent before invocation | **PROVEN** (pre-fix) | Zero references to `PermissionGateway` anywhere in the pre-fix file |
| H. Governor absent before invocation | **PROVEN** (pre-fix) | Zero references to `Governor`/`GovernorCouncil` anywhere in the file (pre- or post-fix — A2A never routed through Governor even before this mission) |
| I. No middleware performs equivalent authorization | **PROVEN** | Middleware only handles authentication (Section 4), never inspects request bodies for action-type semantics |
| J. At least one reachable agent can perform a side effect | **CONDITIONAL — corrected this mission.** No currently-materializable agent behind this registry has any real side effect today (Section 1, finding 2) — this is a latent architectural risk, not a live one, a material refinement of RR-3.6's own framing |
| K. No universal downstream re-gate exists | **PROVEN** | `AgentBase.run()`'s trivial stub and all ~60 `agent_types.py` wrappers have no re-gating logic of any kind (confirmed by full source read) |
| L. Caller can therefore cross the intended authorization boundary | **PROVEN architecturally**, even though (J) means no real damage was currently possible — the boundary itself did not exist, which is the defect this mission closes regardless of today's specific registry contents |

## 8. Agent/Action Contract

`AgentDefinition.capabilities` (e.g. `["python", "typescript", "bash"]` for `coder`) is a **skill/language-tag vocabulary**, fundamentally incompatible with `PermissionGateway`'s **action_type-tier vocabulary** (e.g. `"send_email"`, `"execute_code"`). Cross-validating between them would compare incompatible namespaces. `_resolve_action_type()` therefore extracts the real, intended `action_type` deterministically from `task["type"]`, `task["action"]`, `params["type"]`, or `params["action"]` (checked in that order, first match wins) — mirroring the literal key convention `Governor.dispatch()`'s own task dicts and real district agents' own `run()` implementations already use (confirmed via RR-3.6's own investigation of `email_agent.run()`'s `task_type = task.get("type")` pattern). If none of these four keys carry a string value, the request **fails closed** — no guess, no LLM classification, no default "invoke_agent" wrapper (Section 6's explicit prohibition).

## 9. Confused-Deputy Analysis

Tested and proven (Section 16):
- A generic wrapper label (`{"type": "invoke_agent"}`) is itself what gets classified — it resolves to `UNKNOWN` (not a real tier), never silently approved as if it meant something harmless.
- The same `action_type` classifies identically regardless of which registered agent name is requested — agent identity cannot smuggle a different authorization outcome.
- A free-form payload with no deterministic field (`{"description": "...", "content": "rm -rf /"}`) fails closed — the dangerous-looking free text is never interpreted or executed.
- Disagreeing `task["type"]` vs `task["action"]` resolve deterministically (`type` wins, documented precedence) — never an ambiguous or LLM-guessed outcome.
- A caller cannot hide a dangerous operation behind a harmless `action_type` by stuffing extra params: every real `PermissionGateway._execute_action()` handler examined reads only the params keys relevant to its own declared `action_type` and ignores unrelated fields (e.g. `"respond"`'s handler never reads a `"code"` param even if one is present) — confirmed by direct source reading of the handler set, not assumed.

## 10. Capability Binding

Per Section 8's reasoning, capability binding against `AgentDefinition.capabilities` was deliberately **not implemented** — the vocabularies are incompatible, and attempting to cross-check them would either wrongly block legitimate GREEN actions or provide a false sense of validation. Binding is enforced entirely through `PermissionGateway._classify(action_type)`, the same single source of truth `/command` and `/ws/command` already rely on. The requested agent name is preserved only as an existence check (404 for unknown agents, matching prior API behavior) and informational params (`_a2a_requested_agent`), never as an authorization input.

## 11. Repair Design

DecisionEngine was deliberately **not inserted** (Section 5): the caller has already selected a concrete agent/operation, so candidate competition adds no security or semantic value — it would only visually mimic `/command` without a real requirement, which the mission explicitly warned against. The chosen shape is: `A2A request → deterministic action-identity extraction (fail closed if absent) → Action(action_type, params, proposed_by="a2a") → PermissionGateway.execute()`. This resolves Section 11/18's central tension (Gateway both authorizes AND executes via its own dispatcher, while A2A's contract nominally names a specific agent) by treating the named agent as informational rather than authoritative for execution — exactly how `/command`/`/ws/command` already work (the caller never picks the specific executing agent instance there either; Governor's own capability routing does). Given finding 2 (Section 1) — no currently-real agent behind this registry has meaningful, distinguishable capability — this is not a loss of any real functionality today, and is the architecturally correct choice for whenever real capabilities are eventually registered here too.

## 12. Implementation

**File**: `core/api/routers/a2a.py`.

- New `_resolve_action_type(task, params) -> str | None` — deterministic extraction, documented precedence, fail-closed on `None`.
- `_dispatch()` rewritten: existence check preserved (informational + 404 contract); `instance.run()` and `_materialize_agent()` invocation removed from the execution path entirely (the function itself is left in place, now unused, to minimize diff surface — confirmed not exported in `__all__`, not imported elsewhere); execution now flows exclusively through `PermissionGateway().execute(Action(action_type=..., params={**task_if_dict, **params, "_a2a_requested_agent": agent_name}, proposed_by="a2a"))`.
- Response construction distinguishes `blocked` (denial, any tier), `not_implemented` (never reported as success), `error` (Gateway exception), and genuine success — mirroring RR-3.6's `/ws/command` pattern.
- Both `invoke_agent()` and `session_message()` call the same fixed `_dispatch()`, so the fix applies uniformly to both mounted endpoints (Section 19).

## 13. Post-Fix Call Graph

`POST /a2a/districts/{name}/invoke` → `invoke_agent()` → `_dispatch()` → [0] existence check (404) → [1] `_resolve_action_type()` (fail closed if `None`, zero further calls) → [2] `PermissionGateway.execute(Action(...))` (the sole execution-capable call) → honest response construction. `POST /a2a/sessions/{id}/messages` → `session_message()` → identical `_dispatch()` flow with `task=body.message` (always a bare string, so step [1] always fails closed for sessions today).

## 14. Permission Tier Tests

Implemented and passing (real, unmodified `PermissionGateway._classify()`): GREEN real harmless action (`respond`) authorized and executed via Gateway alone; FORBIDDEN → zero execution; UNKNOWN → zero execution; RED rejection/timeout → zero execution (mocked transport, real `GatewayResult` shape); action-type resolution confirmed agent-independent and confirmed that capability tags (e.g. `"python"`) never resolve to a real tier on their own.

## 15. Session Authorization Tests

`test_rr3_7a_session_message_fails_closed_no_executable_dispatch` and `test_rr3_7a_session_reuse_does_not_imply_blanket_authorization`: three sequential messages in the same session each independently fail closed (zero Gateway calls across all three) — proving no per-session authorization cache or blanket-trust shortcut exists. Authorization occurs (or, here, correctly never occurs) per request, never per session.

## 16. Double-Execution Test

`test_rr3_7a_gateway_authorization_happens_before_any_execution` (call-order instrumentation) and `test_rr3_7a_approved_action_executes_exactly_once` (`await_count == 1`): both confirm `PermissionGateway.execute()` is the only execution-capable call and it fires exactly once per approved request. No `Gateway.execute() + instance.run()` double-execution is possible by construction — `instance.run()` was removed from the authorized path entirely, not merely sequenced after Gateway.

## 17. Exploit-Shape Regression

`test_rr3_7a_exploit_shape_regression_red_action_no_longer_reaches_agent_run`: a real agent name + a real RED-tier action (`execute_code`) + a RED denial/timeout `GatewayResult` — confirmed `PermissionGateway.execute()` is reached with the correct `action_type`, and no code execution occurs. Independently verified via git-stash: 18 of 22 new tests fail against the pre-fix code, including this one and the call-order/double-execution tests.

## 18. Broad Regression

13 files (A2A ×2, `/ws/command`, `/command`, RR-3.5, RR-3 overnight, RR-2, RR-1, RR-1.5, governor ×3, permission_gateway, R19): only the same 3 already-confirmed pre-existing failures from every prior mission's own regression (`test_regression_governor_capability_routing.py` ×2, `test_permission_gateway.py`'s stale-mock RED-timeout test). Zero new regressions. All 55 A2A-related tests (22 new + 33 pre-existing) pass.

## 19. Production Validation

VECTOR launched in `api` mode, well within the 15-minute bound. One real, harmless, non-mocked HTTP POST to `POST /a2a/districts/coder/invoke` with `task={"type": "respond", "message": "hello from RR-3.7A production validation"}` completed successfully: `HTTP 200`, `status="ok"`, `action_type="respond"`, `agent="coder"`. Confirmed directly in the server's own log: `[VECTOR][gateway] respond classified as GREEN (proposed by a2a)` — proving the real `PermissionGateway` was reached with `proposed_by="a2a"` exactly as designed, real tier classification occurred, and real execution followed. No RED or FORBIDDEN action occurred anywhere in the validation window (confirmed via full log review). This is a materially stronger, fully-successful observation than RR-3.5's or RR-3.6's own production validations, both of which were limited by `classify_chat_intent()`'s LLM-call timeout — A2A's structured input bypasses that classifier entirely.

## 20. Adversarial Audit

| Claim | Verdict | Evidence |
|---|---|---|
| 1. Every executable A2A request is authorized | **PROVEN** | Source construction + call-order test + production validation |
| 2. Actual capability, not wrapper, determines permission tier | **PROVEN** | `_resolve_action_type()` extracts the real intended type; generic wrapper labels resolve to UNKNOWN |
| 3. Caller cannot hide RED action behind GREEN wrapper | **PROVEN** | Deterministic precedence + confirmed real handlers only read params relevant to their own classified action_type |
| 4. Selected agent cannot execute a capability different from authorized | **PROVEN** | `instance.run()` removed from the path entirely; only `action_type` determines execution, agent-independent (tested) |
| 5. Session reuse cannot bypass authorization | **PROVEN** | Three sequential session messages, zero Gateway calls, no cached authorization state |
| 6. UNKNOWN fails closed | **PROVEN** | Dedicated test |
| 7. Malformed payload fails closed | **PROVEN** | Dedicated test (no type/action key at all) |
| 8. Denial means zero execution | **PROVEN** | RED rejection/timeout, FORBIDDEN, UNKNOWN tests all confirm |
| 9. Approved action executes exactly once | **PROVEN** | `await_count == 1` + call-order test |
| 10. No Governor fallback changes requested agent | **PROVEN** | The requested agent was never authoritative for execution after this fix — Gateway/Governor's own routing is, exactly matching `/command`/`/ws/command`'s existing, unchanged behavior |
| 11. No sibling A2A endpoint remains direct-run | **PROVEN** | Both `invoke_agent()` and `session_message()` route through the same fixed `_dispatch()` |
| 12. `/command` and `/ws/command` remain unchanged | **PROVEN** | Diff touches only `a2a.py` and the new test file |

## 21. Diff Audit

```
core/api/routers/a2a.py                | 165 ++++++++----
tests/test_rr3_7a_a2a_authorization.py | 457 +++++++++++++++++++++++++++++++++
2 files changed, 573 insertions(+), 49 deletions(-)
```

One production file, one new test file. `data/models/neural_policy.{pt,meta.json}` modified again as a real side effect of this mission's own production validation — left uncommitted, same discipline as every prior mission.

## 22. Commit Ledger

- Starting HEAD: `5de36e5a76fe10530fa3c5d17d5ba43e4ce8e372`
- **Final HEAD**: `e757ee709a0b48fc52aa924d2670b3ac0945f256`

One production commit, as preferred; no second test-strengthening commit was needed.

## 23. Evidence Ladder

| Claim | Level |
|---|---|
| A2A's executable branches now reach PermissionGateway before any side effect | **BEHAVIORALLY VERIFIED** — a real, successful, fully-observed GREEN production invocation, not just tests |
| The pre-fix bypass was architecturally real but practically latent (no live-dangerous capability reachable today) | **SOURCE IMPLEMENTED + INTEGRATED**, confirmed by exhaustive class-existence tracing across all three agent-registration sources |
| Session messages fail closed | **TEST VERIFIED** (schema-guaranteed — no structured field is possible, confirmed by direct model inspection, not just test behavior) |
| `/command`/`/ws/command` remain unaffected | **TEST VERIFIED** + **RUNTIME REACHABLE** (zero source lines touched) |

## 24. Remaining Structured-Endpoint Gap

~50 endpoints across 26 router files (`agency.py`, `analytics.py`, `brain.py`, `calls.py`, `chief.py`, `city.py`, `coding_extended.py`, `design.py`, `documentation.py`, `finance.py`, `governance_extended.py`, `health.py`, `interview.py`, `karpathy.py`, `languages.py`, `learning.py`, `news.py`, `ops.py`, `patterns.py`, `privacy.py`, `projects.py`, `qa.py`, `reflection.py`, `relationships.py`, `skills.py`, `startups.py`) each call `Governor.dispatch({"type": "<hardcoded literal>", ...})` with zero `PermissionGateway` reference anywhere in any of the 26 files — confirmed real and unchanged by this mission, explicitly deferred to RR-3.7B per the mission's own scope boundary (Section 0: "DO NOT TOUCH THE ~50 STRUCTURED ROUTER ENDPOINTS YET. Those belong to RR-3.7B"). `voice_ws.py` remains genuinely untraced (flagged AMBIGUOUS in RR-3.6, not investigated further here — out of this mission's A2A-specific scope).

## 25. Verdict

**RR-3.7A PASS — A2A AUTHORIZATION BOUNDARY CLOSED**

RR-3.6's finding was independently reproduced and confirmed real, with one material severity correction discovered through deeper investigation: no currently-real capability was actually reachable through the affected registry, making the pre-fix gap latent rather than live-dangerous — reported honestly rather than either overstating or dismissing the original finding. The fix closes the architectural gap completely for both mounted A2A endpoints, using a deliberately non-imitative design (no DecisionEngine, no capability-tag cross-checking) justified from first principles rather than copied from `/command`. All 12 adversarial claims survive falsification. All required test categories (structural, tier, confused-deputy, session, call-order, double-execution, exploit-shape) pass, 18 of 22 independently confirmed via git-stash to catch the original bug. Broad regression is clean. Production validation achieved a full, real, successful end-to-end observation — stronger evidence than either prior mission's own validation phase.

Per Section 23's own explicit scoping allowance, this PASS stands despite RR-3.7B (the ~50-endpoint structured-dispatch class) remaining open — that gap was never this mission's target.

Per the Hard Stop: RR-3.7B, RR-4, RG-C2, RG-D2, and R27 are not started. VECTOR is stopped, confirmed terminated. Awaiting independent review.
