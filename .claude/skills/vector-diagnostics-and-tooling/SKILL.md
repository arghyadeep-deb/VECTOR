---
name: vector-diagnostics-and-tooling
description: Load when you need to MEASURE VECTOR's state instead of eyeballing it — health snapshot, coverage, wiring audit, DB size, soak/burn-in, kokoro/voice diagnosis. Points to the real diagnostic scripts + how to read them. Triggers: "is VECTOR healthy", "measure", "diagnose", "audit wiring", "coverage", "why is X slow", "DB size", "soak test", "diagnostic".
---

# VECTOR Diagnostics & Tooling

How to MEASURE, not guess. VECTOR ships a large `scripts/` diagnostic toolset;
this skill maps the useful ones with interpretation. Ground truth 2026-07-07.
Evidence discipline: commands below were RUN and their real output quoted, or
tagged `[UNVERIFIED-CMD: reason]`.

## When NOT to use this skill
For running/operating VECTOR use `vector-run-and-operate`; for the acceptance bar
use `vector-validation-and-qa`; for debugging a specific break use
`vector-debugging-playbook`.

## The fast health snapshot
```
python .claude/skills/vector-diagnostics-and-tooling/scripts/health_snapshot.py
```
Ships in this skill's `scripts/` dir — one command that reports Python/torch/CUDA,
config load, memory-DB size, and smoke status. Read it top-to-bottom; any line
starting `FAIL` is the thing to fix first.

## The core diagnostic commands (verified 2026-07-07)
| Command | What it measures | Healthy reading |
|---|---|---|
| `python scripts/smoke_test.py` | 38 core wiring checks | RAN → `Smoke tests: 38/38 PASS` |
| `python scripts/integration_check.py` | 51 integration/wiring checks | expect `ALL WIRING VERIFIED` (51/51) |
| `python run_vector.py --mode doctor` | environment/health doctor | `[UNVERIFIED-CMD: long-running, not run this session]` |
| `python run_vector.py --mode readiness-check` | readiness gate | `[UNVERIFIED-CMD: long-running]` |
| `python scripts/check_soak.py` | soak/burn-in signal (loop alive, no dead coroutines) | run once VECTOR is running as a service |
| `python scripts/check_coverage.py` | test coverage % (gates on %, no longer masks errors) | ~29% floor (2026-06-28) |
| `python scripts/audit_wiring.py` / `audit_all_wiring.py` | agent/district wiring completeness | no orphaned dispatch routes |
| `python scripts/diagnose_kokoro.py` | voice/TTS model diagnosis | reports kokoro model presence + GPU load |
| `ls -lh vector_memory.db` | memory DB size | RAN → `134M` (healthy post-2026-06-29 cleanup; watch for GB-scale bloat) |

## Interpretation guides
- **DB size climbing toward GBs** → the context_budget FTS-dump bug is back; see
  `vector-debugging-playbook` (DROP+CREATE the FTS table, stop the dump).
- **smoke < 38 or integration < 51** → a wiring regression; do NOT ship. Bisect
  the failing check name.
- **coverage dropping** → a canary, not the goal (see `plans/harness/05-evals.md`);
  don't optimize coverage as an end.
- **doctor/readiness-check red** → environment or readiness gap; read the specific
  failure line.

## Adding a diagnostic
Put measurement scripts in `scripts/` (repo) or this skill's `scripts/`. Rule:
a diagnostic must PRINT a machine-readable pass/fail line, not require eyeballing.

## Provenance and maintenance
2026-07-07. Verified this session: smoke `38/38 PASS`, DB `134M`. Re-verify the
full list: `ls scripts/ | grep -iE "audit|check|diagnos|coverage|soak"`. The
doctor/readiness-check modes are real (`grep -oE "doctor|readiness-check" run_vector.py`)
but were not run here (tagged UNVERIFIED-CMD above) — run them on a live box.
