# OD-56 Workflow Bash Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dormant compatibility `WorkflowEngine` bash action fail closed behind owner approval, filesystem confinement, an executable allowlist, and a minimal subprocess environment without wiring the engine into production.

**Architecture:** Keep the compatibility engine's public workflow/result contract, but isolate bash validation and execution inside the existing module. Resolve the command and cwd before approval, ask the real `PermissionGateway.evaluate_external()` entry point using a new RED action type, and execute only after approval; represent denials as a non-raising blocked workflow result.

**Tech Stack:** Python 3.12 stdlib (`asyncio`, `os`, `shlex`, `shutil`, `subprocess`, `sys`, `pathlib`), VECTOR `PermissionGateway`, `core.runtime_paths`, pytest.

---

### Task 1: Lock in fail-closed bash behavior

**Files:**
- Modify: `tests/test_vectorcode_agents_workflow_engine_phantom_success.py`

- [ ] Add focused async regression tests for gateway denial/no subprocess, approved output compatibility, outside-root cwd rejection, and non-allowlisted executable rejection.
- [ ] Run each new test against the pre-fix source and record its expected failure.

### Task 2: Implement the narrow security boundary

**Files:**
- Modify: `core/config.py`
- Modify: `vectorcode/src/agents/workflow_engine.py`

- [ ] Register `workflow_bash_execute` in `CONFIG["permission"]["red"]`.
- [ ] Add a fixed allowlist for Python, Git, and pytest executables and resolve the requested executable through the minimal PATH.
- [ ] Resolve a supplied relative cwd from `get_project_root()`, default absent cwd to that root, and reject resolved paths outside `get_project_root()` and `get_data_root()`.
- [ ] Build a fresh environment containing PATH plus Windows process-bootstrap variables only when present.
- [ ] Call `PermissionGateway.evaluate_external("workflow_bash_execute", params, "workflow_engine")`; if denied, return a blocked step/workflow result without invoking `subprocess.run`.
- [ ] Preserve successful stdout as the step result and preserve existing nonzero-exit failure behavior.

### Task 3: Verify the focused surface

**Files:**
- Verify: `core/config.py`
- Verify: `vectorcode/src/agents/workflow_engine.py`
- Verify: `tests/test_vectorcode_agents_workflow_engine_phantom_success.py`

- [ ] Run the two pre-existing test files that reference this compatibility engine.
- [ ] Run `python -m py_compile` for every touched Python file.
- [ ] Search imports/construction sites and confirm no production wiring was introduced.
- [ ] Inspect `git diff` and `git status --short`; leave all changes unstaged and do not commit.
