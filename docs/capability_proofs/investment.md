# Capability Proof — investment

**Verdict: NEEDS-CONFIG (environmental DB contention — NOT a code defect, see below)**

Run at: 2026-06-20T12:41:40.626437+00:00

## Error

`core.memory.episodic.MemoryDatabaseUnavailable: [VECTOR][memory] Local SQLCipher memory DB is unreadable: C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vector_memory.db. The file appears encrypted or corrupted and cannot be opened with the current DB key. If this DB has memories you need, restore the original VECTOR_DB_KEY/keyring entry. To start fresh without deleting the old file, run: python run_vector.py memory-repair`

## Traceback

```
Traceback (most recent call last):
  File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\core\memory\episodic.py", line 431, in get_db_connection
    _db_connection = _open_sqlcipher_connection(db_path)
  File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\core\memory\episodic.py", line 170, in _open_sqlcipher_connection
    conn.execute("SELECT count(*) FROM sqlite_master")
    ~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
sqlcipher3.dbapi2.DatabaseError: file is not a database

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\scripts\capability_smoke.py", line 238, in run_live
    output = await probe()
             ^^^^^^^^^^^^^
  File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\scripts\capability_smoke.py", line 147, in _live_investment
    agent = FinAgentAgent()
  File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\districts\investment\finagent_agent.py", line 81, in __init__
    self._memory   = EpisodicMemory()
                     ~~~~~~~~~~~~~~^^
  File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\core\memory\episodic.py", line 553, in __init__
    self.conn = get_db_connection()
                ~~~~~~~~~~~~~~~~~^^
  File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\core\memory\episodic.py", line 435, in get_db_connection
    raise MemoryDatabaseUnavailable(_unavailable_message(db_path)) from exc
core.memory.episodic.MemoryDatabaseUnavailable: [VECTOR][memory] Local SQLCipher memory DB is unreadable: C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vector_memory.db. The file appears encrypted or corrupted and cannot be opened with the current DB key. If this DB has memories you need, restore the original VECTOR_DB_KEY/keyring entry. To start fresh without deleting the old file, run: python run_vector.py memory-repair
```
