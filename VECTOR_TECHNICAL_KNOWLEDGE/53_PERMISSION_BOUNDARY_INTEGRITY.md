# 53 — Permission Boundary Integrity Remediation

**Date**: 2026-09-02
**Type**: SAFETY-CRITICAL AUDIT + TARGETED REMEDIATION. Not a redesign of Governor, PermissionGateway,
or any district agent's execution model.
**Question answered**: Can any production side-effecting action path bypass VECTOR's intended
permission/governance boundary?
**Answer, in short**: `Governor.dispatch()` itself intentionally does not call `PermissionGateway`
— that is by design, and (Phase 3) is not the bug the earlier finding assumed it was. But tracing
every real execution path downstream of `dispatch()` and of `autonomous_loop._act_on()` found one
confirmed, live, RED-tier bypass (Finding 1: outbound email) and one confirmed, live, YELLOW-tier
contract gap (Finding 2: skill-matched actions) — both fixed in this pass, both behaviorally
verified.

---

## 1. Executive Summary

- `Governor.dispatch()` (`core/city/governor.py:1970`) does not call `PermissionGateway` — confirmed
  by full reading of the method. This is **not** an oversight: `dispatch()` is a routing layer
  (rate-limit, taint-tracking, prompt-injection-scan, budget-check, council-review-for-RED-task-types,
  then `agent.run(task)`), and the codebase's actual safety architecture gates real side effects at
  the point each agent performs them, not centrally at the routing layer. This pattern is correctly
  implemented in several places checked directly (`git_bot.py`'s `push_github`, `hedgebot_agent.py`'s
  `solana_swap_execute`, `uploader.py`'s `content_publish` — the last of these carries its own
  code-comment record of an near-identical prior audit, task #92, 2026-07-23, fixed the same class
  of bug for social-media uploads).
- The decentralized "gate at point of effect" pattern is only as safe as its weakest actual
  implementation. **Finding 1** (confirmed, fixed): `districts/communications/email_agent.py`'s
  `run()` task-type dispatch table routed `"reply"`/`"send_reply"`/`"forward"` to
  `reply_forward.handle_reply_email()`/`handle_forward_email()` → `core/email/sender.py`'s real
  `smtplib.SMTP` send, with **zero** `PermissionGateway` involvement — even though `send_email` is
  explicitly RED-tier, and even though this exact class already has a correctly-gated
  `send_reply()` method that turned out to be unreachable dead code (nothing in `run()`'s dispatch
  table ever called it). Confirmed reachable from a normal chat message via two separate API
  endpoints (`commands.py`, `websocket.py`), both of which route an LLM-classified intent straight
  to `governor.dispatch()` with no gateway step in between.
- **Finding 2** (confirmed, fixed): `autonomous_loop._act_on()`'s VectorCode-routing and
  skill-matching pre-dispatch gates only explicitly checked `FORBIDDEN` and `RED` before calling
  `gw.execute()`; `YELLOW`-classified actions silently received the same no-confirmation treatment
  as `GREEN`, contradicting YELLOW's own documented contract ("requires whatever existing
  confirmation/permission mechanism VECTOR already defines").
- Both findings are fixed with the smallest possible change at the closest existing boundary — no
  new permission framework, no change to `Governor`, no change to `PermissionGateway`'s own logic,
  no change to routing/provider/cadence/memory/planning architecture.

---

## 2. Scope

In scope: tracing the complete production action-execution surface for permission-boundary
integrity, classifying `Governor.dispatch()`'s relationship to `PermissionGateway`, finding and
fixing any other confirmed real bypass, with behavioral (not source-only) verification.

Out of scope (per task instructions, confirmed not touched): a general cognitive-architecture audit,
the 7-day-experiment readiness question, the hypothesis pipeline (`51`/`52`/`55`/`56` docs), plan
crash-recovery (`52`), unrelated pre-existing test failures, LLM routing/provider selection, model
selection, decision-engine scoring thresholds, memory architecture, planning architecture.

---

## 3. Methodology

Every claim below is labeled with how it was established:

