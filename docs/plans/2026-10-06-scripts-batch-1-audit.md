# Root scripts batch 1 audit plan

## Scope

Audit only the 30 owner-assigned files in `scripts/`, plus regression tests required
for narrow fixes and one append-only entry in `docs/OPEN_ISSUES.md`.

## Method

1. Read every assigned script completely and inventory its inputs, writes, subprocesses,
   imports, error handling, and success criteria.
2. Search repository automation, documentation, manifests, and source for references to
   each filename/module to classify it as live/load-bearing, manually reusable, pytest
   collected, or an apparently completed one-off.
3. Reproduce each credible defect without changing code. Prioritize path confinement,
   atomic persistence, encoding, secret exposure, argument injection, false success,
   wrong imports, and falsy-value handling.
4. Add a focused pytest regression test, observe it fail, then implement the smallest
   safe fix in the assigned script and rerun the focused test.
5. Run syntax/import/static checks and all new focused tests. Review the final diff for
   scope, security, and accidental changes.
6. Re-read the current end of `docs/OPEN_ISSUES.md`, allocate the next available issue
   number, and append findings plus the complete live-versus-one-off classification.

## Guardrails

- Do not edit files owned by the parallel batches.
- Do not change public signatures without first finding all callers.
- Do not "fix" test-like scripts that pytest collects; report their status instead.
- Flag policy/design ambiguity instead of choosing behavior without evidence.
- Preserve all unrelated working-tree changes.
