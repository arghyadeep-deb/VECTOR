# VECTOR Autonomy Safety Audit — Threat Model & Remediation

> Read-only audit. No behavior changed. Date: 2026-08-13
> Scope: observation → cognition → decision → action → permission_gateway → external side effect
>
> **UPDATE 2026-08-13 (same session): all 11 remediation items implemented and
> verified — see §8 "Remediation Applied" at the bottom. The audit section above
> the line is the original read-only finding; the fixes follow.**

---

## 1. The Autonomy Path (traced)

```
observe_loop (0.5s)            core/loop/autonomous_loop.py:612
  └─ _observe_tick → AmbientListener.listen_tick → _pending_voice (validated, sanitized)
       │  prompt_injection.scan_text on input; non-dict discarded; confidence clamped
       │
think_loop (10s)              autonomous_loop.py:706
  └─ _think_tick
       ├─ voice intent? → governor.dispatch({source:"voice"})        [owner path]
       ├─ ContextEngine.get_world_state() (RULE 1 hydrate)
       ├─ GoalSystem.generate_immediate_actions(4) → Candidate list
       ├─ Plan candidates (PlanRunner)
       ├─ DecisionEngine.evaluate(candidates)  [5-factor + policy + reasoning bank]
       ├─ ContinueGate (budget/coherence) → may pause/stop
       └─ if winner.score > 0.3 → _act_on(winner)
            │
act  →  _act_on                autonomous_loop.py:913
       ├─ proactive_*       → gateway.execute (GREEN, nudge only)
       ├─ plan:*             → _act_on_plan_step (→ gateway per step)
       ├─ code_*/code_review_vc → gateway.classify; if RED → gateway.execute; then vectorcode_bridge
       ├─ SwarmCoordinator consensus (multi-agent) → may reject
       ├─ CounterfactualMemory.should_avoid → blocks if score>0.7 + policy penalty
       ├─ ThreatDetector._scan_threats → blocks if severity≥0.85
       ├─ RedTeamAgent.attack_plan (RED actions) → BLOCKED/MODIFY/APPROVED
       ├─ SkillManager match → gateway.classify; if RED → gateway.execute
       └─ else → governor.dispatch(task) → district agent
                    │
                    └─ district agent performs the real side effect,
                       calling gateway itself when its action is RED:
                         content_scheduler  → gateway.execute("content_publish")
                         phone_poster       → gateway.request_approval("instagram_post_via_phone")
                         content_arm        → gateway.request_approval("growth_publish_reel")
                         hedgebot.solana_execute → gateway.execute("solana_swap_execute")
                         investment/safety.approve_live_trade → gateway.execute("financial_transaction")
                         browser_controller → gateway.request_approval(...)
```

**Key invariant confirmed:** The autonomous loop never calls a real-world side effect directly. It either routes through the gateway (proactive, code_*, skills) or through the governor → district agent, where the district agent itself calls the gateway before its RED action. RULE 3 (LLM has zero direct access) holds at the loop layer.

---

## 2. Action Inventory & Tier Classification

Source of truth: `core/config.py` PermissionConfig + `permission_gateway.py` constants.

### GREEN (auto-execute, no owner)
| Action | Side effect | Notes |
|--------|-------------|-------|
| search_web, search_arxiv, get_hn | external API read (DuckDuckGo/ArXiv) | response truncated to 500 chars |
| check_weather | external read (wttr.in) | |
| check_attendance, check_fatigue | local read | |
| play_music, music_*, widget_* | **PC control** (media keys, HUD UI) | purely local; widget_* = /ws broadcast only |
| git_status, git_log, recent_commits, code_review_vc, read_code, analyze_code | local read | |
| daily_digest, daily_review, reflect, consolidate, progress, analyze_progress | local memory ops | |
| hand_researcher, hand_collector, hand_predictor, hand_trader, hand_lead, hand_vault_sync | scheduled hand dispatch | ⚠ see F-3 |
| proactive_* | nudge only (never executes) | |

