# VectorCode 100% Absorption — Master Plan

**Sources:**
- `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\VectorCode_vectorcode\repo` (VectorCode, Python)
- `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\vectorcode_vectorcode\repo` (VectorCode, TypeScript)

**Target:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode\python\vectorcode\`

**Executor:** Claude Sonnet 4.6 (this plan is a handoff; each wave is a separate session).

---

## Scope (measured)

| Source | Files | Lines | Bytes |
|--------|-------|-------|-------|
| VectorCode `*.py` (excl tests) | ~390 | **261,041** | ~11 MB |
| VectorCode `run_agent.py` alone | 1 | 12,229 | 675 KB |
| VectorCode `tests/` | 821 | ~100k | 11 MB |
| VectorCode `vectorcode/src/` (TS/JS) | 276 | ~20,376 | 926 KB |
| VectorCode `v3/` (TS) | 1230 | ~100k+ | 18 MB |
| VectorCode `v2/` (TS+MD) | 993+1115 | — | 25 MB |

**Currently absorbed:** ~30,000 Python lines (~12% by line count; ~45% by feature count per last assessment).

---

## Execution model

Work is split into **8 waves**, each a standalone session for Sonnet 4.6. Dependencies:

```
Wave 0 (runtime foundation)
    ↓
Wave 1 (tools) ── Wave 2 (agent subsystems)
    ↓                     ↓
Wave 3 (gateway + CLI) ←──┘
    ↓
Wave 4 (plugins, cron, acp, skills_hub, voice, curses_ui)
    ↓
Wave 5 (VectorCode TS → Python)   [can run parallel to Wave 1–4 after Wave 0]
    ↓
Wave 6 (tests + CI)
    ↓
Wave 7 (packaging + release)
```

Each wave has its own plan file (`01-wave-0.md` … `07-wave-7.md`) with:
- Exact source→target file mappings
- Line counts per file
- Acceptance tests
- Rollback procedure

---

## Wave summary

| # | Wave | Source files | Target files | Est lines to port |
|---|------|-------------:|-------------:|------------------:|
| 0 | Runtime foundation | 8 | 12 | 15,000 |
| 1 | Tool subsystem | 82 | 80 | 42,000 |
| 2 | Agent subsystems | 52 | 45 | 35,000 |
| 3 | Gateway + CLI | 53 + 58 | 90 | 80,000 |
| 4 | Extensibility (plugins/cron/acp/skills_hub/voice) | 60 | 55 | 15,000 |
| 5 | VectorCode TS → Python | ~500 TS | ~150 py | 30,000 |
| 6 | Tests + CI | 821 | 800 | ~40,000 |
| 7 | Packaging | — | 6 | 500 |
| **Total** | | **~1,600** | **~1,240** | **~257,500** |

---

## Sonnet 4.6 execution protocol (per wave)

Each wave session starts with this prompt template:

```
You are porting VectorCode/VectorCode → VectorCode. Read these first, in order:
1. vectorcode/docs/absorption/00-MASTER-PLAN.md
2. vectorcode/docs/absorption/NN-wave-N.md  (the wave assigned)
3. vectorcode/docs/vectorcode_specs.md
4. Any files listed under "Read before coding" in the wave plan.

Then execute the wave top-to-bottom. Stop at each "CHECKPOINT" and run
the acceptance test before proceeding. If a checkpoint fails, diagnose
root cause before patching.

Hard rules:
- Never delete a VectorCode file without confirming it's truly dead code.
- Never touch files outside vectorcode/python/vectorcode/ without asking.
- Every ported file must have a matching test in tests/.
- Every ported file must keep a header comment: # Ported from <source_path>
- All model calls route through providers/ + transports/ (no direct httpx
  to provider APIs in tools or agent code).
- Preserve VectorCode behavior exactly where possible. Improvements go in
  a separate commit after the base port passes tests.
```

---

## Invariants across all waves

1. **Package layout is frozen.** `vectorcode/python/vectorcode/` is the root. All new modules land here.
2. **No TypeScript at runtime.** `vectorcode/packages/` TS scaffolding is archived; final product is Python.
3. **Ollama-first, cloud-optional.** Every provider path must degrade gracefully when cloud creds are missing.
4. **Permission gateway is mandatory.** Every tool call routes through `permissions/` before execution.
5. **No new dependencies** without updating `requirements.txt` AND `pyproject.toml` AND `docs/absorption/deps.md`.
6. **All file writes are atomic.** Use `utils.atomic_json_write()` pattern from VectorCode.
7. **No surrogates in JSON.** Sanitize with `_sanitize_surrogates()` before serialize.
8. **Subagents inherit iteration budget** from parent; never reset to fresh 90.

---

## Definition of Done (100% absorption)

- [ ] `vector run "<task>"` executes a full think→act→observe loop with real tool calls
- [ ] All 82 VectorCode tools callable from the loop (with matching schemas)
- [ ] All 58 VectorCode CLI commands available under `vector <cmd>`
- [ ] HTTP gateway serves `/run`, `/stream`, `/status` with auth
- [ ] Plugin system discovers and loads user plugins from `~/.vectorcode/plugins/`
- [ ] MCP client connects to external MCP servers; tools surface in `/tools`
- [ ] 143 VectorCode skills + VectorCode built-in skills both discoverable
- [ ] SPARC workflow methodology (VectorCode v2) invokable as a slash command
- [ ] All 821 VectorCode tests + VectorCode tests ported and passing in pytest
- [ ] `pip install vectorcode` works from a fresh venv
- [ ] `docker build` produces a runnable image
- [ ] README + API docs complete; CI green

---

## Wave files (to be written next)

- `01-wave-0-runtime.md` — Agent runtime foundation
- `02-wave-1-tools.md` — Tool subsystem (82 files)
- `03-wave-2-agent.md` — Agent subsystems
- `04-wave-3-gateway-cli.md` — Gateway + CLI
- `05-wave-4-extensibility.md` — Plugins, cron, ACP, voice, TUI
- `06-wave-5-vectorcode.md` — VectorCode TS → Python port
- `07-wave-6-tests.md` — Test port + CI
- `08-wave-7-packaging.md` — pip / docker / release

Status of each wave plan: `[ ] not written` | `[x] ready` | `[RUN] in progress` | `[DONE] complete`

| Wave | Plan file | Status |
|------|-----------|:------:|
| 0 | 01-wave-0-runtime.md | [x] ready |
| 1 | 02-wave-1-tools.md | [x] ready |
| 2 | 03-wave-2-agent.md | [x] ready |
| 3 | 04-wave-3-gateway-cli.md | [x] ready |
| 4 | 05-wave-4-extensibility.md | [x] ready |
| 5 | 06-wave-5-vectorcode.md | [x] ready |
| 6 | 07-wave-6-tests.md | [x] ready |
| 7 | 08-wave-7-packaging.md | [x] ready |