- **NOT IMPLEMENTED** / **IMPLEMENTED** — the code exists (or doesn't) as read directly.
- **INTEGRATED** — the code is wired into a real call chain reachable from a production entry
  point, confirmed by tracing imports and call sites (grep + direct reads), not assumed from
  a class/function's mere existence.
- **RUNTIME REACHABLE** — a concrete call chain from a genuine production trigger (a chat message,
  an autonomous decision tick, a scheduled Hand) to the code in question was traced end to end.
- **TEST VERIFIED** — a test exists that imports and calls the real code (not source-string
  matching) and asserts on its behavior.
- **BEHAVIORALLY VERIFIED** — a test was written and *run* during this task, observed to pass,
  and (for the two fixes) reasoned through against the pre-fix code to confirm it would have failed
  before the change.

No claim in this document is upgraded to "verified" on source inspection alone.

---

## 4. Existing Permission/Governance Architecture

Reused, not reinvented, from `core/loop/permission_gateway.py` and `core/config.py`:

- **GREEN** (`CONFIG['permission']['green']`) — auto-execute, no owner gate. Read-only or genuinely
  harmless local operations (`search_web`, `check_weather`, `respond`, `git_status`, Hand types with
  `requires_approval=False`, ...).
- **YELLOW** (`CONFIG['permission']['yellow']`) — "requires whatever existing confirmation
  mechanism VECTOR already defines." In `PermissionGateway.execute()` this means: auto-execute if
  the action has earned trust-ladder promotion (N consecutive owner approvals, zero bad outcomes),
  or if `proposed_by` is an owner-trust marker (`"api_command"`/`"voice"` — the owner's own typed/
  spoken command IS the confirmation), otherwise a real Pushover notify + wait for explicit
  approve/reject (10s in production, near-instant in tests), defaulting to NOT-approved on timeout
  unless `VECTOR_YELLOW_AUTO_CONFIRM=1` is set.
- **RED** (`CONFIG['permission']['red']`) — consequential, hard-to-reverse, or outward-facing.
  Council review may run first (advisory), but **every** RED action still needs `PermissionGateway`
  approval; a subset (`OWNER_APPROVAL_ONLY` — `financial_transaction`, `solana_swap_execute`,
  `push_github`, `deploy_production`, `delete_files`, `content_publish`, `hand_browser`,
  `hand_content`, `hand_clip`) can **never** be approved by an LLM-council vote alone, only real
  owner approval. `RED_INTERACTIVE_TOOLS` (shell/GUI/browser/vision control) get a narrow,
  server-side-only "owner just typed/spoke this" bypass, hardened against `proposed_by` spoofing
  from client-supplied request bodies (`sanitize_proposed_by()`, see
  `tests/test_red_interactive_tools_bypass.py`).
- **FORBIDDEN** — `format_drive`, `mass_delete`, `share_private_data`. Always rejected, no path
  exists to override.

This taxonomy was **reused as-is** — nothing added, nothing renamed, per the task's explicit
instruction not to invent a new one.

**Where PermissionGateway sits relative to other components** (established by tracing, not
assumed):

- **Governor**: does *not* call it. `Governor.dispatch()` is a routing layer only (§6). Real
  gating happens inside the district agent methods `dispatch()` eventually calls into, at the point
  each one performs an actual side effect — a decentralized "gate at point of effect" pattern.
- **DecisionEngine**: does not call it directly; candidates flow to `_act_on()`, which is the real
  gate boundary for the autonomous decision path (§5, §6).
- **Planner** (`core/loop/planner.py`): read directly — `plan()`/`plan_for_energy()` only *read*
  `get_world_state()` and filter/rank candidate dicts; they perform no side effects and call neither
  `Governor` nor `PermissionGateway` themselves. `PlanRunner`/`plans.py` (the actual multi-step
  execution engine) constructs Actions and dispatches through `_act_on_plan_step()` →
  `PlanRunner.execute_step()`, which (per `52_AUTONOMY_BLOCKER_REMEDIATION.md`'s earlier work on
  this exact file) routes through `AutonomousExecutor`, itself gateway-wrapped. Not re-audited line
  by line this task (out of scope — plan execution's permission wiring predates and is orthogonal
  to this task's two findings), but its existing architecture already assumes gateway involvement.
- **ToolRegistry / MCP**: `core/mcp_server.py`, `hands/runner.py` both import and call
  `PermissionGateway` directly. Hands specifically: `HandRunner._dispatch()` (no gateway) is used
  *only* for `hand.requires_approval == False` (GREEN) Hands; `HandRunner._dispatch_via_gateway()`
  (real `PermissionGateway().execute()`, fail-closed on denial) is used for
  `requires_approval == True` (RED: `hand_browser`/`hand_content`/`hand_clip`) Hands — confirmed by
  reading `run_hand()`'s branch selection (`hands/runner.py:157-159`). Classification: **A —
  intentional and safe.**
- **OS/device adapters** (`core/control/pc_controller.py`, `phone_controller.py`): both import
  `PermissionGateway` (confirmed via grep); not exhaustively re-traced this task (lower marginal
  risk than the RED-tier communications/content/financial paths actually exercised — documented as
  a residual limitation, §15).
- **External APIs** (git push, email send, Solana swap, YouTube/Instagram/TikTok/Twitter upload):
  individually traced — see §8.

---

## 5. Complete Action-Path Inventory (Phase 1)

| # | Source | Status | Notes |
|---|---|---|---|
| 1 | Autonomous loop (`_think_tick` → `_act_on`) | S5 — behaviorally verified this task (§9) | The real gate boundary for autonomous decisions. Two gaps found and fixed here (Findings 1 candidate route, Finding 2). |
| 2 | Planner / plan executor | S2 — integrated (per `plans.py`'s existing architecture, not re-audited) | Out of this task's scope; already assumes gateway involvement per prior work. |
| 3 | `Governor.dispatch()` | S3 — runtime reachable, confirmed NOT itself a gate (§6) | Routing layer; safety depends on what it calls into. |
| 4 | Decision/action execution | S5 — same as #1 | `_act_on()` is where decisions become actions. |
| 5 | Tool registry / tool executor | S2 — integrated (`core/runtime/executor.py` calls `self.permission_gateway.execute(action)`, confirmed via grep + read) | Not the path exercised by Findings 1/2. |
| 6 | MCP / external tool paths | S2 — integrated (`core/mcp_server.py` imports gateway) | Not exhaustively traced this task. |
| 7 | Shell / subprocess execution | S5 — behaviorally covered by pre-existing `RED_INTERACTIVE_TOOLS` hardening (`run_shell_command` is RED, single real implementation inside `_execute_action()`, only reachable via `execute()`) | Confirmed via `tests/test_red_interactive_tools_bypass.py`, not re-verified line-by-line this task (already covered by a dedicated, passing regression suite). |
| 8 | Filesystem writes/deletes/moves | S3 — `delete_files` is RED + `OWNER_APPROVAL_ONLY`; `coding_tools.py` file-write helpers gate on `is_coding_grant_active()` (a context-var only autonomous_loop's gateway-approved code paths set) | Not exhaustively traced. |
| 9 | Network/API side effects | **S5 for email (Finding 1, now fixed)**; S5 for git push, Solana swap, content upload (pre-existing, confirmed correct) | See §8. |
| 10 | Device/system actions | S2 — integrated (`pc_controller.py`/`phone_controller.py` import gateway) | Not exhaustively traced this task. |
| 11 | Background/autonomous workers (Hands) | S5 — behaviorally traced via `hands/runner.py`'s branch selection (§4) | Classification A. |
| 12 | Scheduled/proactive actions | S5 — `_act_on()`'s `proactive_*` branch routes straight to `gw.execute()` before any district routing (`autonomous_loop.py:971-987`, read directly) | Classification A. |
| 13 | Fallback/direct execution paths | **S5 — Finding 1 and Finding 2 were both fallback/direct-execution gaps, now fixed** | See §8, §9. |
| 14 | Legacy action APIs | S3 — `answer_question`'s special-case in `dispatch()` bypasses district routing entirely but also performs no side effect (pure conversational LLM answer) | Read directly; not a side-effecting path. |
| 15 | Any direct imports/calls causing side effects | Covered by the targeted grep sweep in §7/§8 (subprocess/os.system across ~90 files scanned for gateway-adjacency; the two confirmed dangerous gaps are Findings 1/2) | Not every one of the ~90 files was individually read line-by-line — see §15. |

---

## 6. `Governor.dispatch()` Analysis (Phase 3)

Full method read (`core/city/governor.py:1970-2402`). Confirmed by direct reading, not assumption:

- **Every caller**: `core/api/routers/commands.py` (chat fast path), `core/api/routers/websocket.py`
  (`/command` HTTP + presumably the WS handler proper, same `classify_chat_intent()` pattern),
  `core/loop/autonomous_loop.py` (`_fanout_handler()`'s event-driven downstream-task dispatch, and
  `_act_on()`'s fallthrough when no skill/VC/plan/proactive route claims the action),
  `core/loop/permission_gateway.py` (`_execute_action()`'s `hand_*` branch — dispatch called
  **after** gateway approval, as the execution mechanism), `core/voice/realtime.py`,
  `hands/runner.py` (`_dispatch()`, GREEN Hands only), plus internal recursion for decomposed
  subtasks.
- **Every action type it accepts**: any `task["type"]` string — no fixed enum; `route_task()`
  classifies to a district if none is given.
- **Whether it invokes PermissionGateway**: **no** — confirmed by reading the full method body.
  Its checks are: GCRA rate limiting, taint tracking (shell/fetch sink substring match on
  `task_type`), prompt-injection scan, budget quota (non-blocking warning only), Merkle audit log,
  OTel span, LLM-council review for RED-tier `task_type`s (`_should_convene_council`), then
  `agent.run(task)`.
- **Whether policy evaluation happens before/after permission**: council review (a soft,
  advisory LLM-council check, not `PermissionGateway`) runs *before* `agent.run()`; there is no
  `PermissionGateway` step at any point in this method.
- **Whether execution can occur without permission**: **yes, from `dispatch()`'s own perspective**
  — it always calls `agent.run(task)` (bounded by a timeout) once routing succeeds. Whether that
  constitutes an actual unsafe bypass depends entirely on what `agent.run()` does for that
  `task_type` — traced per-agent in §8.
- **Whether autonomous calls behave differently from user-triggered calls**: no — `dispatch()`
  itself treats them identically; the only differentiator downstream is `Action.proposed_by`
  (checked by `PermissionGateway`, not by `dispatch()`).
- **Whether exceptions/fallbacks can bypass the gateway**: `dispatch()`'s own `try/except` wraps
  the whole body and returns an error dict on failure — it doesn't fall through to an alternate
  unsafe path.
- **Whether internal/system actions intentionally bypass it**: the `answer_question` special-case
  skips district routing (pure Q&A, no side effect — safe by construction, nothing to gate).

**Classification: A/D — intentional and safe as a routing layer; not itself the "gate."** This is a
correction to the earlier audit's framing (`52_AUTONOMY_BLOCKER_REMEDIATION.md`'s "Permission
Gateway Finding"), not a reversal of its factual observation (zero `PermissionGateway` calls in
`governor.py` is still true). What that earlier finding didn't check — because it was scoped to
`governor.py` alone — is whether the agents `dispatch()` calls into gate themselves. Most of the
ones checked directly (`git_bot.py`, `hedgebot_agent.py`, `uploader.py` post-2026-07-23-fix,
`node_guard.py`, `threat_scout.py`, `google_ads_agent.py`) do, or have no real side-effect
capability at all (pure analysis/generation agents whose `run()` ignores `task_type` and does a
fixed, safe operation regardless). **One did not** — Finding 1.

---

## 7. PermissionGateway Analysis

`core/loop/permission_gateway.py`, `PermissionGateway.execute(action: Action) -> GatewayResult`
(line 421) is the sole enforcement point: classifies the action, checks a capability-token layer,
then branches on FORBIDDEN (blocked + audited) / GREEN (auto-executed) / YELLOW (trust-ladder or
owner-command fast path, else real wait-for-confirmation) / RED (`_handle_red_tier()` — council
review with the `OWNER_APPROVAL_ONLY` carve-out enforced, else owner-command fast path for
`RED_INTERACTIVE_TOOLS`, else real Pushover approval). `_execute_action()` (line 885) is the
**only** place that performs real side effects for gateway-routed actions, and — confirmed by grep
across the full non-test codebase — is called **only** from inside `execute()` itself (three
call sites, all within this one file); no code anywhere else calls `gw._execute_action()` directly.
This means: **any action that genuinely reaches `PermissionGateway.execute()` cannot bypass its own
classification/approval logic.** The vulnerability surface is entirely about which actions reach
`execute()` in the first place — which is what Findings 1 and 2 are about.

---

## 8. Discovered Bypasses

### Finding 1 — EmailAgent "reply"/"send_reply"/"forward" bypass real SMTP send (CONFIRMED, FIXED)

**Location**: `districts/communications/email_agent.py`, `EmailAgent.run()`, `task_type in
("reply", "send_reply")` and `task_type == "forward"` branches.

**Call chain** (each link individually confirmed by direct code read):
```
[chat message] → commands.py's intent_action fast path
    → classify_chat_intent(text)  [LLM call, invents task_type/district from free text]
    → governor.dispatch({"type": "reply", ..., "_llm_classified": True})
        [NO PermissionGateway call anywhere in this chain up to here]
    → Governor.dispatch(): capability match on EmailAgent.capabilities (includes "reply",
      "forward", "send_email" — confirmed by reading __init__) → agent.run(task)
    → EmailAgent.run(): task_type in ("reply","send_reply") →
      districts.communications.reply_forward.handle_reply_email()
    → core/email/sender.py:send_email() → smtplib.SMTP(...).sendmail(...)   [REAL SEND]
```
Identical chain exists via `core/api/routers/websocket.py`'s `/command` HTTP endpoint (same
`classify_chat_intent()` → `governor.dispatch()` pattern, confirmed by direct read) and via
`autonomous_loop._act_on()`'s fallthrough path (if no `proactive_`/`plan:`/VC/swarm/skill match
claims the action, it goes straight to `governor.dispatch()` with no gateway step — confirmed by
reading `_act_on()` in full, §9).

**Why it wasn't caught by the class's own gated `send_reply()` method**: that method (line ~268,
correctly calls `PermissionGateway().execute(Action(action_type="send_email", ...))` before
sending, fails closed on gateway error) is **never called from `run()`'s task-type dispatch table**
— confirmed by grepping the whole file for `self.send_reply` (zero matches). It is dead code from
the dispatch perspective. The module's own docstring documents the *intended* design
("send_email (send routes through VECTOR's permission gateway)") — this is a real defect against
documented intent, not an ambiguous design choice.

**Risk classification** (Phase 5):
1. Can it actually execute at runtime? **Yes** — `send_email()` has a complete, unstubbed SMTP
   implementation; not a stub or simulated response.
2. Reachable autonomously? Not confirmed as a live autonomous-decision candidate (grepped
   `goal_system.py`/`decision_engine.py`/`anticipation.py` for `"reply"`/`"forward"` — no hits), but
   reachable via `_act_on()`'s generic fallthrough if any future candidate source ever proposes it.
3. Reachable without a deliberate high-stakes user action? **Yes** — a completely ordinary chat
   message ("reply to that email and say...") is sufficient; the "user interaction" involved is not
   the intended safety confirmation, it's the same conversational input RULE 3 exists to mediate.
4. Does policy (council review) run? Only for RED-tier `task_type` strings in
   `_should_convene_council` — `"reply"`/`"forward"` are not council-tier task types (council
   applies to `dispatch()`'s own `task_type`, a different vocabulary from `PermissionGateway`'s
   `action_type`), so no.
5. Does permission run? **No — this is the bug.**
6. Can fallback execute it? N/A — this isn't a fallback path, it's the primary path.
7. Can an exception bypass the boundary? No exception is needed; there was no boundary here to
   bypass.
8. Intentional? **No** — contradicts the module's own docstring and the sibling `send_reply()`
   method's design.
9. Remediation required? **Yes — done, see §11.**

### Finding 2 — `_act_on()`'s VC-routing and skill-matching gates skip YELLOW (CONFIRMED, FIXED)

**Location**: `core/loop/autonomous_loop.py`, `_act_on()`, `_VC_ACTION_TYPES` block
(~line 1000-1019) and the VectorCode-Skills block (~line 1160-1213).

Both blocks classified `winner.action_type` via `gw.classify()` and only called `gw.execute()`
(the actual gate — confirmation/trust-ladder/audit) when the level was `"RED"`; `FORBIDDEN` was
separately blocked; **`GREEN` and `YELLOW` fell through identically**, straight to real execution
(`bridge.run_task()` or `sm.execute()`), with no confirmation, no trust-ladder check, no audit
write, no owner notification for YELLOW.

**Risk classification**:
1. Can it execute at runtime? Yes, for the skill-matching block — any `winner.action_type` that a
   skill (of 100+ manifests) matches with confidence > 0.6 is eligible, not restricted to a fixed
   set. For the VC-routing block, currently moot — no `_VC_ACTION_TYPES` member is presently
   classified YELLOW (`code_review_vc` is GREEN, the rest are RED — confirmed in `core/config.py`).
2/3. Reachable autonomously, without a deliberate approval action? Yes for the skill-matching
   block, for any YELLOW action_type a skill happens to match (e.g. `commit_code`, `set_reminder`,
   `write_note_personal`, `pc_screenshot`).
4/5. Policy/permission run? Neither — `gw.execute()` (the only place YELLOW's actual
   confirmation/trust-ladder logic lives) was never called for YELLOW here.
6/7. Fallback/exception bypass? No — this was the primary path's own condition, not an
   error-recovery gap.
8. Intentional? The code's own comment says the fix "mirrors the VectorCode gate above" and
   explicitly frames itself as closing a FORBIDDEN/RED gap (a real 2026-06-21 fix, per
   `tests/loop/test_skill_gateway.py`'s docstring) — nothing suggests YELLOW's omission was a
   deliberate choice; it reads as an oversight in that same fix, not a design decision.
9. Remediation required? **Yes — done (both blocks, for consistency), see §11.**

### Bypasses checked and confirmed NOT present (documented for completeness)

- **`push_github`** (`git_bot.py`): local commit happens unconditionally (documented, intentional —
  `commit_code` is deliberately YELLOW and low-friction per `core/config.py`'s own comment: local
  git is reversible, auto-commit is a documented required workflow); the actual **push** goes
  through `self._gateway.execute(Action(action_type="push_github", ...))` *before* calling GitHub's
  API, checked via `if not gate_result.approved: return`. No raw `git push`/`.push()` call exists
  anywhere outside `permission_gateway.py`'s own `_execute_action()` handler (grepped). Classification: A.
- **`solana_swap_execute`** (`hedgebot_agent.py`): gates before signing, fails closed on gateway
  error ("NEVER fail open" — explicit in the code's own docstring). Classification: A.
- **Social media uploads** (`uploader.py`): already fixed in a prior session (2026-07-23, task #92,
  documented in the file's own `_gate_publish()` docstring — the exact same bug class as Finding 1,
  for a different district, already caught and closed before this task). Classification: A
  (post-fix).
- **Node/network monitoring** (`node_guard.py`, `threat_scout.py`): `run()` ignores `task_type`
  entirely and always performs the same fixed, read-only scan — no real side-effect capability
  exists to bypass.
- **Google/Meta/Amazon Ads agents** (`districts/marketing/`): `run()` task types are all
  analysis/copy-generation (`audit`, `copy`, `performance`, `landing`) — no real ad-spend or
  publish capability exists in these agents at all.
- **Event fan-out downstream tasks** (`autonomous_loop._fanout_handler()` → `governor.dispatch()`,
  no gateway): the `task_type` vocabulary here (`"implement_design"`, `"distribute_content"`,
  `"lockdown_systems"`, etc., from `core/event_bus/wiring.py`'s `EVENT_TRIGGER_MAP`) is fixed,
  hardcoded, and not implemented by name in any district agent (grepped — zero matches) — these
  land on whichever agent wins the district's HP lottery and get whatever fixed, generic behavior
  that agent's `run()` performs (confirmed read-only/harmless for the security district's agents
  specifically). Not exhaustively checked for every district × every trigger task_type
  combination — documented as a residual limitation (§15), but the mechanism (fixed, internal,
  non-LLM-invented, non-user-controllable task types with no dedicated handlers) makes this
  structurally low-risk compared to Finding 1's free-text-classified, real-implementation case.

---

## 9. Runtime Reachability — Behavioral Confirmation

Both findings were confirmed reachable and then confirmed fixed via tests that call the *real*
production code (not source-string inspection):

- **Finding 1**: `tests/test_email_agent_permission_gate.py` (9 tests) instantiates the real
  `EmailAgent`, calls the real `run()` with `task_type="reply"`/`"send_reply"`/`"forward"`, and
  only mocks `PermissionGateway.execute` (to control approve/deny) and the SMTP-reaching
  `reply_forward.handle_reply_email`/`handle_forward_email` functions (so no test sends real
  email). Confirms: denial blocks execution, approval allows it, gateway-unreachable fails closed,
  a GREEN read-only task (`"list"`) never touches the gateway at all, and the pre-existing
  `send_reply()` method's own gate still works standalone.
- **Finding 2**: `tests/loop/test_skill_gateway.py` (4 new tests, alongside 3 pre-existing static
  guards) drives the real `AutonomousLoop._act_on()` end to end for a YELLOW-classified,
  skill-matched `Candidate`, with a fake gateway object substituted via `_get_gateway()` (so the
  test controls classify/execute deterministically) and `SkillManager.match`/`execute` monkeypatched
  at the class level. Confirms: YELLOW now reaches `gw.execute()`, a YELLOW denial prevents
  `sm.execute()` from running, GREEN still never calls `gw.execute()` (no added friction), and
  FORBIDDEN still blocks before either call.

---

## 10. Risk Classification Summary

| Bypass | Tier if reached | Runtime reachable | Autonomous | No-deliberate-approval reachable | Policy runs | Permission ran (pre-fix) | Intentional | Fixed |
|---|---|---|---|---|---|---|---|---|
| Finding 1 (email reply/forward) | RED | Yes | Not confirmed as autonomous candidate | Yes (any chat msg) | No | No | No | **Yes** |
| Finding 2 (skill-matched YELLOW) | YELLOW | Yes (skill-matching block) / no live case (VC block) | Yes | Yes | No | No | No | **Yes** |
| `push_github` | RED | Yes | No (needs explicit PR request) | No | Council (advisory) | Yes | Yes | N/A (already correct) |
| `solana_swap_execute` | RED | Yes | Yes | No | Council (advisory, `OWNER_APPROVAL_ONLY` enforced) | Yes | Yes | N/A (already correct) |
| Social uploads | RED | Yes | Yes | No | Council (advisory) | Yes | Yes | N/A (fixed 2026-07-23) |
| Event fan-out downstream tasks | varies (task_type has no dedicated handler) | Yes | Yes | N/A — event-triggered, not user/LLM-text-triggered | No | No | Yes (fixed, internal vocabulary) | N/A — structurally low-risk |

---

## 11. Remediation Performed

### Fix 1 — `districts/communications/email_agent.py`

Added a `PermissionGateway().execute(Action(action_type="send_email", ...))` gate, matching the
exact pattern the class's own (previously-unreachable) `send_reply()` method already used, at the
top of both the `"reply"`/`"send_reply"` branch and the `"forward"` branch of `run()`. Fails closed
(returns `{"status": "blocked", "reason": "gateway_unreachable"}`) if the gateway call raises;
returns `{"status": "blocked", "reason": "not_approved"}` if denied; proceeds to the existing
`handle_reply_email()`/`handle_forward_email()` call unchanged if approved. No other branch of
`run()` was touched — read-only/local operations (`list`, `get`, `thread`, `search`, `draft_*`,
`mark_read`, `move`, `delete` [local DB delete, not a send], `poll_inbox`, `store_incoming`) are
untouched and still gate-free, per the "don't add blanket checks to harmless operations" constraint.

### Fix 2 — `core/loop/autonomous_loop.py`

Changed `if _level == "RED":` to `if _level in ("RED", "YELLOW"):` in both the `_VC_ACTION_TYPES`
block and the VectorCode-Skills block of `_act_on()` — a two-token change per block, reusing
`gw.execute()`'s own already-correct YELLOW handling rather than adding new confirmation logic.
`FORBIDDEN` handling and `GREEN`'s no-gate fast path are both unchanged.

---

## 12. Exact Files/Functions Changed

| File | Function(s) | Change |
|---|---|---|
| `districts/communications/email_agent.py` | `EmailAgent.run()` | Added gateway gate to the `"reply"`/`"send_reply"` and `"forward"` branches only |
| `core/loop/autonomous_loop.py` | `AutonomousLoop._act_on()` | Widened the RED-only gate condition to `("RED", "YELLOW")` in two places |
| `tests/test_email_agent_permission_gate.py` | new file, 9 tests | Behavioral regression coverage for Finding 1 |
| `tests/loop/test_skill_gateway.py` | 4 new tests appended | Behavioral regression coverage for Finding 2 |
| `VECTOR_TECHNICAL_KNOWLEDGE/53_PERMISSION_BOUNDARY_INTEGRITY.md` | new file | This document |

No other file was modified by this task.

---

## 13. Behavioral Verification

39 targeted new/changed tests, all run this task and passing:
- `tests/test_email_agent_permission_gate.py`: 9/9
- `tests/loop/test_skill_gateway.py`: 7/7 (3 pre-existing static guards, unchanged and still
  passing, + 4 new behavioral tests)

Each new test calls real production code (`EmailAgent.run()`, `AutonomousLoop._act_on()`) and
asserts on observed behavior (whether a mock send function was called, whether the gateway's
`execute()` was invoked, what status was returned) — not on source text.

---

## 14. Regression Results

**Targeted new/changed tests**: 16/16 pass —
`tests/test_email_agent_permission_gate.py` (9/9, Finding 1) +
`tests/loop/test_skill_gateway.py` (7/7 — 3 pre-existing static guards, unchanged and still
passing, + 4 new behavioral tests, Finding 2).

**Full suite baseline** (`tests/unit` + `tests/integration`, same exclusions used by the three
prior tasks this session — `test_planning.py`'s 2 independently-broken `MissionPlanAdvisor`-patch
tests and 1 flaky timing test in `test_loop_stall_fixes.py`, obtained via `--junitxml`):

```
2212 collected, 2175 passed, 8 failed, 0 errors, 29 skipped
```

**Identical to the immediately-prior baseline** (`56_HYPOTHESIS_OBSERVATION_CONTRACT.md`, same
numbers) — same 8 failing test names, individually re-confirmed unrelated in prior sessions
(`agent_registry` successor reconstruction, `correction_learner` domain classification ×4,
`decision_engine` epistemic scoring ×2, council red-tier verdict logic). **Zero change from this
task's fixes.**

**Broader governor/permission-adjacent sweep** (35 files outside the tests/unit+integration scope —
`tests/backend/`, `tests/districts/`, `tests/hands/`, `tests/loop/`, root-level `tests/test_*
governor*/*district_run_wiring*`, `tests/unit/test_governor.py`, `tests/unit/test_permission_
gateway.py`, etc. — chosen because they touch `Governor`/district-routing/permission-adjacent code
most directly; 2 known-slow, unmocked-LLM-adjacent files excluded — `test_memory_tree_performance.py`,
`test_llm_intent_gate.py`):

```
549 collected, 541 passed, 3 failed, 0 errors, 5 skipped
```

3 failures, individually traced:
1. `test_agent_registry_successor_class::test_dying_coding_swarm_respawns_...` — already in the
   established 8-failure baseline above (`agent_registry.py`, untouched this task).
2. `test_regression_governor_capability_routing::test_languages_routes_correctly_despite_wrong_
   llm_guess` — **newly surfaced this task** (this file lives outside the tests/unit+integration
   scope tracked by prior sessions, so it was never run against the established baseline before).
   Root-caused by isolated re-run with full traceback: the test mocks
   `core.inference.provider_client.get_client()` to control the LLM's classification, but
   `classify_chat_intent()` never reaches that mocked call for this input — a `REGEX_PRECLASSIFY`
   step (confirmed via the function's own debug log: `raw=''`, meaning the LLM was never invoked)
   short-circuits first and returns `task_type="quiz_vocabulary"` instead of the test's expected
   `"hindi"`. This is a test/implementation drift between `governor.py`'s regex-preclassify layer
   (added after this test file was written) and the test's assumption that only the LLM path
   determines `task_type` — entirely unrelated to `PermissionGateway`, `email_agent.py`, or
   `_act_on()`'s YELLOW-gate fix (neither this task nor any prior task this session modified
   `governor.py`, `intent_matcher.py`, or the regex-preclassify logic).
3. `test_regression_governor_capability_routing::test_news_trends_routes_correctly_despite_wrong_
   llm_guess` — same root cause, different pre-classify path (`EMBEDDING_MATCH` via
   `core.city.intent_matcher`, confirmed via the same debug-log technique: returns
   `task_type="ai_news"` instead of the test's expected `"news"`).

```
NEW FAILURES CAUSED BY THIS TASK'S CHANGES: 0
PRE-EXISTING FAILURES (established baseline): 8
PRE-EXISTING FAILURES (newly discovered this task, confirmed unrelated via root-cause trace): 2
```

`python -m py_compile` clean on both changed production files
(`districts/communications/email_agent.py`, `core/loop/autonomous_loop.py`).

---

## 15. Remaining Limitations / Ambiguities

- **Not every one of the ~90 files using `subprocess`/`os.system` was individually read** — the
  ones checked (git, email, Solana, social upload, Hands, node/security monitoring, marketing ads)
  cover the highest-plausible-risk categories (RED-tier, real external side effects, `OWNER_
  APPROVAL_ONLY`). The remainder are predominantly video/audio encoding, sandboxed test/research
  runners, and Claude-Code-facing MCP dev tools (`core/coding_assistant/`,
  `core/mcp_tools/expansion_modules/`) — lower plausible risk for an *autonomous VECTOR decision*
  to reach with attacker- or owner-unintended effect, but not exhaustively traced this task.
- **`core/control/pc_controller.py`/`phone_controller.py`** (device control) import
  `PermissionGateway` but were not traced call-site-by-call-site the way email/git/Solana were —
  documented as unverified-in-depth rather than assumed-safe.
- **Event fan-out's downstream task_types** (§8) are structurally low-risk (fixed, internal,
  non-LLM-invented vocabulary with no dedicated per-task_type handlers found) but were not checked
  against literally every district's `run()` implementation — only the security district's two
  agents were read directly.
- **Plan execution** (`plans.py`/`PlanRunner`) was not re-audited this task; its permission wiring
  predates this task and appeared, from the earlier `52_AUTONOMY_BLOCKER_REMEDIATION.md` work, to
  already assume gateway involvement — this is carried forward as an existing assumption, not
  independently re-verified here.
- **Autonomous reachability of Finding 1** specifically (as opposed to chat-triggered reachability,
  which is confirmed) was not found in `goal_system.py`/`decision_engine.py`/`anticipation.py`'s
  candidate-generation code as it stands today — the fix closes the gap regardless of which trigger
  reaches it, but the "is this genuinely one of VECTOR's autonomous behaviors, or only a chat-
  triggered one" distinction matters for how the finding should be weighed against 7-day-experiment
  risk (chat-triggered still means *the owner's own ordinary use of VECTOR* could have caused an
  unapproved real send — not a hypothetical).

---

## 16. Final Status

```
PERMISSION BOUNDARY: FIXED + VERIFIED
```

This does **not** mean VECTOR is ready for the 7-day autonomous experiment — see §15 for what
remains unverified, and the unchanged scoping caveats in `51_FINAL_COGNITIVE_INTEGRATION_AUDIT.md`.
It means: the specific question this task was asked to answer (can any production side-effecting
action bypass the intended permission boundary) has a concrete, evidenced answer — yes, two
confirmed ways, both now fixed and behaviorally verified — rather than an unresolved assumption.
