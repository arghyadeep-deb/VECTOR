# T9-fix-1: Governor capability-tier gap (email_agent.py) — CLOSED 2026-09-28

## Finding (Codex external review, T9 round, 2026-09-27; verified real by Claude reading the code)

`core/city/governor.py`'s `_is_known_task_type()` treats ANY agent-declared capability string as
"known" — its only job is to distinguish "known, let dispatch proceed untiered" from "unknown, refuse"
for names with no entry in `core/config.py`'s GREEN/YELLOW/RED lists. It does not itself apply a tier.

`districts/communications/email_agent.py` declares `discard_draft`, `mark_read` and `move` as real
capabilities (see its `run()` task_type branches, ~line 505-532). None of the three had a
`core/config.py` tier entry, so `Governor.dispatch({"type": "move", "district": "communications", ...})`
reached `EmailAgent.move_email()` with **zero PermissionGateway involvement** — not even a GREEN
classification. This is the same class of gap the 2026-09-25 Governor district-trust fix
(`c276264cf`) closed for a curated "risk word" list, but that fix did not cover every one of the ~715
real agent-declared capability strings, and these three were not covered.

## Fix applied (option (b) from the finding — explicit, scoped tiering)

Rather than making `_is_known_task_type()` fail closed on every untiered declared capability globally
(option (a) in the finding), which would require auditing all ~715 agent-declared capability strings
system-wide to avoid breaking legitimate but-still-untiered functionality elsewhere — explicitly out of
scope for this task — three real tier entries were added to `core/config.py`, scoped to exactly the
gap found plus the same class found in the same file:

| Capability | Tier | Why |
|---|---|---|
| `mark_read` | GREEN | Flips a read/unread flag on an email already in the owner's own local store. No send, no delete, no external effect. |
| `discard_draft` | YELLOW | Deletes a locally-stored draft — real local mailbox-state mutation, no external send. |
| `move` | YELLOW | Moves an email between folders — real local mailbox-state mutation, no external send. |

Both new entries are flagged in `core/config.py`'s own comments and in this report for the pending
independent (Codex) review, per `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_AGENT_SPEC.md`'s guardrail: never
silently add or loosen a tier.

## Other email_agent.py capabilities audited the same way (per the finding's own scope: "just these 3
plus any other email_agent.py action types found the same way")

`list`, `get`, `thread`, `poll_inbox`, `store_incoming`, `reply`, `send_reply`, `forward`,
`user_interaction`, `communications` were also classified UNKNOWN before this fix. None of them are the
same class of gap:

- `list`/`get`/`thread`: pure local SQLite reads (`list_emails`/`get_email`/`get_thread`) — no mutation,
  no external effect.
- `poll_inbox`/`store_incoming`: real IMAP fetch + local store write, but this is *receiving* mail
  (comparable to the already-GREEN `new_email` webhook path) — no owner-initiated mutation and no send.
- `reply`/`send_reply`/`forward`: already internally re-gated at the real risk point — each branch calls
  `PermissionGateway().execute(Action(action_type="send_email", ...))` (RED tier) *before* the actual
  SMTP send (fixed earlier, `53_PERMISSION_BOUNDARY_INTEGRITY.md` Finding 1). The outer task_type
  identity being untiered does not bypass anything, because the actual dangerous operation is gated
  inside the handler regardless of the outer tier.
- `user_interaction`/`communications`: never matched as a literal `task_type` in `run()`'s branch chain
  at all — dispatching either falls through to the harmless read-only status branch (`else:` — returns
  unread/total counts). Descriptive capability labels for A2A discovery, not real dispatchable actions.

None of these were tiered by this fix — doing so was unnecessary (they involve no real, ungated
mutation) and out of scope. Left untouched, consistent with "do not do a full audit of all 715 in this
task."

## Why not option (a) (fail-closed globally)

Implementing `_is_known_task_type()` to require a real tier for every agent-declared capability
system-wide would immediately need every one of the other ~700+ agent-declared-but-untiered capability
strings across the whole manifest to already have a correct tier, or every one of them would newly
break (Governor would refuse dispatch for legitimate, currently-working functionality it has never
audited). That is explicitly a separate, larger task per the finding's own text ("a broader audit is a
separate task if needed") and was not attempted here.

## Verification

- New regression test: `tests/test_t9_fix1_email_agent_capability_tiers.py` (9 tests) — proves
  `discard_draft`/`move` are now classified YELLOW and refused without a real `PermissionGateway`
  approval receipt, dispatch with one, never reach the agent when refused, and `mark_read` is GREEN and
  dispatches without needing a receipt (GREEN is itself the approval).
- `python -m pytest tests/test_t9_fix1_email_agent_capability_tiers.py -v` — 9 passed.
- Ran alongside the existing Governor/permission regression suite
  (`test_governor_unknown_task_gate.py`, `test_regression_governor_capability_routing.py`,
  `test_regression_governor_dispatch_authorization_boundary.py`, `tests/unit/test_governor.py`) — no
  regressions.

## Status

T9-fix-1 CLOSED. T9-fix-2 (web_extract DNS rebinding), T9-fix-3 (signature cache key) and T9-fix-4 (SSL
context cache staleness) were already closed by commit `4ad8d439a` ("fix: close external security
review findings", landed via Codex 2026-09-28 while Claude's weekly quota was exhausted) — verified by
reading that commit's actual diff, not assumed from the backlog's stale `pending` status. All four T9
findings are now closed; the whole-diff T9 review itself (`45bed5d89..HEAD`) still needs a final Codex
re-run to confirm closure independently.
