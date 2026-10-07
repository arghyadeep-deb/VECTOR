# OD-57 fail-closed database and HUD bootstrap plan

## Scope

- Make `SharedFacts` propagate SQLCipher open failures when encryption is active.
- Make main-database aliases in `db_registry` propagate SQLCipher open failures when encryption is active.
- Keep plain SQLite behavior only when SQLCipher is not active.
- Launch the local HUD through a temporary HTML redirect so the API key is absent from process argv.
- Do not change database schemas or the dormant engine implementations.

## Verification

1. Add focused regression tests and run them against the current implementation to capture the expected failures.
2. Apply the smallest error-handling and HUD-launch changes.
3. Re-run focused regressions, relevant existing suites, and `py_compile` for every touched Python file.
4. Inspect the final diff for schema changes and search for functional consumers of the two dormant engines.

