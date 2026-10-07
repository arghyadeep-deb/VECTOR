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
| G1 | Reasoning ceiling (free-tier-only runtime policy) | Owner (policy) | **Accepted** | Owner's existing runtime policy (`.claude/rules/models.md`); no AI-executable action exists for this gap, only an owner-decision input document | 2026-07-08 (original policy) | Revisit if a cost/quality analysis is produced and the owner reviews it — not yet done | Owner explicitly changes the free-tier-only policy |
| G2 | Recurring bug classes (phantom-success, fail-open, os.environ-direct, non-atomic-write, missing-UTF8, banned-imports, loguru misuse, CWE-22) | Claude+Codex | **Controlled** (partial — not eliminated) | `scripts/bug_class_lint.py` (commit `f0ee1dfb8`, wired `089bf8057`): BLOCKING tier for flask/pickle/requests in `.claude/hooks/pre_commit_gate.py` + CI; ADVISORY tier (report-only) for threading/env-secret/loguru — too large an existing surface (80/150+/90 files) to grandfather responsibly in one sitting | 2026-10-07 | **Needs a dedicated follow-up**: promote threading/env-secret/loguru to BLOCKING once each has an individually-reviewed grandfather list | A new violation of flask/pickle/requests lands (should be impossible now — CI/hook block it); or the advisory-tier counts need to start trending toward zero on a real schedule |
| G3 | Safety-gate bugs recurring (red-team phantom-approval, sandbox fail-open, gateway bypass) | Claude+Codex | **Controlled** | `tests/test_safety_gate_fault_injection.py` (commit `88586ac00`) — 14 fault-injection tests covering gateway-unavailable bypass, red-team timeout/exception/unparseable-verdict, `_classify()` crash-on-malformed-input, durable-audit-write-failure. 6 independently re-confirmed failing pre-fix | 2026-10-07 | Re-run this suite after any change to `permission_gateway.py`, `autonomous_loop.py`, `red_team_agent.py`, or `core/sandbox/` | A new caller path bypasses `_get_gateway()` without going through the checks this suite covers — the suite itself doesn't claim to have found every bypass, only the ones a deliberate search turned up |
| G4 | Stubbed/incomplete features backlog (growth district scaffolding, unwired second permission system, dead cron lifecycle, etc.) | Owner (per-item decision) | **In progress** | `docs/design/owner-decision-backlog.md` — inventory normalization only (mechanical aggregation + re-verification against current code), NOT technical closure. Each row still needs an owner wire/delete/defer decision | 2026-10-07 | N/A until owner reviews the backlog doc | Each row closes individually once the owner decides and it's executed |
| G5 | VECTOR cannot audit/fix itself (self-patching) | Owner (authorization), Claude+Codex (build) | **Accepted** (deliberately deferred) | No code built yet. Converged design exists (docs/plans/2026-10-07-improvement-debate.md, "Stage B — supervised patch proposal"): immutable allowlist of proven-safe AST transforms, disposable credential-free checkout, zero ability to touch tests/rules/CI/baselines, zero stage/commit/merge/push capability, landing requires an owner-authorized external principal | 2026-10-07 (design only) | Revisit once gaps 2/3/7/8 have been solid for a meaningful stretch — rushing this recreates the exact self-reinforcing-false-success risk this whole audit found repeatedly | Owner explicitly authorizes building Stage B |
| G6 | Vendored-tree scope (~5,100 files, wiring-check only) | Owner (per-component decision) | **Accepted** (as a standing policy, not yet decided per-component) | Standing wiring-check-only policy, unchanged. Codex's round-3 refinement: 4 dispositions per component exist (remove-if-unused / pinned-external-dependency-with-SBOM / reachability-scoped-review / commission-full-depth-for-critical-ones) — not yet applied per-component | Policy: 2026-10-01; refinement: 2026-10-07 | Needs an owner-reviewed component list with a disposition per component — not yet built | Owner asks for the per-component disposition list, or a specific vendored component becomes newly reachable/load-bearing |
| G7 | Enforcement integrity / bypass resistance | Claude+Codex | **Partially controlled** | Fixed 2 concrete bypass paths (commit `d003aba53`): `pre_commit_gate.py` syntax-gate-exception now fails closed; `auto_commit.py` no longer passes `--no-verify`. **Unverified**: whether GitHub branch protection is actually configured on `main` — `gh` CLI unavailable in this environment | 2026-10-07 | **Needs next session**: run `gh api repos/arghyadeep-deb/VECTOR/branches/main/protection` (install `gh` first) or ask the owner to check `github.com/arghyadeep-deb/VECTOR/settings/branches` directly | A new local-hook-only control is added without a corresponding CI-level enforcement |
| G8 | Gap-registry truth and closure evidence | Claude+Codex | **Eliminated** (this file is the fix) | This file. Supersedes the implicit assumption that `docs/OPEN_ISSUES.md` prose alone is sufficient tracking | 2026-10-07 | Re-check this file's own rows stay accurate whenever a gap's status changes — the discipline this file exists to enforce | This file itself goes stale (rows not updated after a real status change) — which is exactly the failure mode it exists to prevent, so treat any staleness here as a new finding, not a shrug |
| G9 | V1 acceptance | Owner (action required) | **Accepted** (frozen, not yet satisfied) | `VECTOR_TECHNICAL_KNOWLEDGE/STAGE_8_V1_REACCEPTANCE_2026-09-26.md` states the current frozen remaining criteria: owner-run voice/camera checks + a real day of use. No AI action can substitute for these | 2026-09-26 (criteria frozen) | Durable but revocable per the converged debate: an ordinary future finding → V1.x backlog, never reopens the whole contract; only a newly discovered CRITICAL vuln or evidence the original verdict was false suspends acceptance, and then only the affected checks rerun | Owner completes the voice/camera checks + a real day of use, OR a critical vuln is found in already-accepted scope |
| G10 | Hook-tree reconciliation (`.claude/hooks/` vs `vectorcode/hooks/`) | Claude+Codex | **Eliminated** | `vectorcode/hooks/README.md` + `tests/test_claude_settings_hooks_point_at_live_dir.py` (commit `db1daf1d5`) — confirmed `vectorcode/hooks/` is a one-time historical snapshot with zero live callers; the live tree is unambiguous and tested | 2026-10-07 | N/A — closed | A new hook is added to `.claude/settings.json` pointing somewhere other than `.claude/hooks/` (the regression test catches this automatically) |

## Summary as of 2026-10-07

- **Eliminated: 2** (G8, G10)
- **Controlled: 3** (G2 partial, G3, G7 partial)
- **In progress: 1** (G4)
- **Accepted (owner-only, not yet actioned): 4** (G1, G5, G6, G9)

This is NOT "10/10 gaps fixed." It is an honest accounting of exactly where
each one stands, which is the actual deliverable the debate converged on.
