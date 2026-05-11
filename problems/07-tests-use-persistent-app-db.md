# Problem 07 - Tests Pollute The Persistent App DB

## Symptom

`tests/test_memory_curator.py` inserted an episode with a fixed ID:

```text
old-episode-smoke
```

Because tests use the real `vector_memory.db`, rerunning the test caused:

```text
sqlite3.IntegrityError: UNIQUE constraint failed: episodic_memory.id
```

## Why It Matters

Tests must be repeatable. A persistent memory DB is good for VECTOR, but tests
need isolation or unique data.

## Implemented Solution

Updated the memory curator test to generate a unique old episode ID using the
current timestamp.

## Remaining Work

- Add a test config path that points SQLite to a temporary DB.
- Stop all tests from writing to the production `vector_memory.db`.

