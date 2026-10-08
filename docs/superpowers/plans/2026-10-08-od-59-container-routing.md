# OD-59 Container Routing Implementation Plan

> **For agentic workers:** Execute this plan inline and leave all changes uncommitted, per the owner's instructions.

**Goal:** Route `VectorSandbox` code and shell execution through the existing `ContainerRunner` when a supported local runtime and `vector-sandbox:latest` image are available, preserving the current subprocess fallback.

**Architecture:** Add a cached, fail-safe Docker/Podman image probe and a one-time fallback warning. Use self-contained container argv for Python and shell execution, translate both supported container response shapes into `SandboxResult`, and deliberately keep `run_file` on the host because no mount allowlist is configured by default.

**Tech Stack:** Python 3.12+, asyncio, stdlib subprocess/shutil/functools, loguru, pytest.

---

### Task 1: Add regression tests first

**Files:**
- Create: `tests/test_vector_sandbox_container_routing.py`

- [ ] Test successful `run_code_safe` and `run_shell` routing, payload/env forwarding, non-zero results, protocol timeout translation, host fallback behavior, and one-time warning behavior.
- [ ] Mock `_container_runtime_available` and `ContainerRunner.run`; do not contact Docker.
- [ ] Run the new test file against the current implementation and confirm failures caused by absent routing.

### Task 2: Implement runtime detection and routing

**Files:**
- Modify: `core/sandbox/vector_sandbox.py`

- [ ] Add a cached Docker/Podman binary-and-image probe that captures all output and degrades to unavailable on every exception.
- [ ] Add one-time, reason-specific fallback warning state.
- [ ] Route self-contained Python and POSIX shell argv through `ContainerRunner.run` in `asyncio.to_thread`, forwarding the scrubbed environment.
- [ ] Translate normal and pre-exit error dictionaries to `SandboxResult`.
- [ ] Keep `run_file` on the existing subprocess implementation with a mount-policy comment.
- [ ] Update the class docstring to describe container isolation and the weaker fallback accurately.

### Task 3: Verify

**Files:**
- Verify: `core/sandbox/vector_sandbox.py`
- Verify: `tests/test_vector_sandbox_container_routing.py`

- [ ] Run the focused regression tests.
- [ ] Run `python -m py_compile` for every touched Python file.
- [ ] Run the requested full sandbox-related pytest selection and record exact results.
- [ ] Inspect the final diff and working-tree status; do not commit.

### Task 4: Prevent host environment leakage into containers

**Files:**
- Modify: `tests/test_vector_sandbox_container_routing.py`
- Modify: `core/sandbox/vector_sandbox.py`

- [ ] Add a regression test proving container execution receives an empty environment when `extra_env` is omitted, even when host-only variables are populated.
- [ ] Add coverage proving explicitly supplied environment keys, including a normally host-specific key such as `PATH`, are forwarded unchanged.
- [ ] Run the new regression test against the current implementation and confirm it fails because `_build_env()` injects host defaults.
- [ ] Move `_build_env(extra_env)` to the host-subprocess branch and pass a shallow copy of only `extra_env` to `_run_container()`.
- [ ] Confirm the existing real host-subprocess fallback tests remain unchanged and pass.
- [ ] Run `python -m py_compile` for both touched Python files and the complete focused pytest file; record exact results and do not commit.
