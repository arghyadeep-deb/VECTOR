# M1c-4 — Development Verification Hazard Inventory + Consequential Side-Effect Surface

Read-only, static analysis only. Nothing was executed, imported, or run for this audit — every
claim below is sourced from `git log`/`grep`/direct file reads, or from prior sessions' own
already-committed, already-disclosed reports (cited by file:line), never from re-running anything.

## Part 1 — Development verification command inventory

Searched `git log -n 300` commit bodies and every `VECTOR_TECHNICAL_KNOWLEDGE/*.md` report for
bare `python <module>.py` invocations used as "verification."

| Command pattern | Source citation | Touches persistent/real state? | Reasoning |
|---|---|---|---|
| `python core/brain/goal_system.py` | R11 report §10 (first incident); `COGNITIVE_EVOLUTION_ORCHESTRATOR.md` M1/M1b (this session, second incident) | **YES — confirmed twice, real incidents** | `__main__` (pre-M1b-fix) constructed a bare `GoalSystem()` against whatever `configured_db_path()` resolved to with no isolation; called real mutating methods. **Currently fixed on disk (uncommitted, part of M1b) via an unconditional `VECTOR_DB_PATH` override + hard `assert` before construction — but that fix has not yet been reviewed/approved per the current STOP order.** |
| `python core/memory/policy.py` | R12-H audit Finding 4 (`VECTOR_TECHNICAL_KNOWLEDGE/r12_audits/R12-H_persistence_audit.md:52`); confirmed directly in this audit (`core/memory/policy.py:265-313`) | YES, but low-severity | `pm = PolicyMemory()` bare, real DB, no isolation guard of any kind (not even a broken one) — but every write uses a `uuid.uuid4()`-suffixed key (`smoke_web_test`/`smoke_veto_test_{run_id}`), so it can never collide with or corrupt real owner data. Still an unauthorized real-DB write in principle. **Not fixed.** |
| `python core/memory/episodic.py` | R12-H audit Finding 8 (`R12-H_persistence_audit.md:78-80`); confirmed directly in this audit (`core/memory/episodic.py:1440-1455`) | **YES — meaningful, not just throwaway** | `mem = EpisodicMemory()` bare, zero isolation guard (not even an attempted one). Writes throwaway `'test'`/`'task'` episodic rows AND **unconditionally overwrites the real `semantic_memory` row keyed `owner_name`** with the literal string `'Arghyadeep'` (`episodic.py:1447`) on every run. Currently harmless only because that value happens to already be correct — this is a real, unconditional overwrite of real semantic memory, not a throwaway key. **Not fixed. Arguably the single most dangerous individual `__main__` block found in this audit**, since running it "just to sanity check the file imports" silently commits a real write with no announcement. |
| `python core/runtime/plans.py` | `52_AUTONOMY_BLOCKER_REMEDIATION.md:288-294` (previously run directly as verification for the plan-recovery-hook milestone); confirmed directly in this audit (`core/runtime/plans.py:969-1061`) | **NO — genuinely safe** | Every persistence-touching test inside this `__main__` block explicitly constructs `PlanStore(path=tmppath)` with `tempfile.NamedTemporaryFile`, never touches `get_plan_store()`'s real default singleton (`data_path("plans","plans.json")`). Filesystem JSON, not the SQLite singleton, so it isn't even exposed to the `VECTOR_DB_PATH`/dotenv hazard class. **This is the one file in this inventory that already does isolation correctly**, and is directly relevant to the paused R17 milestone (which will touch this exact module) — the module's own self-test convention is not the risk; a deliberate R17 mutation against the real store would be a separate, intentional action, not an accidental one. |
| `python core/brain/epistemic_tracker.py` | Confirmed directly in this audit (`core/brain/epistemic_tracker.py:244-253`) | NO | `et = EpistemicTracker(db_path=db)` with an explicit `tempfile.NamedTemporaryFile` path — correctly isolated via this module's own (non-`VECTOR_DB_PATH`) constructor-parameter convention. |
| `python core/memory/counterfactual.py` | Confirmed directly in this audit (`core/memory/counterfactual.py:391-396`) | NO | Same pattern — `cf = CounterfactualMemory(db_path)` with an explicit temp path. Correctly isolated. |
| `python districts/karpathy_lab/autoresearch_runner.py` | `58D_KARPATHY_AUTORESEARCH_PERMISSION_REMEDIATION.md:270-279` — **this one WAS actually run directly by a prior session**, not merely read | **Real external side effect, but the safety gate held** | Running this module directly (as a real, deliberate verification step for the 58D permission-remediation task, not an accident) exercised the real `PermissionGateway`/`CouncilBrain`/Pushover-confirmation chain end-to-end. It correctly returned `{"status": "blocked", ...}` with zero subprocess execution and zero file writes — **but it did send a real Pushover push notification to the owner's phone**, since that's how the approval-request step works. Not a safety failure (the RED gate did its job), but a genuine "running this for verification has a real-world side effect the runner might not expect" finding, distinct from the DB-mutation class. |
| `python core/mcp_server.py` (no args, or with `--transport sse --port 9000`) | `60_FINAL_PRE_EXPERIMENT_AUTONOMOUS_SIDE_EFFECT_RED_TEAM.md` §2 row for `core/mcp_server.py`, §9.1; confirmed directly in this audit (`core/mcp_server.py:223-229`) | **YES — the most severe entry in this table if actually served and connected to** | Not run in this audit (per the no-execution rule) or, per Task 60's own record, ever exercised end-to-end with a real client — but Task 60's own S3-level source trace already established this file's docstring literally instructs `python core/mcp_server.py --transport sse --port 9000` as its real entry point, exposing 14+ tools **including `db_quarantine`, email deletion, and browser actions with no `PermissionGateway` enforcement and a fail-open security wrapper**. Task 60 classified this "Class A (user-only)" and out of the *autonomous-loop* experiment's scope (since nothing in `autonomous_loop`/`Governor`/the scheduler starts it) — but it remains fully reachable by any developer (or future orchestrator agent) who runs this exact "let me just check the MCP server starts" command. |

