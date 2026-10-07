# OD-20 SQLCipher Migration Plan

## Goal

Encrypt the five VECTOR-owned plaintext SQLite stores named by OD-20 while
preserving existing data, using the already-proven OD-19/OD-52 migration
pattern and the single owner-managed key from `core.memory.episodic`.

## Scope

1. Email (`email.db`): make `core/email/schema.py` the sole connection and
   migration owner; route `core/api/routers/email.py` through it.
2. Contacts (`contacts.db`): add a lightweight shared schema/connection owner
   used by both `core/api/routers/relationships.py` and
   `districts/relationships/contact_manager.py`.
3. Persona evolution (`evolution.db`): migrate both owned tables in
   `core/persona/evolution.py`.
4. Scheduler (`scheduled_tasks`, `task_run_logs`): migrate in
   `core/scheduler/store.py`. The VectorCode path is a re-export shim and is
   intentionally unchanged.
5. MCP audit (`mcp_audit_log`): migrate in `core/security/mcp_security.py`.

`core/trading/graph/checkpointer.py` is explicitly out of scope.

## Pattern per database

- Prefer `sqlcipher3`, fall back to `pysqlcipher3`, then plain `sqlite3` with a
  prominent warning.
- Delegate `_get_db_key()` to `core.memory.episodic._get_db_key()`.
- Detect plaintext only by the 16-byte SQLite header.
- Before migration, copy the original to
  `<path>.plaintext.bak.<UTC timestamp>`.
- Remove the original path only after the backup exists, create an encrypted
  replacement, recreate the real schema, introspect every owned table with
  `PRAGMA table_info`, and copy every row.
- On any exception, close/remove the partial encrypted replacement and copy
  the retained plaintext backup back to the original path.
- Set `PRAGMA cipher_page_size = 4096` on every SQLCipher connection and use
  the SQLCipher driver's `Row` type.

## Verification

- Add one real-file regression test module for each database covering fresh
  encryption/raw-byte secrecy, plaintext migration with identical rows and a
  retained backup, and idempotent reopen.
- Demonstrate each new suite fails before production changes.
- Run `python -m py_compile` on every touched Python file.
- Run the new tests and the affected existing email, relationship, persona /
  evolution, scheduler, and MCP-security tests; report exact counts.
- Review `git diff` and confirm no changes to the trading checkpointer or the
  VectorCode scheduler shim.
