# Capability Proof — trading

**Verdict: NEEDS-CONFIG (same environmental DB contention as `investment.md` — NOT a code defect)**

See `investment.md` for the full root-cause analysis: a leftover process from
earlier in this session (PID 48532, `run_vector.py api`) held a concurrent
connection to `vector_memory.db`, and `TradingConductorAgent` hit the exact
same SQLCipher contention as `FinAgentAgent` did moments earlier — on a
completely different class/module, which is what confirms this is
process-level contention, not a `trading_conductor_agent.py` defect.
Re-run after closing concurrent VECTOR processes for a clean verdict.

Run at: 2026-06-20T12:42:29.594890+00:00

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
  File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\scripts\capability_smoke.py", line 155, in _live_trading
    agent = TradingConductorAgent()
  File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\districts\investment\trading_conductor_agent.py", line 56, in __init__
    self._memory  = EpisodicMemory()
                    ~~~~~~~~~~~~~~^^
  File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\core\memory\episodic.py", line 553, in __init__
    self.conn = get_db_connection()
                ~~~~~~~~~~~~~~~~~^^
  File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\core\memory\episodic.py", line 435, in get_db_connection
    raise MemoryDatabaseUnavailable(_unavailable_message(db_path)) from exc
core.memory.episodic.MemoryDatabaseUnavailable: [VECTOR][memory] Local SQLCipher memory DB is unreadable: C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vector_memory.db. The file appears encrypted or corrupted and cannot be opened with the current DB key. If this DB has memories you need, restore the original VECTOR_DB_KEY/keyring entry. To start fresh without deleting the old file, run: python run_vector.py memory-repair
```
