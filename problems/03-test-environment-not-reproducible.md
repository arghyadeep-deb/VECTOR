# Problem 03 - Tests Do Not Collect In Current Environment

**Status: FIXED 2026-05-12 — pytest.ini updated with asyncio_mode=auto, testpaths=tests, norecursedirs excluding .venv/node_modules/__pycache__, filterwarnings suppressing DeprecationWarning/UserWarning/ResourceWarning.**

## Symptom

Running `pytest -q` failed during collection with:

```text
ModuleNotFoundError: No module named 'loguru'
```

`requirements.txt` does contain `loguru`, so the repo likely has the dependency
declared but the active Python environment is not installed from it.

## Why It Matters

Progress claims like `47/47 tests passing` are not meaningful unless a clean
local setup can reproduce them.

## Implemented Solution

Installed the minimal missing packages needed for local verification in the
active `python` environment:

- `loguru`
- `pydantic`
- `pydantic-settings`
- `pytest`
- `pytest-asyncio`
- `httpx`

Then restored the repo-pinned Pydantic core pair:

- `pydantic==2.13.3`
- `pydantic_core==2.46.3`

Added `pytest.ini` so generated temp folders and vendored/reference trees are
not collected as tests.

Verified:

- `python run_vector.py smoke` passes.
- Full suite: `154 passed, 30 warnings in 39.19s`.

## Remaining Work

- Create or activate a virtual environment.
- Run `pip install -r requirements.txt`.
- Consider adding a small `requirements-dev.txt` if test-only packages appear.
- Recheck the full suite after all direct `ollama.chat()` calls are migrated to
  `core.inference.ollama_safe`.
