# Test-Suite Isolation Implementation Plan

> **For agentic workers:** executed inline (executing-plans). Steps use checkbox syntax.

**Goal:** Every pytest session runs against a fresh temporary DB/data dir and aborts if it would touch live files.

**Architecture:** `tests/conftest.py` sets `VECTOR_DB_PATH`, `VECTOR_TEST_DATA_DIR`, `VECTOR_DB_KEY` at import time (before VECTOR modules load) and a guard verifies the resolved paths. The five stores that still hard-code the repo `data/` folder are routed through `core.runtime_paths.data_path()` (identical path in production). `counterfactual.py` and `meta_cognition.py` already use `data_path()`.

**Tech Stack:** pytest, sqlite3/SQLCipher, `core.runtime_paths`.

**Files:**
- Modify: `tests/conftest.py`
- Modify: `core/brain/epistemic_tracker.py:19`, `core/brain/suggestion_queue.py:21`, `core/brain/person_model.py:33-34`, `core/inference/ollama_safe.py:591`, `core/metering/inference_observability.py:33`
- Create: `tests/test_suite_isolation.py`

---

### Task 1: Route the five hard-coded stores through data_path()

- [ ] **Step 1: failing test** (`tests/test_suite_isolation.py`)
  ```python
  import subprocess, sys, os
  from pathlib import Path
  ROOT = Path(__file__).resolve().parents[1]

  def _prod_path(expr: str) -> str:
      env = {k: v for k, v in os.environ.items() if k not in ("VECTOR_TEST_DATA_DIR", "VECTOR_DATA_DIR")}
      return subprocess.check_output([sys.executable, "-c", expr], cwd=ROOT, env=env, text=True).strip().splitlines()[-1]

  def test_epistemic_default_db_is_repo_data_in_production():
      p = _prod_path("from core.brain.epistemic_tracker import _DEFAULT_DB; print(_DEFAULT_DB.resolve())")
      assert p == str((ROOT / "data" / "epistemic.db").resolve())
  ```
  (equivalent tests for `suggestion_queue._DEFAULT_DB`, `inference_observability._DB_PATH`)
- [ ] **Step 2:** `pytest tests/test_suite_isolation.py -k production -v` → PASS on current code (guards production paths), and a second test asserting they follow `VECTOR_TEST_DATA_DIR` when set → FAIL.
- [ ] **Step 3: implement** — replace `Path(CONFIG.get("data_dir","data")) / "epistemic.db"` with `data_path("epistemic.db")` (same for suggestion_queue); person_model: `base = data_path()`; ollama_safe: `db_path = data_path("telemetry.db")`; inference_observability: `_DB_PATH = data_path("telemetry.db")`. Import `from core.runtime_paths import data_path`.
- [ ] **Step 4:** run both tests → PASS.
- [ ] **Step 5:** `git commit -m "fix(tests): route remaining data/ stores through data_path()"`

### Task 2: Session redirect + guard in conftest

- [ ] **Step 1: failing test** — subprocess runs `pytest --collect-only` with `VECTOR_DB_PATH=<repo>/vector_memory.db` preset and expects a non-zero exit and "refusing to run" in output; a second test asserts a normal session's `configured_db_path()` is under the temp dir.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** at the top of `tests/conftest.py` (after imports): create `tempfile.mkdtemp(prefix="vector_pytest_")`; `os.environ["VECTOR_DB_PATH"]` = `<tmp>/vector_memory.db`, `VECTOR_TEST_DATA_DIR` = `<tmp>/data`, `VECTOR_DB_KEY` = dummy; if the *caller-preset* `VECTOR_DB_PATH` equals the repo's real DB, `pytest.exit("refusing to run: ...", returncode=3)`; verify after setting; register cleanup via `atexit` (`shutil.rmtree(..., ignore_errors=True)`).
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** `git commit -m "test: fresh temp DB/data dir per pytest session with live-path guard"`

### Task 3: Live-file snapshot + sharded full run

- [ ] **Step 1:** write `scripts/snapshot_live_state.py` output to scratchpad (size+mtime of `vector_memory.db`, `data/*.db`, `post_jobs.db`, `content_jobs.db`, `email.db`) — run before/after.
- [ ] **Step 2:** run the sharded suite (batches of 25 files, `-m "not requires_ollama"`, `--timeout=120`).
- [ ] **Step 3:** compare snapshots; any file that changed is investigated (live loop vs test); add store to Task 1 if a test wrote it.
- [ ] **Step 4:** record failures vs the Task 90 baseline; fix or report (no assertion weakening).
- [ ] **Step 5:** `git commit` fixes; update spec/report.
