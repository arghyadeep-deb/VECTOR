# Repo-Maintenance Dev Loop — Design
> 2026-07-07, Fable 5. Task P3.4. DESIGN ONLY — do NOT auto-start without owner
> sign-off (it takes autonomous repo actions).

## Goal (owner's spec, verbatim intent)
While repo maintenance is active: wake every ~5 min, triage repos, read each
repo thread's latest state, reuse ONE thread per repo, assign its highest-value
BOUNDED task within granted permissions, DON'T interrupt coherent active work.
Require tests + live proof + autoreview + green CI before anything lands.
Escalate product/access/security/irreversible decisions. Record meaningful
changes. STOP when every item is landed, decision-ready, blocked, or no-work-left.

## How it maps to EXISTING VECTOR machinery (reuse, don't rebuild)
| Need | Existing piece |
|---|---|
| Wake every 5 min | `/loop` skill (dynamic pacing) or CronCreate; ScheduleWakeup 270s to stay cache-warm, or 300s+ if idle |
| Autonomous act→verify→reflect | `core/loop/autonomous_loop.py` |
| Permission gating | `core/loop/permission_gateway.py` (GREEN/YELLOW/RED) |
| Earned autonomy | `core/loop/trust_ladder.py` |
| One thread per repo | Agent/SendMessage thread reuse (persist thread id per repo) |
| CI gate | `.github/workflows/ci.yml` (pytest enforced) |
| Autoreview | `/code-review` skill / addy/obra reviewers |
| Escalation | permission_gateway RED → Pushover to owner |

## The loop (state machine)
```
STATE: repo_maintenance_active (owner-toggled flag)
every 5 min (while active):
  1. TRIAGE: list target repos; for each, read latest thread state
     (open PRs, failing CI, TODO/FIXME hotspots, stale branches, issues).
  2. GUARD: if a repo has coherent ACTIVE work (recent commits in a live
     session, WIP PR being iterated) → SKIP it this tick (don't interrupt).
  3. SELECT: per idle repo, pick the single highest-value BOUNDED task that
     fits within granted permissions (bounded = completable this tick with a
     clear done-condition). Reuse the repo's one thread.
  4. EXECUTE via the thread, within permission tiers. GREEN auto; YELLOW/RED per
     gateway. NEVER exceed granted scope.
  5. LAND-GATE (all must pass before merge/land):
     - tests written + passing
     - live proof (the change actually works, not just compiles)
     - autoreview passed (/code-review, filter <80 confidence)
     - green CI
     If any fails → do not land; leave decision-ready or fix within scope.
  6. ESCALATE (to owner via Pushover/RED) for: product decisions, access/perms,
     security, anything irreversible (force-push, deploy, delete, spend).
  7. RECORD: meaningful changes → memory + commit (per commit convention;
     NO Co-Authored-By).
  8. STOP CONDITION: exit the loop when EVERY item across repos is one of:
     landed | decision-ready (awaiting owner) | blocked | no-work-left.
```

## Safety invariants (non-negotiable)
- Never land without the full LAND-GATE (tests + live proof + autoreview + CI).
- Never take an irreversible/outward action autonomously — escalate.
- Never interrupt coherent active work (the GUARD step).
- Respect the permission gateway; high-blast-radius actions (shell, deploy)
  stay RED (see plans/harness/06-trust-boundary.md denylist recommendation).
- Bounded tasks only — no open-ended refactors autonomously.

## Pacing (from the /loop + ScheduleWakeup guidance)
- Active triage with external state to watch: 270s (stay in prompt-cache TTL).
- Idle / nothing to do: 1200-1800s heartbeat (don't burn cache 12×/hr).
- Don't pick 300s (worst-of-both: cache miss without amortizing).

## Implementation sketch (when owner approves)
1. Add a `repo_maintenance_active` flag (config/env).
2. A driver skill `/repo-maintain` or a CronCreate autonomous loop that runs the
   state machine above, one Agent thread per repo (SendMessage to continue).
3. Wire LAND-GATE to CI status API + /code-review + the test runner.
4. Wire ESCALATE to permission_gateway RED → Pushover.
5. Dry-run first (report-only mode: triage + select + explain, NO landing) for
   several cycles; owner reviews; then enable landing for GREEN-tier tasks only;
   expand via trust ladder.

## Do NOT
- Auto-start this. It takes autonomous repo actions across sessions. Owner must
  explicitly enable it, ideally after a dry-run period.

## Provenance
2026-07-07. Ties to `core/loop/autonomous_loop.py`, `permission_gateway.py`,
`trust_ladder.py`, `.github/workflows/ci.yml`, `/loop` + `/code-review` skills.