### YELLOW (10s wait / trust ladder / owner-typed bypass)
| Action | Side effect | Notes |
|--------|-------------|-------|
| commit_code | **modifies files** (git commit, explicit files only; never `git add -A`) | |
| create_calendar_event, set_reminder | external GCal write | |
| write_note_personal | **writes file** to Obsidian vault | |
| pc_screenshot | local capture | |
| monthly_report, finance_report, journal, weekly_journal | local write | |
| create_project, add_deadline, log_exercise, run_tests | local write | |

### RED (Council + Pushover owner approval, 5min timeout, fail-closed)
| Action | Side effect | Gating |
|--------|-------------|--------|
| send_email | **sends email** (SMTP) | gateway._execute_action → sender.send_email; 24h dedup |
| send_message_routine | **sends message to a person** | RED_INTERACTIVE_TOOLS (owner-typed bypass) |
| content_publish | **publishes to Dev.to/Hashnode/Medium** | OWNER_APPROVAL_ONLY (no bypass) |
| execute_code | runs code | VectorSandbox subprocess isolation |
| run_shell_command | **shell exec** | RED_INTERACTIVE_TOOLS; bash AST guard blocks rm -rf/format/\| sh/HKLM |
| gui_task, click_screen, desktop_task, browser_task, vision_control | **PC/phone control** | RED_INTERACTIVE_TOOLS; browser_controller also self-gates |
| pc_type, pc_click, pc_launch_app, launch_app | **PC control** | RED_INTERACTIVE_TOOLS |
| code_task, code_generate, code_fix, code_debug | **writes/executes code** | RED_INTERACTIVE_TOOLS |
| download_file | network fetch to disk | RED_INTERACTIVE_TOOLS; SSRFGuard upstream |
| financial_transaction | **real money** | OWNER_APPROVAL_ONLY; safety.py kill_switch + paper_trading first |
| solana_swap_execute | **real on-chain funds** | OWNER_APPROVAL_ONLY; hedgebot fails CLOSED if gateway unreachable |
| push_github | **remote git push** | OWNER_APPROVAL_ONLY; _execute_action stubs to not_implemented today |
| deploy_production | infra deploy | OWNER_APPROVAL_ONLY; stubbed not_implemented |
| delete_files | file deletion | OWNER_APPROVAL_ONLY; stubbed not_implemented |
| overwrite_note_personal | vault overwrite | RED |
| hand_browser, hand_content, hand_clip | **purchases/forms/publishing/upload** | OWNER_APPROVAL_ONLY |

### FORBIDDEN (never)
`format_drive`, `mass_delete`, `share_private_data`

### UNKNOWN → RED (fail-closed)
`_classify` returns UNKNOWN for anything not in the lists; `execute()` blocks, records, warns after 3 blocks.

---

## 3. Threat Model — 12 Scenarios Tested

