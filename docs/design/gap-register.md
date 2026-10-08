# VECTOR Gap Register

**Purpose (gap 8 of the post-audit improvement plan, debated and converged
2026-10-07 — full transcript in `docs/plans/2026-10-07-improvement-debate.md`).**
This repo has, twice this cycle, had a "fully audited" claim that didn't
survive closer inspection (see `core/sandbox/` missing from every core/
audit batch despite core/ being marked complete; `.claude/hooks/` diverging
silently from the already-"fixed" `vectorcode/hooks/`). Narrative claims in
commit messages and `docs/OPEN_ISSUES.md` prose are easy to lose track of
and easy to overclaim from. This file is the single place that tracks
closure status per gap, with the three honest outcomes distinguished:

- **Eliminated** — the defect/gap no longer exists.
- **Controlled** — residual risk is bounded by a real, tested enforcement
  mechanism, but the underlying condition hasn't been fully removed.
- **Accepted** — the owner knowingly keeps the limitation (a policy
  decision, not a defect).

A gap is never just "done." Every row below states which of the three it
is, what the actual proof is, and — for **accepted** rows — when that
acceptance should be revisited.

**How to use this file:** when a gap's status changes, edit its row here
AND add the detailed evidence to `docs/OPEN_ISSUES.md` as usual — this file
is the index with the current truth; `OPEN_ISSUES.md` is the historical
record of how it got there. If the two ever disagree, trust whichever has
the more recent, more specific proof artifact (a commit hash + passing
test), not whichever sounds more confident.

