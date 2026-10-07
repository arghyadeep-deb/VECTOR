# OD-52 Audit SQLCipher Migration Plan

1. Add disk-backed regression tests proving fresh audit databases encrypt secret-bearing events, plaintext databases migrate without changing event or Merkle-chain data, backups remain intact, and encrypted databases are not migrated twice.
2. Reproduce the plaintext-storage and fail-open severity behavior against the current implementation.
3. Port the established `PersonModel` SQLCipher connection and backup-preserving migration pattern into `AuditLogger`, retaining the shared database key, explicit cipher page size, standard pragmas, and existing schema migration.
4. Change unknown severity actions to fail closed with `block`.
5. Compile every touched Python file and run the focused and existing audit test suites.

