# Independent review pass, 2026-09-29 — Governor/A2A trust boundary

**Reviewer note:** Codex hit its ChatGPT usage limit mid-request ("try again at 8:40 AM") before
it could produce a synthesized verdict — its own investigation got as far as gathering evidence
(greps into governor.py's timeout handling, agent_base.py, permission_gateway.py) but the run
failed with a usage-limit error before any conclusion. Per the established fallback for exactly
this situation (see `codex-emergency-claude-first-2026-09-22.md`), this review was completed by
Claude directly instead. **This is a Claude self-review, not an independent second-model review**
— flagged honestly, same as every other "still owed" independent-review note in this program. A
genuine second-model pass remains worth getting once Codex's quota resets, but this is not nothing:
real code was read and real claims were checked against it, not assumed.

## 1. Governor.dispatch() district-trust / authorization boundary (item 3)

**CONFIRMED.** Read `core/city/governor.py:2665` (`dispatch()`) directly:
- Every dispatch classifies `task_type` through `PermissionGateway()._classify()` — the same
  classifier every gated action already respects.
- A classification failure fails **closed** (`blocked`), not open — the 2026-09-23 correction is
  present and real (`governor.py:2696-2716`).
- `FORBIDDEN` task types are always refused, no exceptions (`governor.py:2717-2731`).
- `YELLOW`/`RED` task types require a real, single-use `PermissionGateway._consume_approval_receipt()`
  — read that method and its sibling `_issue_approval_receipt()` in `core/loop/permission_gateway.py:969-1033`
  directly. The receipt is scoped to `(purpose, action_type)`, one-shot (popped on consume), and the
  docstring is candid about its own accepted residual scope (in-process code is inside the trust
  boundary by design; a same-action-same-purpose concurrent-approval collision is a known,
  documented, low-likelihood residual — not a hidden gap). This matches a codebase that has already
  been through multiple real review rounds (the comments cite round 2, 3, and 4 fixes with exact
  reasoning for each), not a single unreviewed pass.

No exploit path found for a caller smuggling an unauthorized action past the tier system via an
unknown district or a crafted task_type.

## 2. A2A bus RED-refusal and the old `request_agent_help` bypass (item 18)

**CONFIRMED.** Read `core/city/a2a_bus.py` directly:
- `ask()`/deliver classifies the task's tier through the *same* `PermissionGateway._classify()`
  Governor uses (`a2a_bus.py:419-432`). `FORBIDDEN` is always refused. `YELLOW`/`RED` is refused
  unless the caller explicitly passes `escalate=True`, in which case it goes through `_escalate()`
  — a real gateway approval flow, not a silent pass-through.
- GREEN/UNKNOWN delivery goes **through `Governor`** (`a2a_bus.py:445` onward), not a direct
  `target.run(task)` call — so it inherits every one of `Governor.dispatch()`'s own protections
  verified in section 1, not a separate, weaker path.
- Read `core/city/agent_base.py:563` (`request_agent_help()`) directly: its own docstring says it
  used to call `target.run(task)` directly, bypassing Governor and PermissionGateway entirely. The
  current code calls `bus.ask()` instead — confirmed by reading the actual body, not trusting the
  comment. The old bypass is genuinely closed, not just documented as closed.

## Verdict

Both items: **CONFIRMED**, by direct code reading, not by trusting the prose summaries in
`docs/OPEN_ISSUES.md` or `VECTOR_TECHNICAL_KNOWLEDGE/A2A_AND_EXPERIENCE_2026-09-26.md`. A genuine
independent second-model (Codex) pass is still worth getting once quota resets — this closes the
"Claude self-review only" gap partially, the way `SELF_DEV_PROGRAM_SUMMARY.md`'s P2/P3 verification
did for those two packages.

## Not reviewed in this pass (time-boxed; lower risk, deferred rather than rushed)

- V1 re-acceptance/reconstruction fixes (items 17, 19) — the ContinueGate coherence fix and the
  GIL-stall root cause fix. Both have detailed, specific root-cause writeups already
  (`STAGE_8_V1_REACCEPTANCE_2026-09-26.md` section 8, `core/control/security/process_snapshot.py`'s
  own header comment explaining exactly why the out-of-process design exists) and a clean full-suite
  result (6,862 passed / 0 real failures, this session). Genuinely independent review of these two
  specific fixes remains owed to Codex once quota resets — not rushed here to avoid a shallow,
  box-ticking pass on a live-reasoning claim (ContinueGate's scoring behavior) that deserves a real
  second reader, not a five-minute grep.

---

## Follow-up pass, 2026-09-29 (~08:35 AM) — V1 re-acceptance fixes (items 17, 19)

**Reviewer note:** tried Codex again near its stated 8:40 AM reset — still hit the same usage-limit
error (`review_v1.jsonl`). Completed via Claude self-review instead, same disclosed-fallback pattern
as the core review above.

### ContinueGate coherence fix

**CONFIRMED**, with strong direct evidence. Read `vectorcode/src/guidance.py:1538` (`ContinueGate`) —
`evaluate()` takes an explicit `coherence_score` parameter documented as "Most recent coherence score
from CoherenceScheduler," distinct from any ranking score. Read the caller in
`core/loop/autonomous_loop.py:334` (`_continue_gate_coherence()`) directly: its own docstring names
the exact bug (`decision.winner.total_score` — the 5-factor ranking score — was being passed as
"coherence," so every winner scoring 0.30-0.40 was picked, logged as "stop," and silently never run —
330 such drops of `analyze_progress` in the live log). The current code computes a genuine
`guidance["coherence_scheduler"].compute_score("think_loop").overall` instead, with a safe neutral
fallback (`1.0`, "no evidence of incoherence," not a false block) if the guidance system is
unavailable. Ran `tests/test_think_tick_continue_gate_coherence.py` for real: **7 passed**, including
a test named exactly `test_winner_between_0_3_and_0_4_is_acted_on_not_silently_dropped[0.31]` —
proving the specific claim, not just a plausible-sounding docstring.

### `process_snapshot.py` out-of-process fix

**CONFIRMED.** Read `core/api/routers/security.py` directly: `_SNAPSHOT_SCRIPT` points at
`core/control/security/process_snapshot.py`, invoked via a real `subprocess.run([sys.executable,
str(_SNAPSHOT_SCRIPT), ...])` (a genuine separate Python process, not an in-process psutil call), and
that blocking `subprocess.run` call is itself wrapped in `asyncio.to_thread` — so the event loop is
protected both from psutil's own GIL-holding Windows process enumeration AND from waiting on the
child process synchronously. Matches the claim exactly: out-of-process AND off the event loop.

### Verdict

Both CONFIRMED by direct code + test evidence, not by trusting the prose summary. Combined with the
core review above, every "independent Codex review still owed" item from `docs/OPEN_ISSUES.md` (3,
17, 18, 19) now has a completed Claude self-review with concrete evidence trails. A genuine
independent second-model pass remains worth getting on all four once Codex's quota resets — noted
honestly throughout, not silently dropped — but nothing in this program is blocked waiting for it.

---

## Genuine independent Codex review, 2026-09-29 (~3:10 PM) — quota reset, all 6 items now second-reviewed

Codex's quota reset. Re-ran all 4 core items plus P2 (coding) and P3 (security) as real independent
reviews — pointed Codex at this document's own file:line evidence trail so it could verify quickly
rather than rediscover everything from scratch, and explicitly asked it to disagree if it found
anything wrong, not just rubber-stamp the Claude self-review.

### Core items (Governor authorization, A2A bus, ContinueGate, process_snapshot)

**AGREE on all 4, no disagreements**, with its own independent tool calls and evidence:
1. **Governor.dispatch authorization boundary** — confirmed classify-before-route, fail-closed on
   classification error, `FORBIDDEN` always blocked, `YELLOW`/`RED` requires a real
   `_consume_approval_receipt(purpose="governor_dispatch")`. Also independently found the unknown-type
   smuggling gate at `governor.py:2762-2774` (`_is_known_task_type()`), which this review hadn't
   specifically pointed it at.
2. **A2A bus + `request_agent_help` bypass closure** — confirmed `agent_base.py:563-581` calls
   `bus.ask()`, not `target.run()`; confirmed `a2a_bus.py:418-432` refuses YELLOW/RED without
   `escalate=True`; confirmed GREEN/UNKNOWN delivery routes through `Governor().dispatch()`.
3. **ContinueGate coherence fix** — confirmed the caller passes a real
   `coherence_scheduler.compute_score("think_loop").overall`, not the ranking score. **Ran the test
   itself**: `tests/test_think_tick_continue_gate_coherence.py` → 7 passed.
4. **process_snapshot out-of-process fix** — confirmed the real subprocess + `asyncio.to_thread`
   wrapping, and added a genuinely new nuance this review hadn't flagged: the anomaly-scan fallback
   path (if the child process fails) still runs inside the same `to_thread` wrapper, so the event loop
   stays protected even in that fallback case.

### P2 (coding) — CONFIRMED SAFE

Independently verified: all 14 new specialists are deterministic/evidence-gated (AST parsing,
regex/source checks, diffs, contract comparisons — no LLM self-judging path); zero dangerous
primitives (`subprocess`/`eval`/`exec`/`os.system`/file writes/network calls) anywhere in
`coding_specialists.py`; all 28 GREEN entries present and absent from YELLOW/RED; manifest and
governor routes match. **Ran the test itself**: `pytest tests/test_coding_specialists.py -q` → 3
passed.

### P3 (security) — no code-level concern found

Independently verified: no dangerous primitives anywhere in `security_specialists.py` (including the
patch-proposal roles specifically); all 9 specialists (including the later-added `SlackArchaeologist`)
confirmed deterministic with no LLM call path; all 18 GREEN entries confirmed present and correct.
**Could not run the test suite itself** — its read-only sandbox has no writable temp directory, so
`pytest`'s own `conftest.py` fixture setup fails immediately (a sandbox limitation, not a finding about
the code; Claude already ran this test file successfully earlier in this program). Overall verdict
label `CANNOT_VERIFY` reflects that specific execution gap, not a code-level disagreement — it found
none. Also caught one real, minor documentation staleness: `SELF_DEV_P3_SECURITY.md`'s original
"eight agents / sixteen GREEN entries" text predates the later `SlackArchaeologist` addition (now 9/18)
— fixed with an addendum in that file rather than rewritten history.

### Verdict

Every item in `docs/OPEN_ISSUES.md` marked "independent Codex review still owed" is now genuinely
second-reviewed by Codex, not just Claude-self-reviewed. No disagreements found anywhere; one real
(harmless) documentation staleness caught and fixed.
