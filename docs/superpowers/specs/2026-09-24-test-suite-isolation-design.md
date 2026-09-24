# Test-suite isolation — design (2026-09-24)

Sub-project **E** of the "make everything an integral part of VECTOR" program
(others: C header cleanup, D content pipeline, B core/ module triage, A vendored trees).
Prerequisite for the rest: every later change needs a full-suite run that must not touch live state.

## Problem

- The test suite writes into the owner's live `vector_memory.db` and other live stores.
  About 51 test files use the memory DB with no isolation; 58 isolate only by opting in to
  the `isolated_vector_db` fixture.
- Several stores ignore `VECTOR_DB_PATH` and hard-code the repo's `data/` folder:
  `epistemic.db`, `suggestion_queue.db`, `counterfactual.db`, `person_models.db`,
  `meta_cognition.db`, `telemetry.db`.
- Consequences seen on 2026-09-24: seven `test_postiz_absorption` tests failed on a rerun because
  an earlier run left a 24-hour `blog_dedup` row in the live DB; `test_fresh_domain_no_penalty`
  reads the live causal graph and drifts as it grows; every full-suite run mutates live state,
  which the owner's standing rule forbids.

## Decision

One **fresh temporary database per pytest session** (approach 1, chosen by the owner), with a hard guard
against ever resolving to a live path. Tests keep sharing state *within* a session exactly as today, so
behaviour changes minimally; nothing survives to the next run.

Rejected: a fresh DB per test (slow: about 6,000 encrypted DB creations; breaks tests that rely on state
from earlier tests) and detection-only (fails ~51 files until each is hand-fixed, no isolation).

## Design

### 1. Redirect and guard — `tests/conftest.py`, at import time (before VECTOR modules load)

- Create a session temp dir.
- `VECTOR_DB_PATH = <tmp>/vector_memory.db`. Sibling DBs derived via `configured_db_path().with_name(...)`
  (`email.db`, `post_jobs.db`, `content_jobs.db`) follow automatically.
- `VECTOR_TEST_DATA_DIR = <tmp>/data` (already honoured by `core.runtime_paths.data_path()`,
  `districts/content/post_job.py`, `districts/content/video_pipeline.py`).
- `VECTOR_DB_KEY` = a dummy test key so the SQLCipher DB never uses the owner's real key.
- **Guard:** after setting these, resolve `configured_db_path()` and `data_path("x").parent`; if either
  is the repo's real `vector_memory.db` or under `<repo>/data`, abort the session with a clear message.
- The existing opt-in `isolated_vector_db` fixture keeps working unchanged (it narrows to a per-test path).
- Temp dir is removed at session end; the guard state is checked again at session finish.

### 2. Stores that ignore those variables (~8 one-line changes)

Route these through `core.runtime_paths.data_path()`:
`core/brain/epistemic_tracker.py`, `core/brain/suggestion_queue.py`, `core/memory/counterfactual.py`,
`core/brain/person_model.py`, `core/city/meta_cognition.py`, and the `data/telemetry.db` sites in
`core/inference/ollama_safe.py` and `core/metering/inference_observability.py`.
In production `data_path()` resolves to `<repo>/data/...`, identical to today; each change carries a test
asserting the production path is unchanged (with the test env vars unset).

### 3. Proving it works

Before the full run, snapshot size + mtime of the live `vector_memory.db` and every `data/*.db`;
after the run, compare. The owner's live loop may write some of these itself, so differences are
inspected, not asserted zero. The full sharded suite then gives the baseline comparison
(5,012 passed / 13 failed / 36 skipped) that was left incomplete.

### 4. Tests that relied on live data

Anything failing only because the DB is now empty is reported. Fixing a test to build its own fixture data
is in scope; weakening an assertion is not. `test_fresh_domain_no_penalty` becomes deterministic
(empty causal graph). Known pre-existing failures stay documented, not hidden.

## Error handling

- Guard failure → abort with the offending path and the variable to fix; never fall back to the live path.
- If a store still writes outside the temp dir (found by the snapshot comparison), it is added to section 2.

## Testing

- `tests/test_suite_isolation.py`: (a) guard aborts on a live-path override (subprocess); (b) the session
  DB path is under the temp dir; (c) each redirected store's production path equals the old hard-coded path
  when the test env vars are unset; (d) two sequential sessions do not share blog-dedup state.
- Full sharded suite run + snapshot comparison as the acceptance check.

## Out of scope

Per-test DB isolation; deleting or migrating any live data; changing production path layout;
the other sub-projects (C, D, B, A).
