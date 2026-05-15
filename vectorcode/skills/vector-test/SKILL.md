<!-- VECTOR-INGESTED ASSET
  Source: .claude/skills/SKILL.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:55+00:00
-->

---
name: vector-test
description: Run the __main__ smoke test for a specific VECTOR module. Reports ✅ or ❌.
---

The user wants to test a VECTOR module. Run its `__main__` block and report the result.

## Steps

1. Identify the file to test. It may be passed as an argument (e.g., `/vector-test core/memory/episodic.py`) or implied from the current context (the most recently edited file).

2. Activate the virtual environment and run the module:
   ```bash
   cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
   .venv\Scripts\python.exe <file_path>
   ```

3. Report the output clearly:
   - If the output contains ✅: report success
   - If the output contains ❌ or shows an exception: show the error and suggest a fix
   - If the module is a stub (output contains 'status':'stub'): report it as stub and note what needs to be implemented

4. Do NOT run tests with mocks. The `__main__` block in every VECTOR file uses real SQLite / real connections. Let them run as-is.

## Example output
```
Running core/memory/episodic.py...
✅ episodic OK — 6 tables created, store/recall/chain tested
```
