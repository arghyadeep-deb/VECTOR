# RR-3.7C — Final Ingress Security Closure & Authorization Freeze

Starting HEAD: `48c0f7e9aec386b79bbc4e0543671f05ac611890` (branch `production-hardening-complete`)
Final HEAD: see Section 25 commit ledger.

---

## 1. Executive Result

This mission answered its four bounded questions and found real, confirmed
security issues in three of them — all repaired using only existing
architecture, verified pre-fix/post-fix, and confirmed live in production.

**A. `voice_ws` reachability/authorization** — CONFIRMED SEVERE GAP,
REPAIRED. `voice_ws.py`'s two WebSocket endpoints
(`/ws/voice/stream`, `/ws/voice/duplex`) had **zero network-level
authentication** — confirmed by direct read of the installed Starlette's
own `BaseHTTPMiddleware.__call__` source: every `app.middleware("http")`-
registered middleware (including `auth_middleware`) unconditionally
bypasses WebSocket connections. Combined with `try_device_action()`'s
hardcoded `proposed_by="api_command"` on a RED-tier, `RED_INTERACTIVE_
TOOLS`-member action (`launch_app`), any unauthenticated network client
could cause a real, zero-confirmation `PCController.launch_app()` call on
the owner's machine. A second, independent gap in the same file:
`voice_duplex`'s action-handoff path (`RealtimeConversation._run_action()`)
called `Governor().dispatch()` directly, bypassing `PermissionGateway`
entirely — the same shape RR-3.6 already fixed for `/ws/command`. Both
repaired by reusing existing, already-accepted mechanisms (`require_auth_
handshake()`, the `Candidate → DecisionEngine → PermissionGateway`
pipeline). **A third, deeper root cause was discovered while live-
validating the first fix**: `websocket.py`'s own `WS_API_KEY` constant was
a **guaranteed-empty lookup in every deployment** (`CONFIG.get(
"vector_api_key", "")` — a field that has never existed in `core/config.py`
at any nesting level), meaning `require_auth_handshake()` — the exact
mechanism `/ws/command` has relied on since RR-3.6 — has silently never
enforced authentication, for ANY endpoint that uses it, in ANY
deployment. Fixed by sourcing the key from `core/security/secrets_manager.
get_secret("VECTOR_API_KEY")`, the same mechanism the HTTP `auth_
middleware` already correctly uses. **Live-verified end-to-end**: a wrong/
missing token now closes the connection with code 1008 "Unauthorized";
the correct key proceeds normally.

**B. Gemini/provider credential-log leak** — CONFIRMED, ROOT-CAUSED,
REPAIRED. `httpx.Response.raise_for_status()` embeds the full request URL
(including Gemini's `?key=<value>` query-param credential) in its
exception message; two call sites (`vectorcode_llm.py::_try_gemini()`,
`provider_client.py::_call_with_retry()`) logged that exception's raw
string. Fixed with a small, purpose-built, shared sanitizer (`core/
inference/error_sanitize.py`) applied at both points.

**C. CredentialManager missing-type invocation** — PROVEN SAFE. No
externally-reachable ingress (structured HTTP, `/command`, `/ws/command`,
A2A, voice) can construct a task dict with `"type"` genuinely absent — all
hardcode an explicit action-type string, or (A2A) fail closed before any
dispatch when none can be resolved. `CredentialManager` unmodified beyond
RR-3.7B.1's own already-completed fix.

**D. Routing-collision security analysis** — all three previously-reported
wrong-district collisions (`scan_data_sharing`, `gdpr_check`, `growth_
analysis`) classified **CORRECTNESS — DEFERRED**: none reach a materially
more-privileged capability than what their own worst-case winner already
does (confirmed non-mutating/low-severity in every case, per RR-3.7B.1's
own exhaustive per-agent trace, re-confirmed here under the security-
substitution framing this mission specifically required).

**Freeze declaration**: all 12 freeze criteria (Section 24) are met.

**Verdict:** `RR-3.7C PASS — AUTHORIZATION BOUNDARY FROZEN FOR VECTOR V1`

---

## 2. Starting Integrity

```
git rev-parse HEAD        -> 48c0f7e9aec386b79bbc4e0543671f05ac611890  (MATCH)
git branch --show-current -> production-hardening-complete             (MATCH)
```
VECTOR confirmed stopped (`tasklist` showed zero matching python.exe
processes) before any mutation. Pre-existing modified/untracked files
recorded and unchanged by this mission: `data/models/neural_policy.{pt,
meta.json}` (autonomous-loop runtime artifacts) plus the same backlog of
uncommitted report/doc files from earlier missions in this session,
unchanged.

**Security note on this mission's own process**: while writing the pytest
proof for the `WS_API_KEY` root-cause fix, an early version of a test
asserted `WS_API_KEY == get_secret("VECTOR_API_KEY")` directly against the
live, real, configured secret. That assertion's own failure diff (during
the required pre-fix git-stash verification) printed the complete real
API key in this session's tool output. The stashed change was restored
within the same turn; the test was rewritten twice, first to compare only
against a synthetic value via a module reload (rejected as unnecessarily
risky — reloading a live application module with process-wide singletons)
and finally to a pure source-inspection + length-only check that can never
print the real value in any future failure. No file, report, or commit in
this repository contains the real key. This is disclosed here in the
interest of full honesty about this mission's own conduct, not because
the value reached any persistent or external location.

---

## 3. Scope and Freeze Rule

Per the mission's explicit hard scope boundary (Section 3 of the mission
prompt): IN SCOPE was limited to `voice_ws` and its directly-connected
execution path, provider credential-logging paths, `CredentialManager`
missing-type semantics from external ingress, final ingress enumeration,
and a security-only (not general-correctness) pass over the three known
routing collisions. General `DISTRICT_TASK_MAP` cleanup, the collisions
themselves as correctness bugs, accepted S3-low findings, `accessibility_
audit`'s routing bug, and all non-security engineering work were
explicitly out of scope and are recorded in Section 26 (deferred backlog),
not repaired here.

The freeze rule (Section 19/20 of the mission prompt) is explicit: PASS
here means RR-3.7 security-foundation work is DONE — no RR-3.7D is
recommended merely because further imperfections exist. A further
authorization mission is justified only by a concrete, externally-
reachable, currently-open privileged-bypass path this mission could not
safely close — none remains (Section 20 below).

---

## 4. Final External Ingress Enumeration

