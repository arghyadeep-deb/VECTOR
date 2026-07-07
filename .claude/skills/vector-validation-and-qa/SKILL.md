---
name: vector-validation-and-qa
description: Load before claiming any VECTOR work is done, fixed, or passing — what counts as evidence here, the test suites, the quality-gate discipline. Triggers: "is it done", "verify", "tests pass", "before committing", "acceptance", "how do I test", "prove it works", "quality gate".
---

# VECTOR Validation & QA

What counts as evidence on this project. Never assert "done/fixed/passing"
without running the check and reading the output. Ground truth 2026-07-07.

## When NOT to use this skill
For running the app use `vector-run-and-operate`; for change rules use
`vector-change-control`.

## The evidence gate (run before claiming done)
```
python scripts/smoke_test.py         # expect: 38/38 PASS
python scripts/integration_check.py  # expect: 51/51 PASS
python -m pytest <relevant suite> -p no:cacheprovider -q
```
Plus the module self-test for any file you changed: most VECTOR modules end with
`if __name__ == "__main__":` running a real test and printing an OK/FAILED line
(a project convention — every file, every time; `.claude/rules/code_style.md`).

## Test discipline (`.claude/rules/testing.md`)
- Tests live in `tests/` mirroring module structure.
- **Never mock** `permission_gateway`, `session_hydration_prompt`, the HP system,
  or the SQLCipher `episodic_memory` — test the real thing (use a test DB).
- Mocking external APIs (Supabase, cloud LLMs) IS acceptable.
- pytest guards: many code paths check `"pytest" in sys.modules` to stay offline/
  deterministic (trust ladder recording, cloud LLM legs, quota ledger in-memory).
  Preserve these when adding tests — don't let tests hit live models.
- Windows: conftest sets `WindowsSelectorEventLoopPolicy` (else asyncio hangs);
  unique per-run basetemp + read-only-aware rmtree (else WinError 5).

## The quality-gate pattern (worth copying)
When producing an artifact whose quality can't be eyeballed, STAGE it and gate
before installing. Example (`scripts/train_wake_word_synthetic.py`): export to
`*.candidate.onnx`, measure real-clip RECALL FRACTION (>=50% must fire) + silence
false-positive (<0.30), install ONLY if it passes — else keep the working
fallback. LESSON: a `max()` over samples hides a bad model; measure the fraction
that actually works. Never judge success by eye.

## Coverage
`check_coverage.py` gates on %; fixed to not mask test ERRORS. Full run ~29%
(2026-06-28). CI (`.github/workflows/ci.yml`) enforces pytest (no continue-on-error).

## Provenance and maintenance
Dated 2026-07-07. Re-verify: `python scripts/smoke_test.py | tail -2`,
`python scripts/integration_check.py | tail -2`. Rules: `.claude/rules/testing.md`.
