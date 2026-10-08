# OD-38 Filesystem Confinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure production-created `FileReadTool` and `FileWriteTool` instances are confined to the VECTOR repository and runtime data roots without changing generic factory constructor arguments.

**Architecture:** Reuse `core.runtime_paths` as the source of both allowed roots, exposing its established repository-root value through a public accessor. In the MCP and orchestrator builders, apply a narrow post-construction configuration only to real file read/write tool instances; all other tools retain their existing zero-argument construction behavior.

**Tech Stack:** Python 3.12, pathlib, pytest, VectorCode `ToolRegistry`/`BaseTool`.

---

### Task 1: Add failing real-call-site regression coverage

**Files:**
- Create: `tests/test_file_tools_real_confinement_injection.py`

- [x] Exercise `MCPServer._auto_discover_tools()` and `QueryOrchestrator._build_tools()` with the real file-tool registrations.
- [x] Assert each built file tool accepts the resolved repository root and runtime data root and rejects a path outside both roots.
- [x] Add a sentinel tool whose constructor accepts no filesystem arguments and assert both generic builder paths still retain it.
- [x] Run the new tests and confirm the confinement assertions fail because `_allowed_dirs` is empty.

### Task 2: Expose the established repository root

**Files:**
- Modify: `core/runtime_paths.py`

- [x] Add `get_project_root() -> Path` returning the existing resolved `_PROJECT_ROOT` constant.
- [x] Keep `get_data_root()` behavior unchanged.

### Task 3: Inject confinement at both production builders

**Files:**
- Modify: `vectorcode/src/vc_mcp/server.py`
- Modify: `vectorcode/src/vc_system/orchestrator.py`

- [x] Import the real `FileReadTool` and `FileWriteTool` classes for `isinstance` checks.
- [x] After construction, set `_allowed_dirs` only for those two classes to `[get_project_root().resolve(), get_data_root().resolve()]`.
- [x] Cover both registry-created tools and the MCP server's pre-existing direct `FileReadTool` construction.
- [x] Do not pass new keyword arguments through either generic factory.

### Task 4: Remove stale unresolved-decision comments

**Files:**
- Modify: `vectorcode/src/vc_tools/file_read.py`
- Modify: `vectorcode/src/vc_tools/file_write.py`

- [x] Replace the `FLAGGED` comments with concise documentation that production builders inject the enforced roots while direct callers may still supply explicit roots.

### Task 5: Verify behavior and regressions

**Files:**
- Test: `tests/test_file_tools_real_confinement_injection.py`

- [x] Run the new regression tests and confirm they pass.
- [x] Run `python -m py_compile` on every touched Python file.
- [x] Run existing MCP, orchestrator, file-tool, runtime-path, and registry/factory test slices and record exact counts.
- [x] Inspect `git diff` and `git status`; confirm `vectorcode/src/vc_tools/apply_patch.py` is untouched and do not commit.