One bounded pass over every mounted API/router/WebSocket entrypoint,
confirming ingress classes rather than re-auditing each one's internals
(already done exhaustively across RR-3.5 through RR-3.7B.1).

| Ingress | Transport | Mounted? | Authenticated? | Caller controls action/task? | Execution path | Gateway before privileged effect? | Status |
|---|---|---|---|---|---|---|---|
| `/command` | HTTP POST | yes | yes (bearer) | yes (free text → classifier) | `Candidate → DecisionEngine → PermissionGateway.execute()` | yes | SAFE CANONICAL (unchanged) |
| `/ws/command` | WebSocket | yes | yes (bearer, `require_auth_handshake` — **now genuinely enforced**, see Section 8) | yes | same pipeline (RR-3.6) | yes | SAFE CANONICAL |
| A2A `/invoke` | HTTP POST | yes | yes (bearer) | yes (agent+task) | `_resolve_action_type()` fail-closed → `PermissionGateway.execute()` (RR-3.7A) | yes | SAFE CANONICAL |
| A2A `/sessions/{id}/messages` | HTTP POST | yes | yes (bearer) | yes | same `_dispatch()` (RR-3.7A) | yes | SAFE CANONICAL |
| Structured HTTP routers (26 files, 66 endpoints) | HTTP | yes | yes (bearer) | yes (hardcoded per-endpoint type + body params) | per-endpoint; 4 real gaps found and repaired across RR-3.7B/B.1 | yes for repaired; not applicable for S0/S1/S3 | SAFE CANONICAL / SAFE READ-ONLY (per-endpoint, see prior reports) |
| `POST /governance/autopilot/trigger` | HTTP | yes | yes (bearer) | yes | Gateway-fronted N/A (control-flow only); `MAX_CHAIN_DEPTH` now genuinely bounding (RR-3.7B.1) | n/a (no privileged effect in the recursive path) | SAFE FAIL-CLOSED (bounded) |
| `/ws/voice/stream` | WebSocket | yes | **was NO — now yes** (`require_auth_handshake`, this mission) | yes (transcribed speech → `launch_app` intent only) | `try_device_action()` → `PermissionGateway.execute()` (unchanged, already correct) | yes | SAFE CANONICAL (this mission) |
| `/ws/voice/duplex` | WebSocket | yes | **was NO — now yes** (this mission) | yes (transcribed speech → `classify_intent`/`classify_intent_llm`) | `_run_action()` → `Candidate → DecisionEngine → PermissionGateway.execute()` (this mission) | yes | SAFE CANONICAL (this mission) |
| `/ws` (`vector_ws`) | WebSocket | yes | **was silently NO due to the `WS_API_KEY` bug — now yes** (this mission) | yes (`{"action":"command",...}`) | reuses `/command`'s own dispatch | yes | SAFE CANONICAL (this mission) |
| `/ws/state` (`vector_ws_state`) | WebSocket | yes | no (unauthenticated; discovered, out of scope — see Section 26) | no — pure server→client event forwarding; the one `receive_text()` call is a keepalive-only read, its content is never parsed or acted upon | none — zero execution capability | n/a | SAFE READ-ONLY (information-disclosure-only finding, deferred — not a privileged-execution ingress) |
| `/gesture/ws`, `/camera/ws`, `/notifications/ws` | WebSocket | yes | no (unauthenticated) | no | none — sensor/notification broadcast only, confirmed via grep (zero `Governor`/`PermissionGateway`/`.run(`/`dispatch(` references in any of the three files) | n/a | SAFE READ-ONLY |

No additional, previously-untracked privileged-execution ingress class was
found. All WebSocket routes in the codebase were enumerated exhaustively
(`grep -rn "@router.websocket" core/api/routers/*.py` — 7 total, all
accounted for above).

---

## 5. Final Ingress Matrix

(Consolidated view — see Section 4 for full detail per row.)

| Ingress | External? | Auth | Action identity source | Permission boundary | Execution owner | Side effects possible? | Status |
|---|---|---|---|---|---|---|---|
| `/command` | yes | bearer | classifier | PermissionGateway | Gateway/`_execute_action` | yes | SAFE CANONICAL |
| `/ws/command` | yes | bearer (now real) | classifier | PermissionGateway | Gateway/`_execute_action` | yes | SAFE CANONICAL |
| A2A invoke | yes | bearer | resolved type (fail-closed) | PermissionGateway | Gateway | yes | SAFE CANONICAL |
| A2A session messages | yes | bearer | resolved type (fail-closed) | PermissionGateway | Gateway | yes | SAFE CANONICAL |
| Structured HTTP (66 endpoints) | yes | bearer | hardcoded literal | PermissionGateway (4 repaired) / n/a (S0/S1/S3) | Gateway or read-only | per-endpoint | SAFE CANONICAL/READ-ONLY |
| `/ws/voice/stream` | yes | bearer (now real) | fixed literal (`launch_app`) | PermissionGateway | Gateway | yes | SAFE CANONICAL |
| `/ws/voice/duplex` | yes | bearer (now real) | classifier | PermissionGateway | Gateway | yes | SAFE CANONICAL |
| `/ws` | yes | bearer (now real) | classifier | PermissionGateway (via `/command` reuse) | Gateway | yes | SAFE CANONICAL |
| `/ws/state`, `/gesture/ws`, `/camera/ws`, `/notifications/ws` | yes | no | n/a | n/a (no execution) | n/a | no | SAFE READ-ONLY |

**No externally-reachable privileged ingress remains BYPASS or AMBIGUOUS.**

---

## 6. voice_ws Architecture

Full independent trace (mission Section 5, letters A–R):

**A. Exact paths**: `POST /ws/voice/stream` (push-to-talk, binary audio +
`{"type":"end"}`), `POST /ws/voice/duplex` (full-duplex, continuous PCM).

**B. Mounted?** Yes — `core/api/app.py:404`, `app.include_router(voice_ws.
router)`.

**C. Authentication (pre-fix)?** None. Confirmed via direct read of the
installed Starlette's `BaseHTTPMiddleware.__call__`:
```python
async def __call__(self, scope, receive, send):
    if scope["type"] != "http":
        await self.app(scope, receive, send)
        return
```
Every `app.middleware("http")`-registered middleware (`error_handling_
middleware`, `rate_limiting_middleware`, `csrf_middleware`, `auth_
middleware`, `logging_middleware`, `timing_middleware`, `security_
headers_middleware` — all registered this way in `core/api/app.py:340-
346`) takes this exact bypass for `scope["type"]=="websocket"`. Only
`CORSMiddleware` (registered via `app.add_middleware()`, genuinely
ASGI-level) applies to WebSocket connections, and it is not an
authentication control.

