---
name: vector-debugging-playbook
description: Load when something in VECTOR is broken, crashing, hanging, or behaving wrong — a stack trace, an import error, a test failure, a silent no-op. Symptom→cause→fix table for VECTOR's real failure modes, so you don't re-derive settled diagnoses. Triggers: "error", "crash", "traceback", "failing", "hangs", "ImportError", "why is this broken", "debug".
---

# VECTOR Debugging Playbook

Symptom → likely cause → fix, for the failure modes that have actually cost time
on this project. Ground truth 2026-07-07. Always reproduce in isolation before
trusting a fix.

## When NOT to use this skill
For *rules* about what you may change use `vector-change-control`; for *how the
system is meant to work* use `vector-architecture-contract`.

## Triage table

| Symptom | Likely cause | Fix |
|---|---|---|
| `UnicodeEncodeError: 'charmap' codec can't encode` mid-print | Windows cp1252 stdout hit a non-ASCII char | `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` at top, or `PYTHONUTF8=1`; use ASCII in prints |
| `cannot import name 'BaseSettings' from partially initialized module 'pydantic_settings'` when running `python core/X.py` directly | Script-mode auto-prepends `core/` to sys.path → `core/email/` shadows stdlib `email` → circular import | Add the strip-own-dir guard (see `core/config.py` / `core/mcp_server.py` top): remove `_this_dir` from sys.path, ensure repo root present, BEFORE other imports |
| `ImportError: Lazy import of ... speechbrain...` during openwakeword import | torch 2.11 + torchvision register_fake frame-walk detonates speechbrain lazy modules | `import torchvision` FIRST, before openwakeword/openwakeword.train |
| SQLCipher DB errors not being caught by `except sqlite3.X` | SQLCipher driver classes are not sqlite3 subclasses | catch the SQLCipher driver's `IntegrityError`/`ProgrammingError`; go through `core.memory.episodic.get_db_connection()` |
| pytest hangs on Windows (asyncio) | default IOCP event loop | conftest sets `WindowsSelectorEventLoopPolicy` — ensure it's applied |
| `WinError 5 Access is denied` deleting test dirs | reused fixed `--basetemp`, read-only pytest shard dirs | unique basetemp per-run + read-only-aware rmtree; `test_tmp/` is ACL-locked → needs admin shell or reboot |
| DB file huge (GBs) | `context_budget.py` dumping prompt offloads into FTS `episodic_memory`; FTS DELETE only tombstones | DROP+CREATE the FTS table to reclaim; stop the write-only dumping |
| Cloud LLM call 404s with model name `vector-focus` | a local model name was sent to a cloud provider | `_model_for_provider` clamps — verify catalog/routing; cloud providers use their own default_model |
| Gemini always 429 on 2.0-flash / 2.5-pro | owner key has `free_tier limit=0` on those models | use gemini-2.5-flash / 2.5-flash-lite only (already fixed in catalog) |
| Governor routes every unknown task to "research" | vector-ambient modelfile is JSON-only (empty content on plain prompts) → LLM classify validation always failed | use `CONFIG["models"]["focus"]` with `think=False`, not ambient (fixed) |
| `ProviderClient.complete() unexpected kwarg` | complete() didn't forward kwargs | now forwards `**kwargs` to chat() |
| ONNX export "Graph output () does not exist" | openWakeWord `export_to_onnx` writes empty output name | export directly with `torch.onnx.export(..., output_names=["scores"], dynamo=False)` |
| Silent no-op / "no agents" in loop mode | agent registry empty (bootstrap only ran in API mode) | `run_loop()` must call `bootstrap_agents()`; smoke reports `agents_registered` |
| `.env` key not seen (e.g. GEMINI works but Gemini-only-in-.env missing) | .env only loaded when key_pool imported | now loaded at `core/__init__` (2026-07-04) via load_dotenv; existing env wins |

## The method (when it's not in the table)
1. Reproduce in isolation (minimal script, exact imports).
2. Read the FULL traceback bottom-up — the real cause is usually the deepest
   frame, not the top. (The speechbrain and pydantic bugs both hid there.)
3. For import crashes: bisect import order; heavy ML deps have load-order landmines.
4. For "it silently does nothing": check env flags (`VECTOR_*_LLM`), check the
   permission gateway didn't block, check the model returned empty content.
5. Verify the fix with the evidence gate (smoke 38 / integration 51 / pytest).
6. If it's a new class of bug, add a row here.

## Provenance and maintenance
Dated 2026-07-07 from project memory + lived debugging. Re-verify a specific
row by reproducing its symptom. Update rows as fixes land or regress.