**Cross-cutting Part 1 finding:** `89D_POLICY_REWARD_IDENTITY.md:293-304` documents a THIRD, entirely
different hazard class for this same "bare `python <file>.py`" pattern, orthogonal to persistent-
state mutation: running a module as a relative-path script can, on this machine, resolve
`import core.*` against a **different installed/editable copy of the codebase** than the current
worktree (because `sys.path[0]` becomes the script's own directory, which has no `core/` package,
so resolution falls through to whatever alternate root is registered elsewhere on `sys.path`) —
producing misleading verification results that silently test the wrong code entirely. That report's
own conclusion: "Always verify via `pytest` from the worktree root, not via a bare
`python <relative/path>.py` invocation, when multiple checkouts of this codebase may exist on the
machine." This is a second, independent reason (beyond DB isolation) that the entire "run a
module's `__main__` directly to sanity-check a fix" pattern is unreliable in this repo's actual
development environment — not merely a data-safety issue but a correctness-of-verification issue.

## Part 2 — Consequential side-effect surface in dev/test-reachable paths

Scoped strictly to code reachable from a `__main__` self-test, a `tests/` file, or a documented
"smoke test" / "verification" script — not the general production surface (which is expected to
have these capabilities under `Governor`/`PermissionGateway` control).

| File:line | Side-effect type | Gated? | Gating mechanism |
|---|---|---|---|
| `core/memory/episodic.py:1447` | Real DB write (semantic_memory overwrite) | No | None — unconditional |
| `core/memory/policy.py:269-293` | Real DB write (throwaway-keyed) | Partial | Unique-key convention only, not an isolation boundary |
| `core/brain/goal_system.py` `__main__` (pre-M1b-fix state, now fixed on disk but uncommitted) | Real DB write (goal store mutation) | Now Yes (uncommitted) | Unconditional `VECTOR_DB_PATH` override + hard assert, per M1b |
| `core/runtime/plans.py` `__main__` | Filesystem write | Yes | Explicit `tempfile`/`PlanStore(path=...)` |
| `core/brain/epistemic_tracker.py` `__main__` | Real DB write, avoided | Yes | Explicit `db_path=` temp file |
| `core/memory/counterfactual.py` `__main__` | Real DB write, avoided | Yes | Explicit `db_path=` temp file |
| `districts/karpathy_lab/autoresearch_runner.py::run_experiment_cycle` (real-run per 58D report) | Real subprocess (training) + real git branch + real Pushover push notification | Yes for the dangerous part | `PermissionGateway`/`CouncilBrain`/Pushover-approval chain — confirmed held in the one real run on record; the notification itself still fires as a side effect of *requesting* approval, which is a real-world event even when the answer is "blocked" |
| `core/mcp_server.py` (14+ tools incl. `db_quarantine`, email delete, browser actions) | Real DB quarantine / real email deletion / real browser actions, if served and a client connects | **No** | None — Task 60's own finding: "no `PermissionGateway` enforcement and a fail-open security wrapper." Not reachable from the autonomous loop, but fully reachable from a manual `python core/mcp_server.py` dev invocation |
| No `subprocess`/`Popen`/`os.system` found in any `tests/` file's own body during this scoped search beyond the already-cited `autoresearch_runner.py` real-run and the (test-mocked, not real) 58B/58C/58E/58F/58G entries already covered by Task 60's own inventory | — | — | Everything else found in `tests/` that references `subprocess` mocks the call (`unittest.mock.patch`/`AsyncMock`) rather than invoking a real one — consistent with this repo's own testing.md convention of "mocking external APIs is acceptable." Not independently re-verified line-by-line for every one of the 1712 files with a `__main__` block found by the earlier broad grep — see Limitations. |