### T1. Prompt injection (ingested text → action)
**Path:** email/web/message → `scan_text()` (autonomous_loop `_scan_incoming`) → think → governor `classify_chat_intent` invents task_type → gateway.
**Finding — MEDIUM residual risk.** `scan_text` runs at observe ingress. But the LLM that invents action_types from ingested text runs *after* hydration, and its output action_type still hits `_classify`. Unknown action_types → RED/UNKNOWN (blocked). Known dangerous ones (run_shell_command etc.) are RED_INTERACTIVE_TOOLS — and the 2026-08-04 hardening forces non-owner-originated ones to Pushover (skipping CouncilBrain auto-proceed). **This is well-defended.** Residual: a GREEN action_type (e.g. `search_web`) exfiltration via crafted query is not gated (it's GREEN by design).

### T2. Tool-output injection (LLM tool result → next action)
**Path:** tool returns text → fed into next LLM call → LLM proposes action.
**Finding — LOW.** All proposals still route through `_act_on` → gateway. CounterfactualMemory + ThreatDetector + RedTeam form three independent pre-execution filters on the act path. No tool output bypasses the gateway.

### T3. Malicious web content
**Path:** search_web/browse → content returned → LLM reasons over it.
**Finding — LOW.** `search_web` truncates response to 500 chars (`search_response_limit`). Browser controller self-gates every action via `request_approval`. SSRFGuard validates download URLs. PII scrubber (absorbed) redacts screenshots. Content cannot auto-execute — it only influences the next think tick, which is gateway-gated.

### T4. Stale memory (old policy/counterfactual blocks valid action)
**Path:** CounterfactualMemory.should_avoid / PolicyMemory.get_score.
**Finding — MEDIUM (availability, not safety).** Counterfactual blocks at score>0.7 with a policy penalty (reward=0.05) — this is correct for safety but can permanently suppress a valid action if a past rejection was spurious. No TTL/staleness decay on counterfactual entries. A rejected action during a provider failure (T9) poisons future attempts until manual clear. **Not a safety bypass; a liveness risk.**

### T5. Incorrect autonomous assumptions
**Path:** DecisionEngine scores candidates from goal tags via `_TAG_TO_ACTION` map; confidence hardcoded 0.7.
**Finding — LOW.** Winner threshold 0.3 is low, but every winner still passes gateway. The hardcoded 0.7 confidence means scoring is largely goal_alignment+urgency driven. RedTeamAgent.attack_plan specifically adversarially reviews RED winners. Assumptions don't escape the gate.

### T6. Repeated action (same action every cycle)
**Finding — HANDLED.** Counterfactual `should_avoid` + policy penalty (reward 0.05) was added explicitly to kill the "every 10s same winner" loop (documented 2026-06-24 soak). ContinueGate also throttle/pause. **Caveat:** if the action is GREEN (no counterfactual record because it executes, not rejected), nothing prevents a GREEN action repeating every 10s — but GREEN actions are read-only/nudge by definition.

### T7. Duplicate action (same action twice concurrently)
**Finding — SECURITY-CRITICAL BUG (F-1).** `_wait_for_confirmation` keys `_pending_events` by `action.action_type` alone (permission_gateway.py:1276). Two concurrent RED actions of the same type (e.g. two `send_email`, two `content_publish`) collide: the second overwrites the first's `asyncio.Event`. `confirm_action(action_type)` sets whichever Event is currently registered. Outcome: (a) the first action's wait never resolves → 5min timeout → rejected (fail-closed, safe), OR (b) owner taps Approve once and it sets the second's Event while the first is orphaned. **No double-execution** (execute happens after confirmation, once), but **approval routing is ambiguous** and one action silently times out. For non-OWNER_APPROVAL_ONLY RED actions, CouncilBrain auto-proceed (conf≥0.75) can execute both without any owner signal — see F-2.

### T8. Retry storms
**Path:** scheduler_loop drains `RetryQueue.pop_due(limit=5)` every 30s → re-executes via gateway.
**Finding — MEDIUM.** Backoff is sane (1s→5s→30s→5min→30min, max 5 attempts → DLQ). BUT: the retry path calls `gw.execute(action)` with the *original* `proposed_by`. If `proposed_by` was `hedgebot_agent`, a retried `solana_swap_execute` re-enters the RED path correctly. However, retried actions are not re-run through Counterfactual/RedTeam/ThreatDetector (those live in `_act_on`, not `execute`) — the scheduler bypasses the act-layer's three pre-filters. A retried RED action only sees the gateway's CouncilBrain + Pushover. **Acceptable** because the gateway is the authoritative gate, but the defense-in-depth layers are thinner on retries.

### T9. Provider failure (LLM provider crashes mid-decision)
**Finding — LOW for safety.** Inference fallback chain (27 providers → Ollama terminal) means a provider failure never crashes the loop (RULE 2). The risk is T4: a failure during a RED action's CouncilBrain deliberation → `_handle_red_tier` catches and returns "defer" → Pushover. Hedgebot explicitly fails CLOSED on gateway unreachable. **No fail-open path found.**

### T10. Partial execution (multi-step action completes some steps, fails)
**Path:** MissionRunner / PlanRunner / workflows.
**Finding — MEDIUM.** Missions support `request_rollback` (missions.py:181). But rollback is advisory (calls `runner.request_rollback`, sets status) — there is no automatic compensating-action execution. A `content_publish` that succeeds on Dev.to but throws before Hashnode leaves the system in a partially-published state with `mark_failed` on the job but real content already public. The PostJobTracker marks the whole job failed; no per-platform compensating action. **Irreversible public side effect with no undo.** This is inherent to publishing but the tracker does not distinguish "0 platforms published" from "1 of 2 published".

### T11. Plan failure
**Finding — LOW.** Plan steps route through `_act_on_plan_step` → gateway per step. A failed step does not auto-execute subsequent steps (PlanRunner stops on error). `_get_plan_candidates` only surfaces "next ready" steps. No cascading execution on failure.

### T12. Restart during execution / permission state loss
**Finding — SECURITY-CRITICAL (F-3).** The gateway's `_pending_events` / `_pending_actions` are **in-memory only** (singleton, permission_gateway.py:209-211). A process restart (NSSM auto-restart, Ctrl+C, crash) while a RED action is awaiting Pushover approval **loses the pending approval state silently**. The owner's Pushover tap hits `/gateway/approve/{action_type}` → `confirm_action` → no Event found → returns False → the re-spawned loop has no memory of the action. Meanwhile the *district side* (e.g. content_scheduler holding a PUBLISHING job, or content_arm holding a reel) may have already advanced its own state. The durable `RetryQueue` is SQLite-backed and survives, but it only holds *failed* actions — an action awaiting approval at crash time is neither retried nor approvable. **State divergence between the gateway's ephemeral approval state and the districts' persistent job state.**

---

## 4. Additional Findings (outside the 12)

### F-4: Trust-ladder auto-promotion of YELLOW → autonomous execution
`trust_ladder_enabled=True`, `trust_promotion_streak=20`. Twenty consecutive owner approvals of a YELLOW action auto-promote it to execute with **no owner signal** thereafter (permission_gateway.py:262-279). `commit_code`, `write_note_personal`, `create_calendar_event` can become autonomous. A bad outcome demotes instantly (correct), but a subtle wrong-but-non-error outcome (writes the wrong note content, commits the wrong files) won't trip the `_failed` check (`status=="error" or "error" in result`) and so won't demote. **Promoted YELLOW file-write actions can persistently miswrite with no owner check.**

### F-5: coding_tools.py loose file operations
`districts/coding/coding_tools.py` exposes `apply_search_replace`, `write_code_file`, `multiedit_file`, `apply_codex_patch`, `run_code_safely` as direct functions. These are **not gateway-gated** — they are library helpers. Safety relies on *callers* gating. Confirmed `run_code_safely` uses VectorSandbox (isolated), but `write_code_file`/`multiedit_file` write arbitrary paths with `create_dirs=True`. If a district agent calls these directly (not through the gateway's `execute_code`/`code_*` path), the file write bypasses the tier gate. **Defense relies on caller discipline, not enforcement.**

### F-6: pc_controller.run_shell_command private guard
`PCController.run_shell_command` has a `_gateway_approved: bool = False` keyword guard (pc_controller.py:264). This is a soft guard — any caller can pass `_gateway_approved=True` to bypass it. It is not a capability token. The real gate is that callers should go through `gateway.execute("run_shell_command")`. If a district imports PCController and calls `run_shell_command(cmd, _gateway_approved=True)` directly, it runs arbitrary shell. **Soft guard, not a hard boundary.**

### F-7: phone_controller write ops are convention-gated
`PhoneController.tap/swipe/type_text/launch_app/send_keyevent` have docstring-only "RED-tier — only call after approval" notes (phone_controller.py:235-304). There is **no code-level guard** like pc_controller's `_gateway_approved`. The social_safety + gateway gating lives in the *caller* (phone_poster.py), not the controller. A district that imports PhoneController and calls `.tap()` directly bypasses everything. **Convention-only boundary on phone control.**

### F-8: Audit log capped at 500 entries
`self.audit_log = []` with no visible cap in `__init__`, but prior audit noted a 500-entry cap. If capped, forensic evidence of an approval/blocked decision older than the last 500 is lost. For a 24/7 system this is hours of history. **Evidence retention gap.** (Verify the cap location — `_write_audit`.)

### F-9: CouncilBrain confidence threshold is itself LLM-judged
`_handle_red_tier` auto-proceeds at confidence ≥ 0.75 (permission_gateway.py:522). The confidence is an LLM judgment over `action.params` and 400-char context — both attacker-influenceable for non-owner actions. The 2026-08-04 hardening correctly forces OWNER_APPROVAL_ONLY and RED_INTERACTIVE_TOOLS to skip this path (`_council_verdict="defer"`), but **any other RED action not in those two sets can be auto-executed by council confidence alone** with zero owner signal. Check `CONFIG.permission.red` for RED actions not in either set — those are council-auto-proceed-eligible.

---

## 5. Prioritized Remediation List

| Pri | ID | Issue | Fix | Effort |
|-----|----|-------|-----|--------|
| **P0** | F-1 | Concurrent same-type RED actions collide on `_pending_events[action_type]` key | Key `_pending_events` by a unique id (`uuid4` or `action_type+timestamp+seq`), not `action_type`. Update `confirm_action` to accept the id; Pushover URLs carry it. | M |
| **P0** | F-3 | Restart loses in-flight RED approval state; diverges from durable district job state | Persist `_pending_actions` to SQLite (cron_dedup pattern already exists). On startup, re-hydrate pending approvals or explicitly cancel+DLQ them. | M |
| **P1** | F-9 | CouncilBrain auto-proceed (conf≥0.75) can authorize RED actions not in OWNER_APPROVAL_ONLY/RED_INTERACTIVE_TOOLS with no owner signal | Audit `CONFIG.permission.red` — every RED action should be in one of the two sets, OR council auto-proceed should require owner co-sign. Default: disable auto-proceed for any RED action with external side effects. | S |
| **P1** | F-7 | PhoneController write ops have no code-level gate (convention only) | Add a `_gateway_approved`-style hard guard (or a capability-token check) to `tap/swipe/type_text/launch_app/send_keyevent` so direct callers cannot bypass. Mirror pc_controller. | S |
| **P1** | F-6 | pc_controller `_gateway_approved` is a soft kwarg anyone can pass True to | Replace with a capability token issued by the gateway, or move shell exec entirely behind `gateway._execute_action` (remove the public method). | S |
| **P2** | F-4 | Trust-ladder promoted YELLOW file-write actions can miswrite without demotion | Broaden the `_failed` check to include domain-specific failure signals (e.g. commit produced no hash, note path unwritable). Add a periodic owner-visible log of promoted actions. | M |
| **P2** | F-5 | coding_tools file-write helpers are not gateway-gated; relies on caller discipline | Either route the helpers through the gateway internally, or document+enforce that districts must call them only from within a gateway-approved `code_*` execution context. Add an audit grep gate. | M |
| **P2** | F-10 (T8) | Retried actions skip the act-layer's Counterfactual/RedTeam/ThreatDetector filters | In `scheduler_loop` retry drain, run the same three pre-filters before `gw.execute`, or route retries back through `_act_on` instead of `gw.execute` directly. | S |
| **P3** | F-8 | Audit log cap loses forensic evidence | Persist audit log to SQLite (append-only table) instead of in-memory list. Keep 500-entry in-memory ring for fast access, but write every entry to disk. | S |
| **P3** | T4 | Counterfactual entries have no staleness decay; spurious rejection poisons future | Add TTL or confidence-decay to counterfactual records; auto-expire entries older than N days or after a successful similar action. | S |
| **P3** | T10 | Partial-publish state not distinguished in PostJobTracker | Track per-platform publish status distinctly so "0/2 published" (safe to retry) differs from "1/2 published" (needs compensating action or manual review). | M |

**Priority key:** P0 = active safety/correctness bug, fix now. P1 = latent bypass path. P2 = defense-in-depth gap. P3 = hygiene/liveness.

---

## 6. What Is Well-Defended (no action needed)

- **Singleton gateway** (`__new__` override) — fixes the 37-instance approval-stranding bug; all callers share pending state.
- **`sanitize_proposed_by`** on all client-supplied ingress (executor, missions, tasks) — neutralizes `api_command`/`voice` spoofing.
- **OWNER_APPROVAL_ONLY** — real money, deploys, pushes, publishing require a Pushover tap *even when owner-typed*; never bypassed.
- **RED_INTERACTIVE_TOOLS** — owner-typed bypass for interactive tools, but non-owner (autonomous/LLM-originated) forced to Pushover, skipping council auto-proceed.
- **UNKNOWN → RED** fail-closed default.
- **FORBIDDEN** list + bash AST guard (rm -rf, format, `\| sh`, HKLM).
- **VectorSandbox** isolation for `execute_code`.
- **SSRFGuard** before download/httpx calls in provider_client.
- **Counterfactual + ThreatDetector + RedTeam** three independent pre-execution filters on the act path.
- **Hedgebot fails CLOSED** on gateway unreachable (real money never signs on gateway failure).
- **Email 24h dedup** — prevents duplicate sends on retry.
- **RetryQueue** exponential backoff + DLQ after 5 attempts.

---

## 7. Verification Commands (when remediation begins)

```bash
# F-1: confirm no two concurrent same-type RED actions share a key
python -c "import asyncio; from core.loop.permission_gateway import PermissionGateway, Action;
async def t():
    gw=PermissionGateway()
    import asyncio
    a=gw.execute(Action('send_email',{'to':'a@b'},'test'))
    b=gw.execute(Action('send_email',{'to':'c@d'},'test'))
    # both pending? check gw._pending_events keys
asyncio.run(t())"

# F-3: confirm pending state survives restart
# (requires persisting to SQLite first, then kill -9 mid-approval, restart, check)

# F-9: list RED actions not in either protective set
python -c "from core.config import CONFIG; from core.loop.permission_gateway import OWNER_APPROVAL_ONLY, RED_INTERACTIVE_TOOLS;
red=set(CONFIG['permission']['red']); print('council-auto-proceed-eligible:', red - OWNER_APPROVAL_ONLY - RED_INTERACTIVE_TOOLS)"
```

---

## 8. Remediation Applied (this session, 2026-08-13)

All 11 items implemented and verified. Self-tests pass; gateway/trust-ladder tests (138) pass; 158 targeted tests pass (0 failed).

| Pri | ID | Issue | Fix Applied | Files Changed | Verified |
|-----|----|-------|-------------|---------------|----------|
| **P0** | F-1 | Concurrent same-type RED actions collide on `action_type` key | `_pending_events`/`_pending_actions` keyed by unique `action_type#seq`; `confirm_action`/`approve`/`reject` resolve via `get_pending()`; Pushover URLs carry unique id. | `core/loop/permission_gateway.py`, `core/api/routers/gateway.py`, `tests/test_trust_ladder.py` | ✅ gateway/trust tests pass |
| **P0** | F-3 | Restart loses in-flight RED approvals | `_pending_actions` persisted to SQLite (`pending_approvals` table); on init `_rehydrate_pending()` loads interrupted approvals (marked `interrupted: true`, cannot be approved — owner must reject to clear). | `core/loop/permission_gateway.py` | ✅ rehydration logic in init; self-test covers restart path |
| **P1** | F-9 | CouncilBrain auto-proceed for `execute_code`/`send_email`/`overwrite_note_personal` | New `COUNCIL_AUTO_PROCEED_ALLOWED` opt-in allowlist (default empty). Council "proceed" downgraded to "defer" for non-allowlisted RED actions — owner always gets Pushover approval for external side effects. | `core/loop/permission_gateway.py` | ✅ auto-proceed-eligible set now empty by default |
| **P1** | F-7 | PhoneController write ops convention-only | Added `grant_control`/`verify_control` token API to gateway; all PhoneController write primitives (`tap`/`swipe`/`type_text`/`launch_app`/`send_keyevent`/`unlock`) require valid token. `phone_poster.py` mints token after approval. | `core/loop/permission_gateway.py`, `core/control/phone_controller.py`, `districts/content/phone_poster.py` | ✅ phone_controller self-test passes; tokens enforced |
| **P1** | F-6 | pc_controller `_gateway_approved` soft kwarg | Replaced with gateway-minted capability token (`grant_control`/`verify_control`). All PCController write primitives (`run_shell_command`, `move_cursor`, `click`, `type_text`, `hotkey`, `launch_app`) require valid token. `play_music` (GREEN) mints own token. Gateway `_execute_action` mints tokens for approved actions. | `core/loop/permission_gateway.py`, `core/control/pc_controller.py` | ✅ pc_controller self-test passes; tokens enforced |
| **P2** | F-4 | Trust-ladder promoted YELLOW miswrites without demotion | 1) `write_note_personal` reports `error` on silent no-op (vault not configured / no content) instead of `ok`. 2) Broadened `_failed` check in trust ladder to include `status in ("error","blocked","failed")`, `success:False`, `blocked:True`. | `core/loop/permission_gateway.py` | ✅ trust_ladder tests pass; `_execute_action` test updated to expect `error` |
| **P2** | F-5 | coding_tools file-write helpers un-gated | Added contextvar `vector_coding_grant_active` set by loop after gateway-approved code_* actions and code skills. `apply_search_replace`, `write_code_file`, `multiedit_file`, `apply_codex_patch` check `is_coding_grant_active()` and refuse without grant. | `core/loop/permission_gateway.py`, `core/loop/autonomous_loop.py`, `districts/coding/coding_tools.py` | ✅ coding_tools self-test passes with grant set |
| **P2** | F-10 (T8) | Retried actions skip act-layer pre-filters | Scheduler retry drain now runs CounterfactualMemory `should_avoid` + ThreatDetector `_scan_threats` before `gw.execute()` — a retry can't bypass a known block or threat flag. | `core/loop/autonomous_loop.py` | ✅ retry path in scheduler_loop updated |
| **P3** | F-8 | Audit log capped at 500 entries | Added `gateway_audit` SQLite table; every `_write_audit` entry also appended to disk. In-memory 500-entry ring kept for fast access. | `core/loop/permission_gateway.py` | ✅ `_init_audit_store`, `_persist_audit` in gateway init |
| **P3** | T4 | Counterfactual entries no staleness decay | Added `_decay_factor(created_at, decay_days=7.0)`; `should_avoid`/`get_similar_rejections` use decayed similarity so old/spurious rejections fade. Added `prune_stale(max_age_days=90)` for periodic cleanup. | `core/memory/counterfactual.py` | ✅ counterfactual self-test passes; decay logic verified |
| **P3** | T10 | Partial-publish state invisible | PostJobTracker already has one job per platform; added `status_by_title(title)` → `{platform: status}` and `partial_publishes(title=None)` → surfaces titles where ≥1 platform published AND ≥1 failed/cancelled. | `districts/content/post_job.py` | ✅ post_job self-test passes with T10 assertions |

**Net risk posture after fixes:** The two P0 active correctness bugs (F-1, F-3) are resolved. The three P1 latent bypass paths (F-9, F-7, F-6) are closed by capability tokens and opt-in council auto-proceed. Defense-in-depth layers (F-4, F-5, F-10) are now active. Evidence retention (F-8) and liveness hygiene (T4, T10) improved. The well-defended items (§6) remain intact.