| ID | Gap | Owner | Closure Type | Proof Artifact | Date | Review/Expiry | Reopening Condition |
|---|---|---|---|---|---|---|---|
| G1 | Reasoning ceiling (free-tier-only runtime policy) | Owner (policy) | **Accepted** | `docs/design/reasoning-ceiling-analysis.md` (commit `39a54b973`) — owner reviewed 2026-10-08 and explicitly reaffirmed: stay free-tier-only, no paid keys | 2026-10-08 (owner reviewed and reaffirmed) | Reviewed and closed — no further action unless the owner revisits | Owner explicitly changes the policy in a future session |
| G2 | Recurring bug classes (phantom-success, fail-open, os.environ-direct, non-atomic-write, missing-UTF8, banned-imports, loguru misuse, CWE-22) | Claude+Codex | **Controlled** (partial — not eliminated) | `scripts/bug_class_lint.py` (commit `f0ee1dfb8`, wired `089bf8057`): BLOCKING tier for flask/pickle/requests in `.claude/hooks/pre_commit_gate.py` + CI; ADVISORY tier (report-only) for threading/env-secret/loguru — too large an existing surface (80/150+/90 files) to grandfather responsibly in one sitting | 2026-10-07 | **Needs a dedicated follow-up**: promote threading/env-secret/loguru to BLOCKING once each has an individually-reviewed grandfather list | A new violation of flask/pickle/requests lands (should be impossible now — CI/hook block it); or the advisory-tier counts need to start trending toward zero on a real schedule |
| G3 | Safety-gate bugs recurring (red-team phantom-approval, sandbox fail-open, gateway bypass) | Claude+Codex | **Controlled** | `tests/test_safety_gate_fault_injection.py` (commit `88586ac00`) — 14 fault-injection tests covering gateway-unavailable bypass, red-team timeout/exception/unparseable-verdict, `_classify()` crash-on-malformed-input, durable-audit-write-failure. 6 independently re-confirmed failing pre-fix | 2026-10-07 | Re-run this suite after any change to `permission_gateway.py`, `autonomous_loop.py`, `red_team_agent.py`, or `core/sandbox/` | A new caller path bypasses `_get_gateway()` without going through the checks this suite covers — the suite itself doesn't claim to have found every bypass, only the ones a deliberate search turned up |
| G4 | Stubbed/incomplete features backlog (growth district scaffolding, unwired second permission system, dead cron lifecycle, etc.) | Owner (per-item decision) | **Eliminated** (inventory complete; per-item wire/delete/defer decisions still owner's) | `docs/design/owner-decision-backlog.md` (commits `a5ca19414` + `fb9f9ca72`) — **64 distinct entries (OD-1 through OD-62 + 2 corrections), full `docs/OPEN_ISSUES.md` coverage (all 135 items) reached**. Caught 1 stale input claim. Highest-severity findings independently re-verified by the parent session: unencrypted real-person PII (`core/brain/person_model.py` + 6 more stores), a 15,576-file mystery directory (`vectorcode/skills/`), an unauthenticated gateway that can bind to all interfaces (`vectorcode/src/gateway/server.py` via `cli.py:694`), and a path-confinement feature that's a no-op in production (`vc_tools/file_read.py`/`file_write.py`) | 2026-10-07 | The inventory itself is done; re-open if a future audit finds an item this pass missed | Owner works through the 64-item list — this gap's "inventory normalization" job is complete; the gap shifts to 64 separate per-item decisions now tracked in the backlog doc, not in this register |
| G5 | VECTOR cannot audit/fix itself (self-patching) | Owner (authorization), Claude+Codex (build) | **Accepted** (deliberately deferred) | No code built yet. Converged design exists (docs/plans/2026-10-07-improvement-debate.md, "Stage B — supervised patch proposal"): immutable allowlist of proven-safe AST transforms, disposable credential-free checkout, zero ability to touch tests/rules/CI/baselines, zero stage/commit/merge/push capability, landing requires an owner-authorized external principal | 2026-10-07 (design only) | Revisit once gaps 2/3/7/8 have been solid for a meaningful stretch — rushing this recreates the exact self-reinforcing-false-success risk this whole audit found repeatedly | Owner explicitly authorizes building Stage B |
| G6 | Vendored-tree scope (~5,100 files, wiring-check only) | Owner (per-component decision) | **Accepted** (per-component list now built; `core/mining/` sub-question resolved 2026-10-08) | `docs/design/vendored-component-dispositions.md` (commit `3ff259672`) — all 10 vendored components enumerated with a recommended disposition each; found 2 new gaps while building it (`vector_hedgebot/` has no NOTICE.md; `core/mining/`'s classification). **`core/mining/` RESOLVED**: `docs/design/investigation-2026-10-08-channels-comms-and-mining-origin.md` found conclusive git-history evidence it's OpenJarvis-derived (absorbed in the 2026-05-15 "100% parity" commit, port markers in multiple files) — the repo already preserves OpenJarvis's Apache-2.0 license, so this is no longer even "unclear license," just a missing `NOTICE.md` (not yet written) | 2026-10-08 | Owner still needs to pick dispositions for the other 9 components + `vector_hedgebot/`'s missing NOTICE.md | Owner picks the remaining dispositions; `core/mining/NOTICE.md` still needs writing (mechanical, not yet done) |
| G7 | Enforcement integrity / bypass resistance | Claude+Codex | **Partially controlled** | Fixed 2 concrete bypass paths (commit `d003aba53`): `pre_commit_gate.py` syntax-gate-exception now fails closed; `auto_commit.py` no longer passes `--no-verify`. **Unverified**: whether GitHub branch protection is actually configured on `main` — `gh` CLI unavailable in this environment | 2026-10-07 | **Needs next session**: run `gh api repos/arghyadeep-deb/VECTOR/branches/main/protection` (install `gh` first) or ask the owner to check `github.com/arghyadeep-deb/VECTOR/settings/branches` directly | A new local-hook-only control is added without a corresponding CI-level enforcement |
| G8 | Gap-registry truth and closure evidence | Claude+Codex | **Eliminated** (this file is the fix) | This file. Supersedes the implicit assumption that `docs/OPEN_ISSUES.md` prose alone is sufficient tracking | 2026-10-07 | Re-check this file's own rows stay accurate whenever a gap's status changes — the discipline this file exists to enforce | This file itself goes stale (rows not updated after a real status change) — which is exactly the failure mode it exists to prevent, so treat any staleness here as a new finding, not a shrug |
| G9 | V1 acceptance | Owner (action required) | **Accepted** (frozen, not yet satisfied) | `VECTOR_TECHNICAL_KNOWLEDGE/STAGE_8_V1_REACCEPTANCE_2026-09-26.md` states the current frozen remaining criteria: owner-run voice/camera checks + a real day of use. No AI action can substitute for these | 2026-09-26 (criteria frozen) | Durable but revocable per the converged debate: an ordinary future finding → V1.x backlog, never reopens the whole contract; only a newly discovered CRITICAL vuln or evidence the original verdict was false suspends acceptance, and then only the affected checks rerun | Owner completes the voice/camera checks + a real day of use, OR a critical vuln is found in already-accepted scope |
| G10 | Hook-tree reconciliation (`.claude/hooks/` vs `vectorcode/hooks/`) | Claude+Codex | **Eliminated** | `vectorcode/hooks/README.md` + `tests/test_claude_settings_hooks_point_at_live_dir.py` (commit `db1daf1d5`) — confirmed `vectorcode/hooks/` is a one-time historical snapshot with zero live callers; the live tree is unambiguous and tested | 2026-10-07 | N/A — closed | A new hook is added to `.claude/settings.json` pointing somewhere other than `.claude/hooks/` (the regression test catches this automatically) |

## Summary as of 2026-10-07

- **Eliminated: 3** (G4, G8, G10)
- **Controlled: 3** (G2 partial, G3, G7 partial)
- **Accepted (owner-only, not yet actioned): 4** (G1, G5, G6, G9)

This is NOT "10/10 gaps fixed." It is an honest accounting of exactly where
each one stands, which is the actual deliverable the debate converged on.
