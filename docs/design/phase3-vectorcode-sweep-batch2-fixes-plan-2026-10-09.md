# Phase 3 Vectorcode Sweep Batch 2 — Remediation Plan

This plan tracks the ordered remediation requested for the gateway findings in
`phase3-vectorcode-sweep-batch2-2026-10-09.md`. Each item is completed and
verified independently before work begins on the next item.

1. Trace the reported source-to-sink path and the nearest repository-native
   enforcement precedent.
2. Add a focused regression test for the specific security invariant.
3. Apply the smallest fail-closed fix that preserves legitimate behavior.
4. Compile every touched Python file and run the focused existing and new tests.
5. Temporarily stash only the implementation file(s), leaving the regression
   test present, and confirm the test fails against the pre-fix implementation.
6. Restore the implementation, rerun verification, and inspect the final diff.

GW-1 uses the finding's authorized endpoint-disable fallback: the standalone
engine's `permission_gateway` constructor field is not consumed by its tool
execution loop, so merely injecting the shared gateway would not enforce the
security boundary. `/run` and `/stream` must fail with HTTP 503 until they can
delegate to a genuinely governed runner with authenticated actor identity,
project confinement, and an explicit tool allowlist.
