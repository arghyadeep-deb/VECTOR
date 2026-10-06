# VECTOR CLI Batch B Audit Plan

## Scope

Audit only the 61 production files assigned in `vectorcode/src/vector_cli/`, plus narrowly scoped regression tests and the required append-only audit record.

## Method

1. Read the repository rules and every assigned file completely.
2. Run syntax/AST and targeted security/correctness scans, including persistence, path confinement, credential handling, timing-safe comparisons, subprocess boundaries, falsy defaults, logging, and state reuse.
3. Trace repository-wide callers before changing public behavior or declaring code unwired.
4. Reproduce each candidate defect and add a failing regression test.
5. Apply the smallest safe fix, then run focused tests and relevant static checks.
6. Review the final diff, re-run verification, and append the findings to `docs/OPEN_ISSUES.md` using the then-current next item number.

## Guardrails

- Do not modify production files outside the assigned list.
- Preserve unrelated working-tree changes.
- Flag policy/design questions instead of guessing.
- Do not commit; the parent session will review the working tree.
