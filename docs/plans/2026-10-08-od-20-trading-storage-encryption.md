# OD-20 trading-storage encryption plan

## Scope

Encrypt the three overlapping trading-analysis artifacts identified by the
OD-20 investigation and approved by the owner:

- per-ticker LangGraph checkpoint databases;
- `VectorTradingGraph._log_state()` result files;
- `TradingMemoryLog` decision/reflection files.

Do not alter unrelated CLI report/message files or trading behavior.

## Implementation

1. Add focused regressions that exercise a real LangGraph checkpoint round
   trip, result-state round trip, memory-log round trip, plaintext migration
   backups, raw-byte confidentiality, and fail-closed key handling.
2. Change `core/trading/graph/checkpointer.py` to open SQLCipher connections
   with the shared episodic DB key and 4096-byte cipher pages. Migrate existing
   plaintext LangGraph tables into a fresh encrypted DB while retaining a
   timestamped plaintext sibling backup.
3. Add a small `core/trading/storage_crypto.py` helper using AES-GCM and a key
   derived from the same `core.memory.episodic._get_db_key()` secret. Provide
   authenticated, versioned ciphertext framing, transparent decrypt reads,
   atomic writes, and one-time plaintext backups.
4. Route `VectorTradingGraph._log_state()` and every `TradingMemoryLog` read and
   write through that helper. Preserve their existing logical JSON/Markdown
   serialization and parsing behavior.
5. Make missing SQLCipher, missing keys, authentication failures, and malformed
   encrypted payloads raise instead of falling back to plaintext.

## Verification

1. Record the new tests failing against the pre-fix implementation, using a
   production-file-only stash if repository index permissions allow it.
2. Run `python -m py_compile` on every changed Python file.
3. Run the new regressions plus existing checkpoint, trading-graph, memory-log,
   and trading audit tests.
4. Confirm raw on-disk checkpoint, JSON, and Markdown bytes contain neither a
   SQLite header/schema nor the written sensitive marker strings.
5. Review `git diff` and `git status`; leave all changes unstaged and uncommitted.
