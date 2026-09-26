# Codex independent-review packet (prepared 2026-09-27, review NOT run: Codex quota returns 2026-09-27 19:11)

Branch `fix/external-review-2026-09`, nothing pushed. Review base: **`45bed5d89`** (`production-hardening-complete`, the last commit Codex
reviewed: "close Governor.dispatch() authorization-boundary gaps"). Range `45bed5d89..HEAD` is 131+ commits; this packet lists what carries
risk so the review can be scoped instead of reading everything. Everything below was written by Claude (Codex was unavailable), so none
of it has had an independent pair of eyes. Suggested command: `git diff 45bed5d89..HEAD -- <paths below>`.

## 1. Authorization boundary (highest risk, review first)

| Change | Where | What to check |
|---|---|---|
| Permission tiers applied with owner approval (2026-09-25): 17 RED, 52 YELLOW, 64 GREEN + 19 agent-declared names; unknown task types refused by the Governor whatever `district` the caller names | `core/config.py`, `core/city/governor.py`, `tests/test_governor_unknown_task_gate.py`, frozen guard `tests/test_v1_trust_t3_permission_vocabulary.py` | any GREEN entry whose handler writes, spends, sends or reaches out; the "risk word" filter change (destructive verbs always elevated) |
| **New GREEN tier entry: `web_extract`** (read-only http/https GET, SSRF-guarded per redirect hop, size/time limited, page text injection-scanned) and new member of `_PLAN_COMPOSABLE_ACTION_TYPES` | `core/browser/page_extract.py`, `districts/research/web_scout.py`, `core/config.py`, `core/loop/permission_gateway.py` | SSRF (private ranges, redirects, DNS rebinding), response size caps, that "GREEN" is honest |
| Governor pinned-agent branch and `_no_reward` (A2A) | `core/city/governor.py` (`_a2a_pinned_agent`, `_pick_capable`, `_record_experience`, `_account_failure`) | a pinned agent must still pass the tier gate, the unknown-type gate and the timeout; `_no_reward` must not skip a gate, only HP/ledger |
| **A2A bus** (governed agent-to-agent requests for all 230 agents; RED/YELLOW answered `requires_approval` unless `escalate=True`, then an ordinary PermissionGateway proposal from proposer `a2a_agent`) | `core/city/a2a_bus.py`, `core/api/routers/a2a.py` (`/a2a/internal/*`, POST `/ask`), `core/city/agent_base.py` (`a2a_*`, `request_agent_help` now routed via the bus) | authority inheritance (asking a peer must not make an action easier), depth/cycle/rate/payload caps, injection screen, the `/ask` endpoint's auth, the closed `request_agent_help` bypass |
| /command, /ws/command reported failed handler results as done | `core/api/routers/commands.py`, `core/api/routers/websocket.py`, `core/runtime/executor.py` (`result_failure_reason`) | truthful reporting; no path that turns `no_agents` / `error` payloads back into success |
| Permission-boundary audits (2026-09-23/25): pc_* actions via the gateway, home_control gated, owner refresh rejects collection tokens | `core/loop/permission_gateway.py`, `core/collections/auth.py`, `tests/test_jwt_live_server_smoke.py` (7 live-server checks) | token scope separation |

## 2. Behaviour that changes what VECTOR does on its own

| Change | Where | Note |
|---|---|---|
| **Fair cull default ON** (`VECTOR_FAIR_CULL`): the nightly cull needs HP<200 AND >=3 own-fault failures; replay showed 98% of 573 deaths were healthy agents | `core/city/evolution_engine.py` | reverses the previous "kill the lowest-ranked" behaviour |
| Flags default OFF: `VECTOR_HP_FAIR`, `VECTOR_PLAYBOOK`, `VECTOR_LEVEL_COUNCIL`, `VECTOR_EXPLORE`, `VECTOR_GYM` | `core/city/experience.py`, `core/city/agent_base.py` (probation, model-tier floor), `core/security/hp_validator.py` (penalties unsmoothed under the flag) | HP validator EMA was one state shared by rewards and penalties |
| Experience ledger (always records), work board / drills / collaboration credit | `core/city/experience.py`, `core/city/work_board.py` | verified-only credit; gym moves no HP |
| **Plan-step aging** (a ready plan step that loses a decision gains +0.1 confidence and urgency per lost tick, cap 1.0) | `core/loop/autonomous_loop.py` (`_get_plan_candidates`, `_age_plan_candidates`) | fixes plans starving behind ambient goal candidates; check it cannot make a RED/YELLOW step spam approvals (a step leaves `planned` once attempted) |
| ContinueGate coherence fix (was fed the ranking score) | `core/loop/autonomous_loop.py` | 330+ silently dropped winners before |
| Shared outcome assessment (`assess_payload_failure`, `result_field`/`all_of` verification, no LLM replan for content-verified steps) | `core/runtime/executor.py`, `core/runtime/plans.py` | conservative: only explicit failure signals |
| Free-tier rule: the legacy OpenRouter tier only calls `:free` models | `core/inference/vectorcode_llm.py` | it previously mapped to paid Claude/DeepSeek models; only an empty account (HTTP 402) prevented charges |

## 3. Newly spawning processes (2026-09-27)

`core/api/routers/security.py` and `core/control/security/threat_detector.py` now run the process scans in a child process
(`sys.executable core/control/security/process_snapshot.py table|anomalies`). Arguments are constants (no user input); the child is
started with `CREATE_NO_WINDOW`, a timeout, `check=True`, and falls back in-process on failure. Reason: psutil on Windows holds the GIL
for ~10 s per sweep (py-spy), which froze the API 15-27 s every ~30 s. Please check the spawn for injection or path-hijack risk.

## 4. Evidence

* Full suite on `43ef7e5e2`: 6,586 passed / 3 failed / 55 skipped (the 3 HUD dev-mode e2e failures pass alone; load-sensitive).
* Live: 230/230 agents answered an A2A ping across 39 districts; RED `delete_files`/`send_email` requests came back `requires_approval`.
* Live after the stall fix: `/agents` max latency 19-27 s -> 1.99 s over 90 samples; `/security/status` max 6 s -> 0.2 s.
* Strict Stage 4 (`tests/test_stage4_real_goalsystem_competition.py`): real GoalSystem + a real git failure; found and fixed the starvation.

## 5. Not covered / known limits (do not read these as reviewed)

* `districts/emergency`, `districts/security/incident_playbook_runner.py`, `core/resilience/*` still call `subprocess.run` inline in async
  code (rare RED-tier paths, left alone).
* Goal-less plans (`goal_id == ""`) still lose to ambient goal candidates by design (neutral 0.3 alignment); production plans are goal-linked.
* Only GitBot has a practice drill (1 of 230 agents).
