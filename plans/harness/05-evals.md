# Harness Analysis 05 — Evals & Regression
> 2026-07-07, Fable 5. Define "better," catch regressions early, find proxy drift.

## What "better" actually means here (not vanity)
The owner's real want (revealed by behavior): **VECTOR that actually RUNS and does
useful work reliably, built with honest status and minimal rework.** So "better" =
- fewer false "it's done" claims (honesty/correctness),
- fewer regressions reaching the owner,
- more capability that's actually OPERATING (not just built),
- less time re-fighting settled problems.
NOT vanity: LOC, number of districts/skills, "features added."

## What's measured today (real)
- `scripts/smoke_test.py` (38 checks), `scripts/integration_check.py` (51
  wiring checks), pytest suites, per-module `__main__` self-tests, `check_coverage.py`.
- CI (`.github/workflows/ci.yml`) enforces pytest.
- The wake-word quality gate (recall fraction) — a good model-quality eval pattern.

## Gaps / proxy drift (findings)
1. **Coverage % is a drifting proxy.** ~29% coverage is tracked, but coverage ≠
   correctness or honesty. Optimizing coverage would drift from what matters.
   KEEP it as a floor, don't optimize it as the goal.
2. **No eval for the thing that matters most: "does a claimed fix actually
   hold when run 24/7?"** Smoke/integration are static; there's no burn-in or
   soak eval because VECTOR isn't running. The real regression surface only
   appears at runtime.
3. **No regression corpus for the honesty/quality gates** — e.g. no test that
   the injection scanner catches known payloads, no eval that routing picks the
   right domain model, no eval that "done" claims are backed by evidence.
4. **No harness-level eval** (is Claude getting better/worse at this project
   session-over-session?).

## Evals to build (concrete)
1. **Routing eval:** `tests/eval/test_domain_routing_eval.py` — given N sample
   tasks, assert each routes to the expected domain/tier; track pass rate.
2. **Injection eval:** `tests/security/injection_corpus.jsonl` + a test asserting
   the scanner flags every known payload (detection-rate metric over time).
3. **Soak/burn-in check:** once VECTOR runs as a service, a nightly job that
   asserts the loop is alive, no coroutine died, memory DB isn't bloating, quota
   ledger is sane. (Ties to `sre_monitor`/`devops_automator`.)
4. **"Evidence-backed done" gate:** a lint/hook that flags a commit message
   claiming "fixed/passing" without a matching test run in the session
   (partial: pre_commit_gate hook exists — extend it).
5. **Regression baseline:** snapshot smoke/integration counts (38/51) and fail
   CI if they drop — a canary for silent breakage.

## The one thing to watch
The biggest proxy risk is **"features built" standing in for "value delivered."**
Every "what more can I build" is that proxy. The real metric is uptime × useful
actions taken — unmeasurable until VECTOR runs. Install the service; then measure that.

## Provenance
2026-07-07. Sources: `scripts/smoke_test.py`, `scripts/integration_check.py`,
`.github/workflows/ci.yml`, `check_coverage.py`, `tests/`.