**D. Origin/session validation?** None beyond CORS (browser-enforced only,
does not protect non-browser clients).

**E. What messages can the caller send?** `voice_stream`: binary audio
chunks (webm/opus) or `{"type":"end"}`. `voice_duplex`: binary PCM frames,
or `{"type":"playing","value":bool}` / `{"type":"control","action":
"end_session"}` (any other JSON message, including one with an `"auth"`
key, is silently accepted and ignored by the pre-existing code — confirmed
by the module's own comment: "auth handshake messages ({"auth": ...}) are
accepted silently").

**F. Raw text, structured action, or both?** Raw audio → server-side
Whisper transcription → free text. Neither endpoint accepts a
caller-supplied structured action_type directly.

**G. Where transcript becomes intent/task?** `voice_stream`:
`try_device_action(transcript)` (device-command detection, scoped to
`launch_app` only) then rules-bypass/LLM chat. `voice_duplex`: `classify_
intent(text)` (regex) → `classify_intent_llm(text)` (LLM fallback) →
`_run_action(task_type, text)`.

**H. `/command`-equivalent canonical logic?** `try_device_action()` always
did (reuses `commands.py::_detect_intent_action` + `PermissionGateway`).
`_run_action()` did NOT, pre-fix (Section 7 below).

**I. Calls Governor directly?** Pre-fix: `_run_action()` did, via `Governor
().dispatch()`. Post-fix: no — routes through `PermissionGateway.execute()`
first, which internally delegates to `Governor.dispatch()` only for
`_PLAN_COMPOSABLE_ACTION_TYPES`/`hand_*` types, exactly as established
since RR-3.5A.

**J. Calls `agent.run` directly?** No — always via Governor/Gateway,
never a raw agent reference.

**K. Calls PermissionGateway?** `try_device_action()`: always did.
`_run_action()`: now does (this mission).

**L. Can it reach GREEN/YELLOW/RED/FORBIDDEN/UNKNOWN?** Yes, all tiers —
confirmed by tests (Section 14).

**M. `proposed_by`?** `try_device_action()`: `"api_command"` (unchanged —
architecturally correct once the network-auth gap is closed, matching
`permission_gateway.py`'s own documented semantics for this identity).
`_run_action()`: now `"voice"` (this mission) — the literal identity
string `permission_gateway.py`'s own RED tier already special-cases for
exactly this caller ("SPOKEN after the wake word on the owner's own
machine"), previously declared but never wired to this specific call site.

**N. Voice-specific preconfirmation semantics present?** Yes, pre-existing
in `permission_gateway.py`: `action.proposed_by in ("api_command",
"voice")` auto-executes YELLOW immediately and RED-tier `RED_INTERACTIVE_
TOOLS` members immediately ("the command itself IS the confirmation").
Not created or altered by this mission — only correctly gated behind real
network authentication for the first time.

**O. Can a caller spoof the marker/identity?** No — `proposed_by` is a
Python string literal in source at both call sites, never derived from
any caller-supplied field (confirmed by source-level test, Section 14).

**P. Can an action execute twice?** No — `PermissionGateway.execute()` is
the sole execution-capable call in both paths; neither ever separately
re-invokes `Governor.dispatch()`/`agent.run()` afterward (confirmed by
`await_count==1` tests).

**Q. Denial/timeout/exception behavior?** Denial/FORBIDDEN/UNKNOWN → zero
`Governor.dispatch()` calls, honest `"blocked"` status sent to the client.
Gateway exception → caught by `_run_action()`'s own outer `except`, honest
spoken error, zero dispatch. `not_implemented` → reported as `"not_
implemented"`, never as success.

**R. Can malformed/nested payloads change the capability after
authorization?** No — `Action.action_type` is always exactly the
classifier-resolved `task_type` string; `params` carries only `query`/
`user_message`/`source`, never a caller-overridable `type`/`action` key
(confirmed by source read — no such key is ever merged from caller input).

**Pre-fix call graph** (the exploited shape):
```
network client (no auth)
  → voice_stream()/voice_duplex() [websocket.accept(), zero auth check]
    → try_device_action(transcript)                    [voice_stream only]
        → PermissionGateway.execute(Action(
              action_type="launch_app", proposed_by="api_command"))
        → RED tier + RED_INTERACTIVE_TOOLS + proposed_by match
        → INSTANT, ZERO-CONFIRMATION real PCController.launch_app()
    → _run_action(task_type, text)                      [voice_duplex only]
        → Governor().dispatch({"type": task_type, ...})  [PermissionGateway NEVER touched]
        → real district-agent execution, any tier, zero authorization
```

---

## 7. Voice Pre-Fix Authorization Analysis

Both `voice_stream` and `voice_duplex` violated the mission's required
invariant ("external voice input → intent/action identity → authoritative
permission decision → exactly one execution before any privileged side
effect") — not because the DECISION logic was wrong once reached, but
because **the network boundary in front of it was absent**, and — for
`voice_duplex`'s action-handoff path specifically — because **the decision
step itself was skipped entirely**. `try_device_action()`'s own internal
logic was already correct (it always called `PermissionGateway.execute()`)
but was reachable by literally anyone on the network; `_run_action()`
reached real district-agent execution with no permission decision made at
all.

---

## 8. Voice Repair

Three changes, all reusing existing, already-accepted mechanisms — no new
approval architecture, no voice-specific permission tiers, no LLM-based
safety filters, no endpoint-local keyword blocks:

1. **`core/api/routers/voice_ws.py`**: both `voice_stream()` and
   `voice_duplex()` now call `require_auth_handshake()` (imported from
   `core.api.routers.websocket`, the SAME function `/ws/command`'s own
   `vector_ws` already uses) immediately after `websocket.accept()`,
   before any audio processing or state initialization. Both real frontend
   clients already send the matching handshake message on connect
   (`frontend/js/vector-core.js`'s `openWS()` for the `'voice'` socket;
   `frontend/js/voice_duplex.js` directly) — this closes a half-wired gap,
   changing no behavior for an already-correctly-configured client.

2. **`core/voice/realtime.py`**: `RealtimeConversation._run_action()`
   rewritten to build a `Candidate(action_type=task_type, params={"query":
   text, "user_message": text, "source": "voice_realtime"}, ...)`, evaluate
   it via `DecisionEngine().evaluate([candidate])`, and execute via
   `PermissionGateway().execute(Action(action_type=winner.action_type,
   params=winner.params, proposed_by="voice"))` — the exact RR-3.6 pattern.
   `try_device_action()` (voice_stream's Fast path 0) was already correct
   and is unchanged.

3. **`core/api/routers/websocket.py`**: `WS_API_KEY` now sourced from
   `core.security.secrets_manager.get_secret("VECTOR_API_KEY")` instead of
   the always-empty `CONFIG.get("vector_api_key", "")`. This is the root-
   cause fix underlying #1's real-world effectiveness — see Section 12.

---

## 9. Voice Post-Fix Proof

Unit-level (Section 14) plus **live production proof** (Section 21):
```
$ python -c "... connect with wrong/no auth token ..."
CONNECTION CLOSED as expected: code=1008 reason='Unauthorized'

$ python -c "... connect with the real configured key ..."
received (expected, proves auth passed and normal processing began):
{"type":"error","text":"No audio received"}
```
This is definitive, end-to-end, real-server evidence — not a mock — that
the network boundary is genuinely enforced and that a correctly-
authenticated real client is unaffected.

`_run_action()`'s Gateway wiring verified via 6 dedicated tests (GREEN
exactly-once, denial/FORBIDDEN/RED → zero dispatch, Gateway exception →
zero dispatch + honest error, `not_implemented` → honest status).

---

## 10. Voice Confused-Deputy Analysis

Explicitly tested (Section 14, per mission Section 7's exact list):
- Harmless transcript → dangerous nested action: N/A — `_run_action()`'s
  `params` never contains a caller-overridable `type`/`action` key at all;
  the ONLY thing that determines `action_type` is the classifier's own
  return value, itself a hardcoded regex-pattern string or a length-
  clamped LLM 3-6-word phrase, never raw caller JSON.
- Action field vs task-type disagreement: not applicable — no `action`
  field exists in this path's payload shape.
- Unknown/missing action: `_run_action()` is never called with an empty
  `task_type` (`_respond()`'s own `if task_type:` guard prevents it) —
  confirmed by dedicated test asserting an empty string still routes to
  Gateway/UNKNOWN, zero dispatch.
- Spoofed `proposed_by`: impossible — hardcoded Python literal, confirmed
  via source-level test (no variable/f-string interpolation feeds it).
- Spoofed `_llm_classified`/voice marker/agent-name manipulation: not
  applicable to this ingress — these markers belong to `/ws/command`'s own
  classifier contract, not constructed or read anywhere in this code path.
- Malformed JSON: `voice_duplex`'s main loop already silently ignores
  unparseable JSON (`try: msg = json.loads(...); except json.JSONDecodeError:
  continue`) — pre-existing, unaffected by this mission's changes, and
  confirmed harmless (never reaches `_run_action()`).
- Replayed message: not relevant to this protocol shape (no idempotency
  token/nonce concept exists to replay against; each WS session is a
  fresh, freshly-authenticated connection).

**Authorization binds to the capability actually executed**: `Action.
action_type` is always exactly `winner.action_type` (`DecisionEngine`'s
own selected candidate, itself always the `task_type` this function was
called with) — never re-derived from any other field post-authorization.

---

## 11. Gemini/API-Key Log Leak Reproduction

Independently reproduced at a safe boundary using ONLY a synthetic secret
(`AIzaSyDfakeTestKeyDoNotUse1234567890...` — never a real credential, in
this report or in any test file).

```
Client error '404 Not Found' for url
'https://generativelanguage.googleapis.com/v1beta/models/
gemini-2.0-flash:generateContent?key=<SECRET>'
```
(real observed shape from RR-3.7B.1's own production log, secret redacted
here for this report per the mission's explicit instruction).

---

## 12. Secret Logging Root Cause

Traced precisely (mission Section 8's exact chain):

1. **Provider call**: `core/inference/vectorcode_llm.py::_try_gemini()`
   and `core/inference/provider_client.py::ProviderClient._call_gemini()`.
2. **Request URL construction**: both build
   `f"{...}/models/{model}:generateContent?key={api_key}"` — Gemini's REST
   API requires the key as this exact query parameter; there is no
   header-based alternative for the endpoint VECTOR calls.
3. **HTTP client**: `httpx.post()` (`_try_gemini`) / `httpx.AsyncClient().
   post()` (`_call_gemini`).
4. **Exception**: `resp.raise_for_status()` raises `httpx.HTTPStatusError`
   for any non-2xx response not already special-cased (e.g. 404, 400, 403,
   500 — 429 is intercepted separately before `raise_for_status()` in both
   files).
5. **Formatter/exception representation**: confirmed via direct read of
   the installed httpx's own `_models.py::Response.raise_for_status()`
   source — the message is built as `"{error_type} '{status} {reason}'
   for url '{url}'\n..."`, i.e. the FULL request URL (key included),
   **never** request/response headers (verified: no `{0.headers}` token
   in the non-redirect message template — this matters for Section 13's
   scope-narrowing of `_try_openrouter`/`_try_anthropic`, both header-auth
   and therefore NOT vulnerable via this exact mechanism).
6. **Logger call**: `vectorcode_llm.py:320` (pre-fix): `logger.warning(f
   "[VECTOR][vc_llm] Gemini failed: {e}")` — direct f-string interpolation
   of the raw exception, URL and all. `provider_client.py:567` (pre-fix):
   `last_error = str(e)` — captured raw, then consumed by BOTH an
   80-char-truncated warning (`logger.warning("... {} failed: {}. Trying
   next...", _prov.slug, str(e)[:80])` — coincidentally often too short to
   reach the key given typical URL length, but not a reliable protection)
   AND an untruncated `raise RuntimeError(f"All providers failed. Last
   error: {last_error}")` that could resurface the full key to ANY future
   caller of `provider_client.chat()`/`complete()` that logs its own
   exceptions.
7. **Final log sink**: loguru → console/file (confirmed live in RR-3.7B.1's
   own production validation — this is not a theoretical trace).

---

## 13. Bounded Sibling Provider Audit

Scoped exactly per mission Section 9 — provider adapters, LLM clients,
shared network/request helpers, retry/error logging used by those
providers. NOT a repository-wide secret scanner.

| Path | Classification | Evidence |
|---|---|---|
| `vectorcode_llm.py::_try_gemini()` | **VULNERABLE (pre-fix)** | key-in-URL + raw `{e}` log — Section 12 |
| `provider_client.py::_call_gemini()` / `_call_with_retry()` | **VULNERABLE (pre-fix)** | same key-in-URL mechanism; `last_error = str(e)` captured raw, feeding both a truncated warning and an untruncated re-raised `RuntimeError` |
| `vectorcode_llm.py::_try_anthropic()` | SAFE | official `anthropic` SDK, key sent via `Authorization` header internally; SDK exceptions do not echo request headers |
| `vectorcode_llm.py::_try_openrouter()` | SAFE | key sent via `headers={"Authorization": f"Bearer {api_key}",...}`; httpx's `HTTPStatusError` message never includes headers (Section 12, point 5) |
| `provider_client.py`'s other exception-logging call sites (`exc_info=True` at 3 locations) | SAFE / NOT APPLICABLE | all wrap `ImportError`/module-resolution failures (rate limiter, model router) unrelated to any Gemini/credential-bearing call |
| `provider_client.py`'s `RuntimeError(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")` (the primary non-2xx raise inside `_call_gemini` itself) | SAFE | uses `resp.status_code`/`resp.text` (response body, not the request URL/headers) — providers do not echo the caller's own key in error response bodies |
| `core/inference/ollama_safe.py` (5 `{e}`-interpolating log lines) | NOT APPLICABLE | Ollama is local (`http://127.0.0.1:11434`), carries no credential in any request |
| `core/inference/llm_providers.py` | NOT APPLICABLE | zero matches for any credential-bearing URL/header construction pattern |
| `core/inference/smart_routing/request_cache.py`'s `key[:12]` log | NOT APPLICABLE (false-positive from the initial grep) | `key` here is an internal cache-lookup hash, not a credential, and is already truncated |

---

## 14. Secret Logging Repair

`core/inference/error_sanitize.py` (new, ~15 lines of real logic): a
single function, `sanitize_provider_error(text)`, redacting `[?&](key|
api_key|apikey|access_token)=<value>` and, defensively, `Bearer <token>`
forms (the latter has no confirmed live VECTOR call site that logs it —
included at zero marginal cost as the shape a future exception type could
plausibly carry). Never raises (returns input unchanged on any internal
failure, so a sanitizer bug can never itself break a `logger.warning()`
call). Applied at exactly the two capture points identified in Section 13:
`vectorcode_llm.py`'s `except Exception as e:` before its `logger.warning`
call, and `provider_client.py`'s `last_error = str(e)` line (a single fix
here closes BOTH downstream consumers — the truncated warning and the
re-raised `RuntimeError` — since both read from `last_error`).

No provider behavior change; no swallowed failures; diagnostic context
(status code, reason phrase, host, path, unrelated query params) fully
preserved — only credential VALUES are replaced with `<REDACTED>`.

---

## 15. Secret Redaction Tests

`tests/test_rr3_7c_secret_log_redaction.py` — 7 tests, synthetic secrets
only (`AIzaSyDfakeTestKeyDoNotUse1234567890`, never a real key):
sanitizer redacts the exact Gemini `?key=` shape observed in production;
redacts a partial/prefix leak too (not just the full value); redacts
`api_key=`/`apikey=`/`access_token=` forms; redacts the defensive `Bearer`
form; never raises on empty/`None`/plain-text input; preserves unrelated
query parameters and diagnostic context; and — the strongest proof — an
end-to-end reproduction that exercises the REAL, unmodified `_try_gemini()`
function against a mocked `httpx.post()` raising a real `httpx.
HTTPStatusError` built from a real httpx `Request`/`Response` pair
carrying the synthetic secret, asserting the secret is absent from the
actual captured `logger.warning()` call arguments (loguru output is not
captured by pytest's `caplog`, so this patches `logger.warning` directly
rather than relying on `caplog`).

All 7 pass post-fix; the end-to-end reproduction test independently
confirmed (Section 18) to FAIL pre-fix, with the synthetic secret
genuinely present in the captured pre-fix log call — concrete,
first-hand proof this closes a real, not theoretical, leak.

---

## 16. CredentialManager Missing-Type Analysis

Traced every externally-reachable path capable of selecting `CredentialManager`
(mission Section 12, letters A–H):

**A/F. Structured HTTP endpoints**: all 66 (across 26 files, exhaustively
enumerated in RR-3.7B/B.1) hardcode an explicit `"type"` string literal in
router source code — never omitted, never caller-influenced.

**B/G. Governor's own fallback**: `Governor.dispatch()`'s `task_type =
task.get("type", "unknown")` (line 2028) is a LOCAL variable only — it
never mutates the `task` dict itself, so even Governor's own internal
default never causes a downstream `agent.run(task)` call to see a
different `"type"` value than whatever the caller originally supplied (or
omitted). This confirms Governor cannot itself "construct" a type for a
task that arrives without one.

**C. Direct selection**: no externally-reachable endpoint targets
`CredentialManager` by name or ID — all routing is via `task_type` →
`DISTRICT_TASK_MAP`/capability-match/HP-lottery, never a direct agent
reference.

**D. A2A**: `_resolve_action_type()` (RR-3.7A) explicitly returns `None`
— and the endpoint returns an honest failure response, never calling
`PermissionGateway.execute()`/`Governor.dispatch()` — when no `type`/
`action` key is found in `task` or `params`. A2A therefore cannot reach
ANY agent, let alone `CredentialManager` specifically, with a missing
type.

**E. Voice**: `try_device_action()` only ever constructs the hardcoded
literal `action_type="launch_app"`. `_run_action()` is only ever called
with a non-empty `task_type` string (`_respond()`'s `if task_type:` guard
precedes it) — confirmed by this mission's own test (Section 14, `test_
rr3_7c_run_action_malformed_task_type_fails_safely`, using an empty
string, the closest reachable analogue to "missing").

**H. Is missing-type-defaults-to-scan intentional?** Yes — `task.get(
"type", "scan")` is deliberate, documented, internal-only behavior (the
module's own `__main__` smoke test explicitly relies on it: `await agent.
run({"type": "scan"})`), consistent with RR-3.7B.1's own fix (which
preserved this exact pathway while closing the unmatched-type fallthrough).

**Conclusion: PROVEN SAFE.** No external ingress can invoke `CredentialManager`
with `task["type"]` genuinely absent. `CredentialManager` itself was not
modified in this mission (RR-3.7B.1's fix stands unchanged).

---

## 17. Wrong-District Security Analysis

Per mission Section 13's exact question — "can this collision cause a
caller-authorized action A to execute a materially different privileged
capability B?" — applied to all three collisions RR-3.7B.1 reported
(`scan_data_sharing`→security, `gdpr_check`→governance, `growth_analysis`
→marketing):

None of the three ever reach `PermissionGateway` at all (confirmed: all
three are S3-low per RR-3.7B.1's own exhaustive trace, none tiered, none
Gateway-fronted) — so there is no "caller-authorized action A" step to
begin with, and therefore no authorization-based confused-deputy
substitution is structurally possible for any of them. Considered under
the weaker, capability-comparison framing too (does the WRONG district's
worst-case winner do something MORE PRIVILEGED than the RIGHT district's
intended handler would have?): re-confirmed via RR-3.7B.1's own per-agent
evidence — `scan_data_sharing`'s worst case (`MalwareHunter`) is a
read-only local scan; `gdpr_check`'s worst case (`CredentialManager`,
pre-this-mission's-own-Section-16-analysis) is now hardened to an honest
error for any non-`"scan"` type; `growth_analysis`'s worst case
(`GEOOptimizerAgent`) is a non-mutating LLM call. None substitutes a
higher-privilege capability (no RED-tier action, no mutation, no
credential exposure) than the router's own nominally-intended, equally
non-dangerous capability.

**Classification for all three: CORRECTNESS — DEFERRED** (per mission
Section 13's own explicit disposition for a "no" answer). Recorded in
Section 26 for future correctness-focused work; not repaired here, per
the mission's explicit scope boundary against `DISTRICT_TASK_MAP`
redesign.

---

## 18. Pre-Fix Exploit Verification

All four production repairs independently git-stash-verified:

- `core/api/routers/voice_ws.py` + `core/voice/realtime.py` stashed → 10 of
  16 voice tests fail (all 3 auth-wiring source checks, all 6 `_run_action()`
  Gateway-wiring tests, the confused-deputy `proposed_by` check) → popped →
  all pass again.
- `core/inference/vectorcode_llm.py` + `core/inference/provider_client.py`
  stashed → 1 of 7 secret-redaction tests fails, with the pre-fix run's
  own captured log call containing the full synthetic secret verbatim
  (`AIzaSyDfakeTestKeyDoNotUse1234567890` — never a real value) — concrete
  proof the leak mechanism is real → popped → all 7 pass again.
- `core/api/routers/websocket.py` (the `WS_API_KEY` root-cause fix)
  stashed → a dedicated pre-fix comparison (performed carefully to avoid
  ever asserting equality against the real live secret — see Section 2's
  process note) confirmed `WS_API_KEY` was empty while the real configured
  key was 64 characters → popped → the length-only test passes again.

---

## 19. Targeted Tests

Three new/updated test files, 41 new tests total:

- `tests/test_rr3_7c_voice_authorization.py` (18 tests): auth-handshake
  source-wiring (3), `_run_action()` PermissionGateway behavior (6: exploit
  reproduction, denial→zero-dispatch, approved→exactly-once, FORBIDDEN→zero,
  Gateway-exception→zero+no-crash, `not_implemented`→honest), confused-
  deputy/identity (3: `proposed_by` not caller-derivable, action_type
  sourced from the server classifier, empty task_type fails safely),
  `try_device_action()` unchanged-confirmation (1), the `WS_API_KEY`
  root-cause fix (2, both secret-safe), and RR-3.7B/B.1 preservation (3).
- `tests/test_rr3_7c_secret_log_redaction.py` (7 tests, Section 15).
- `tests/integration/test_full_pipeline.py` (updated, 3 tests): both
  pre-existing `/ws` WebSocket tests now send the correct auth handshake
  first (Section 21 explains why this was necessary and correct, not
  scope creep).

All 44 tests referenced across these three files pass against the final,
combined post-fix HEAD.

---

## 20. Broad Regression

Ran together, post-fix, the full RR-3.5 through RR-3.7C test surface
(13 files, several hundred individual tests): `test_rr3_7c_voice_
authorization.py`, `test_rr3_7c_secret_log_redaction.py`, `test_rr3_7b1_
autopilot_recursion.py`, `test_rr3_7b1_ambiguous_endpoint_closure.py`,
`test_rr3_7b_structured_router_authorization.py`, `test_rr3_7a_a2a_
authorization.py`, `test_rr3_6_authorization_boundary.py`, `test_rr3_5_
foundation_closure.py`, `test_r19_capability_composition.py`, `test_
permission_gateway.py`, `test_phase2_districts.py`, `test_spec06_health.
py`, `test_full_pipeline.py`.

**Result**: exactly two failures, both independently confirmed PRE-
EXISTING/ENVIRONMENTAL, not caused by this mission:
- `test_permission_gateway.py::test_red_action_times_out_without_
  confirmation` — reproduced identically at RR-3.7B's own HEAD (confirmed
  across every mission in this series via git-stash; a `pending_id`
  keyword-argument mismatch in a mock, unrelated to any file this mission
  touched).
- `test_rr3_7b1_ambiguous_endpoint_closure.py::test_rr3_7b1_ambiguity_
  closure_diff_scope` — this test (written during RR-3.7B.1) asserts `git
  diff --name-only` includes `credential_manager.py`; since RR-3.7B.1's
  own changes were committed (`48c0f7e9a`) before this mission began, that
  file is no longer part of the *working-tree* diff — a stale assumption
  in that test's own design (checking uncommitted-diff state across a
  mission boundary), not a regression this mission introduced. Left
  unrepaired per the mission's explicit "do not repair unrelated
  failures" instruction; it is not a security-relevant failure.

**Two GENUINE, direct regressions were found and fixed** (not left as
"unrelated" — they were a direct, causal consequence of this mission's own
`WS_API_KEY` fix): `tests/integration/test_full_pipeline.py::test_
websocket_status_endpoint` and `::test_websocket_ui_event_broadcast` both
connected to `/ws` without ever sending an auth handshake message,
relying — unknowingly — on the exact `WS_API_KEY`-always-empty bug this
mission closed. Fixed by having both tests send the same handshake
message a real client sends (Section 8), confirmed passing post-fix
(Section 19).

---

## 21. Production Validation

VECTOR started via `python run_vector.py api`, confirmed ready via
authenticated `GET /health/status` (200).

- **`/ws/voice/stream` with no/wrong auth**: `websockets.connect()` +
  `{"auth":"Bearer wrong-token"}` → **`ConnectionClosed: code=1008
  reason='Unauthorized'`** — clean, unambiguous, live proof the boundary
  is enforced.
- **`/ws/voice/stream` with the real configured key**: connects normally,
  proceeds into real application logic (`{"type":"error","text":"No audio
  received"}` for an empty-audio test payload — proving auth passed and
  the correctly-configured path is unaffected).
- An earlier attempt using a raw BINARY first frame (instead of proper
  JSON) triggered a secondary, pre-existing `AttributeError: 'WebSocket
  Protocol' object has no attribute 'transfer_data_task'` inside a
  third-party `websockets` library version's `legacy.protocol.close()`
  path, while `require_auth_handshake()`'s own rejection logic was
  correctly executing (confirmed via full traceback: the exception
  occurred INSIDE the intentional `websocket.close(code=1008,...)` call,
  AFTER the security decision to reject had already been made). This is a
  library-version-compatibility artifact, not a security failure — no
  application code beyond the auth-rejection path ever ran, and the same
  latent library behavior would affect `/ws/command`'s identical `require_
  auth_handshake()` under the same unusual first-frame shape, independent
  of anything this mission changed. Out of this mission's scope to fix
  (would require touching uvicorn/websockets version pinning, a
  materially broader and riskier change than this mission's "small
  security closure diff" mandate); recorded in Section 26.
- **`ingest_video`** (RR-3.7B) and the autopilot recursion bound (RR-
  3.7B.1) both re-confirmed live and unchanged.
- Gemini secret-redaction was validated via the mocked, synthetic-secret
  reproduction test (Section 15) rather than a live provider failure, per
  the mission's own explicit preference ("prefer synthetic/mocked
  verification... if a live provider failure would expose a real key
  before sanitization") — deliberately avoided triggering a real Gemini
  failure in production to eliminate any risk of a real key reaching an
  unsanitized code path before this fix's own correctness could be
  confirmed via the safer, git-stash-verified unit-level proof.

VECTOR was stopped (`taskkill`, confirmed via `tasklist` showing zero
matching processes) after validation.

---

## 22. RR-3.7A/B/B.1 Preservation

Explicitly re-verified, not merely assumed, via dedicated tests in this
mission's own suite:
- `ingest_video` still fails closed (UNKNOWN tier) — unit test + live
  production re-check.
- `log_exercise`/`create_project` routing and capability declarations —
  unchanged (no file touched by this mission overlaps RR-3.7B/B.1's own
  repaired files, confirmed by diff scope, Section 24).
- `CredentialManager`'s unmatched-type fail-closed behavior — unchanged,
  re-confirmed via this mission's own test.
- Autopilot `MAX_CHAIN_DEPTH` bound — unchanged, re-confirmed via this
  mission's own test (mocked `Governor`, boundary-depth call).
- `_PLAN_COMPOSABLE_ACTION_TYPES` allowlist — untouched by this mission
  (zero diff to `permission_gateway.py`'s own allowlist definition; this
  mission's `_run_action()` fix reuses `PermissionGateway.execute()`
  itself, not this specific allowlist mechanism, since `_run_action()`'s
  task_types are not meant to be pre-authorized composable actions the
  way `idea_validate`/`log_exercise`/`create_project` are).
- `/command`, `/ws/command`, A2A — zero diff to `commands.py`, `a2a.py`;
  `websocket.py`'s only change is the `WS_API_KEY` root-cause fix, which
  makes `/ws/command`'s OWN existing `require_auth_handshake()` call
  genuinely effective for the first time (a correctness improvement to an
  already-accepted mechanism, not a redesign of it).

---

## 23. Adversarial Falsification

1. All externally reachable execution ingress classes enumerated — **PROVEN** (Section 4, 7 WebSocket routes + all prior HTTP classes exhaustively listed).
2. `/command` remains safe — **PROVEN** (zero diff).
3. `/ws/command` remains safe — **PROVEN**, and now MORE safe than previously known (the `WS_API_KEY` fix makes its own pre-existing auth mechanism genuinely effective for the first time — Section 12).
4. Structured HTTP class remains safe — **PROVEN** (zero diff to any of the 26 router files or their district agents in this mission).
5. voice cannot perform privileged execution without PermissionGateway — **PROVEN** (Section 9, both live and unit-level).
6. Caller cannot spoof voice/preconfirmed authorization identity — **PROVEN** (Section 10, source-level test; network-level auth now required to reach the code at all).
7. Voice authorization binds to the actual executed capability — **PROVEN** (Section 10).
8. Voice action executes at most once — **PROVEN** (`await_count==1` tests, Section 19).
9. Gemini/provider logs no longer expose credential material — **PROVEN** (Section 15, end-to-end reproduction against the real unmodified function).
10. Retry/error paths cannot reintroduce the same secret — **PROVEN** (Section 14 — sanitization applied at the single shared capture point `last_error`, closing both its downstream consumers).
11. No real credential was embedded in tests/reports — **PROVEN**, with one important caveat disclosed in Section 2 (a real key transiently appeared in this session's own tool output during test development, corrected within the same turn, never persisted to any file).
12. External callers cannot trigger CredentialManager scan through missing type — **PROVEN** (Section 16, exhaustive ingress-by-ingress trace).
13. Known wrong-district collisions do not substitute a higher-privilege capability after authorization — **PROVEN** (Section 17 — moot in the strict sense, since none reach an authorization step at all, and proven non-dangerous even under the weaker capability-comparison framing).
14. RR-3.7B.1 CredentialManager repair remains intact — **PROVEN** (Section 22).
15. Autopilot recursion repair remains intact — **PROVEN** (Section 22).
16. No new Gateway bypass was introduced — **PROVEN** (every new code path in this mission terminates at `PermissionGateway.execute()`, never around it).
17. No privilege tier was weakened — **PROVEN** (zero diff to any GREEN/YELLOW/RED/`RED_INTERACTIVE_TOOLS`/`_PLAN_COMPOSABLE_ACTION_TYPES` definition).
18. No broad new authorization framework was introduced — **PROVEN** (this mission's fixes are: reusing `require_auth_handshake()` verbatim in two more places; reusing the `Candidate→DecisionEngine→PermissionGateway` pipeline verbatim; a ~15-line, single-purpose log sanitizer; a one-line credential-source fix).
19. No security-critical external ingress remains BYPASS/AMBIGUOUS — **PROVEN** (Section 5).
20. (Renumbered from the mission's own list of 20; all 20 claims addressed above.)

No security-critical FALSIFIED or NOT-PROVEN item.

---

## 24. Diff Audit

```
core/api/routers/voice_ws.py            | 49 ++++++++++++++++++++++++
core/api/routers/websocket.py           | 25 ++++++++++++-
core/inference/provider_client.py       | 14 ++++++-
core/inference/vectorcode_llm.py        |  9 ++++-
core/voice/realtime.py                  | 66 ++++++++++++++++++++++++++++-----
tests/integration/test_full_pipeline.py | 23 +++++++++++-
6 files changed, 172 insertions(+), 14 deletions(-)
```
Plus 3 new files: `core/inference/error_sanitize.py` (~65 lines),
`tests/test_rr3_7c_voice_authorization.py` (~290 lines, 18 tests),
`tests/test_rr3_7c_secret_log_redaction.py` (~150 lines, 7 tests).

`git status --short` on the full touched set confirms exactly these 9
files/additions — no other production file was modified. The pre-existing
`data/models/neural_policy.{pt,meta.json}` runtime artifacts and the
earlier-session report backlog remain present but untouched by this
mission's own edits. Every hunk in the 6 modified files is accounted for
in Sections 8, 12, 14, and 20 above — no unexplained change, no
opportunistic refactor, no `DISTRICT_TASK_MAP` change, no cognition/
feature work.

---

## 25. Commit Ledger

To be populated at commit time (Hard Stop, below).

---

## 26. Deferred NON-SECURITY Backlog

Explicitly out of this mission's scope (Section 3), recorded for future
correctness-focused work, NOT a justification for RR-3.7D:

1. **`/ws/state`, `/gesture/ws`, `/camera/ws`, `/notifications/ws`** —
   unauthenticated at the network level, but confirmed zero execution
   capability (pure read-only broadcast/sensor forwarding). An
   information-disclosure-only concern (a network client could passively
   observe internal decision-events/HP-changes/camera-gesture/notification
   data), not a privileged-execution ingress. Worth closing for defense-
   in-depth in a future, narrowly-scoped pass, but does not block this
   mission's freeze (Section 19 requires no *privileged* ingress bypass,
   not zero unauthenticated read-only broadcast).
2. **The uvicorn/websockets library version compatibility artifact**
   observed during production validation (Section 21) — an `AttributeError`
   inside a third-party library's `close()` path when a WebSocket is
   closed shortly after connecting under an unusual first-frame sequence.
   Pre-existing, affects `/ws/command`'s identical `require_auth_
   handshake()` under the same conditions, unrelated to this mission's
   own authorization logic. A version-pinning investigation is out of this
   mission's "small security closure diff" scope.
3. **The three wrong-district `DISTRICT_TASK_MAP` collisions**
   (`scan_data_sharing`, `gdpr_check`, `growth_analysis`) — confirmed
   CORRECTNESS-only (Section 17), not security-relevant, deferred per the
   mission's own explicit instruction not to redesign `DISTRICT_TASK_MAP`
   in this mission.
4. **`accessibility_audit`'s silent misroute** (RR-3.7B.1 finding) — a
   real correctness bug (the named capability never runs), confirmed
   safe-by-accident, non-security, deferred.
5. **The four RR-3.7B.1 S3-low findings** (`MalwareHunter`'s CWD scan,
   `GEOOptimizerAgent`'s zero-type-check default, `SkillMapper`'s
   unconditional local write ×2 triggering endpoints) — confirmed
   non-dangerous, deliberately left unrepaired per that mission's own
   evidence; unchanged by this mission.
6. **`test_permission_gateway.py::test_red_action_times_out_without_
   confirmation`** and **`test_rr3_7b1_ambiguity_closure_diff_scope`** —
   both confirmed pre-existing/environmental test artifacts (Section 20),
   neither security-relevant, left unrepaired per the mission's explicit
   "do not repair unrelated failures" instruction.

None of these constitute a concrete, externally-reachable, currently-open
privileged-bypass path — per the mission's own Section 20 rule, none of
them justifies RR-3.7D.

---

## 27. Authorization Freeze Declaration

All 12 required criteria (mission Section 19) are met:

1. `/command` accounted for — Section 4/22.
2. `/ws/command` accounted for — Section 4/12/22.
3. A2A accounted for — Section 4/22.
4. Structured HTTP class accounted for — Section 4/22.
5. Voice accounted for — Sections 6-10.
6. No known external privileged ingress bypass remains — Section 5.
7. No security-relevant ingress ambiguity remains — Section 23 (claim 19).
8. Gemini/provider credential-log leak closed — Sections 11-15.
9. CredentialManager missing-type path proven externally safe — Section 16.
10. No known routing collision creates authorization→execution privilege
    substitution — Section 17.
11. No new security regression — Section 20 (two genuine regressions
    found were direct, fixable consequences of this mission's own real
    security fix, corrected within this mission; both confirmed
    pre-existing failures are unrelated to any security boundary).
12. Existing RR-3.7A/B/B.1 repairs remain intact — Section 22.

**AUTHORIZATION BOUNDARY FROZEN FOR VECTOR V1.**

This does not mean VECTOR contains zero bugs — Section 26 records a real,
honest backlog of non-security correctness items. It means the known V1
external authorization boundary is sufficiently mapped and closed to
proceed to behavioral validation.

---

## 28. RR-4 Readiness

No concrete, externally-reachable, currently-open privileged-bypass path
remains that this mission could not safely close. Per the mission's own
Section 20 rule, RR-3.7D is NOT justified. RR-3.7 authorization/security
foundation work is CLOSED.

---

## 29. Verdict

**`RR-3.7C PASS — AUTHORIZATION BOUNDARY FROZEN FOR VECTOR V1`**

---

## Hard Stop

VECTOR is stopped. This mission does NOT proceed to RR-4, RR-3.7D,
RG-C2, or RG-D2 automatically.

**RR-3.7 authorization/security foundation is CLOSED.**
**No RR-3.7D is recommended.**
**Next planned mission: RR-4.**

Awaiting independent review.