## Ranked hazard list (most concerning first)

1. **`core/mcp_server.py`** — real, ungated, destructive tool surface (DB quarantine, email
   deletion, browser actions), reachable by any manual dev invocation, already independently
   confirmed by a prior dedicated red-team task (Task 60) and never remediated (explicitly
   accepted as out-of-scope residual risk for the *autonomous-loop* experiment, but this M1c
   audit's scope is broader — any *developer-invoked* path).
2. **`core/memory/episodic.py`'s `__main__`** — unconditionally overwrites real `semantic_memory`
   data (`owner_name`) with no isolation guard whatsoever, not even an attempted (if broken) one
   like `goal_system.py` had. The most "invisible" of the DB-mutation hazards, since nothing about
   running it looks dangerous and its own printed output (`✅ episodic.py OK`) gives no hint a real
   write occurred.
3. **The general "bare `python <file>.py` as a verification step" pattern itself** — now confirmed
   to have caused real incidents via at least two independent mechanisms (env-var/dotenv precedence
   for the SQLite-singleton files; `sys.path` resolution ambiguity for any relative-path invocation
   per the `89D` report) — this is the systemic root cause, not any single file.
4. **`core/memory/policy.py`'s `__main__`** — real DB write, low severity today only because of a
   disciplined unique-key convention that a future editor could accidentally weaken.
5. **`autoresearch_runner.py`'s real Pushover notification on verification** — not a safety failure
   (the gate held), but a reminder that "verification" in this codebase can have real-world
   side effects even when the dangerous action itself is correctly blocked.

## Limitations of this pass

- The initial broad grep for `if __name__ == "__main__":` found **1712 files** in this repository.
  This audit read and verified the specific files flagged by prior reports (R12-H, 52, 58D, 89D, 60)
  plus the two SQLite-singleton-adjacent modules referenced there (`episodic.py`, `policy.py`,
  `epistemic_tracker.py`, `counterfactual.py`, `plans.py`) and confirmed each one directly via
  source read rather than trusting the prior report's characterization alone. It did **not**
  individually re-read all 1712 files' `__main__` blocks — that would be a full-codebase audit
  beyond this directive's scope. Any file among the other ~1700 not already flagged by an existing
  report is classified **NOT OBSERVED**, not "safe."
- Git commit *bodies* were searched for verification-command patterns; commit *diffs themselves*
  (which could show a command run in a code comment or test docstring not captured by the message
  search) were not exhaustively grepped.
