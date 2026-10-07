# OD-41 plaintext SQLite store migration plan

## Scope

Encrypt only the three owner-design-backlog stores named for this task:

- `vectorcode/src/vc_agents/digest_store.py`
- `vectorcode/src/connectors/store.py`
- `vectorcode/src/vc_tools/storage/sqlite.py`

Do not modify the compatibility shim, caller modules, filesystem tools, or
`connectors/sync_engine.py`.

## Implementation

1. Add real-file regression tests for fresh encrypted databases, automatic
   plaintext migration, exact row preservation, preserved plaintext backups,
   and one-time migration.
2. Reuse the established `core/brain/person_model.py` SQLCipher import and
   fallback pattern in each store, including delegation to
   `core.memory.episodic._get_db_key()`, plaintext-header detection, explicit
   `cipher_page_size = 4096`, and restore-on-failure migration behavior.
3. Keep `DigestStore` rows as tuples. Recreate its current schema and run its
   existing additive column migration before dynamically replaying columns.
4. Recreate the complete `KnowledgeStore` schema, including FTS5 and all three
   triggers, before replaying `knowledge_chunks`; let the insert trigger rebuild
   `knowledge_fts`.
5. Recreate `SQLiteMemory`'s base and FTS tables, dynamically replay
   `documents`, then explicitly rebuild `documents_fts` from the base table.
6. Use the matching module's `Row` type only for stores that previously used
   `sqlite3.Row`; preserve `:memory:` behavior.

## Verification

1. Demonstrate the new regression tests fail before production changes.
2. Run `python -m py_compile` for every touched Python file.
3. Run all new migration tests.
4. Run targeted existing digest, connector, knowledge, and `vc_tools` storage
   suites selected by filename and pytest `-k` expressions.
5. Review `git diff` and `git status`; do not commit.
