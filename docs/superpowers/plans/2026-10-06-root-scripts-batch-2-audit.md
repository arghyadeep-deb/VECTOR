# Root Scripts Batch 2 Security and Correctness Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete a first-pass, line-by-line security and correctness audit of the 30 assigned root `scripts/` files, fix only proven narrow defects with regression tests, and document whether each script is live or an unreferenced one-off.

**Architecture:** Treat each script as an independent CLI or utility boundary. Read every source file in full, trace repository references before changing signatures, and classify findings by concrete runtime impact. For each genuine defect, use a test-first red/green cycle and the smallest local implementation change; record unresolved design or policy decisions without guessing.

**Tech Stack:** Python 3.12+, pytest, pathlib/tempfile/os.replace for safe filesystem operations, ripgrep for reference tracing, loguru where production logging is involved.

---

### Task 1: Establish scope and reference map

**Files:**
- Read: `scripts/cognitive_benchmark.py` through `scripts/langsmith_vector_eval.py` as enumerated in the owner request
- Read: `.github/workflows/**`, `scripts/**`, `docs/**`, `README.md`, `CONTRIBUTING.md`
- Create: working reference inventory in the audit notes for the final `docs/OPEN_ISSUES.md` entry

- [ ] **Step 1: Read every assigned file completely**

Record the CLI inputs, filesystem writes, subprocess calls, imports, exception paths, success criteria, and persistent-state behavior for all 30 files.

- [ ] **Step 2: Search exact filenames and module paths**

Run repository-wide `rg` searches excluding `.git`, then distinguish executable wiring from documentation/history, self-references, imports, and test-only references.

- [ ] **Step 3: Classify lifecycle status**

Mark each file as live/load-bearing, manually runnable but maintained, historical one-off, or unreferenced diagnostic. Preserve uncertainty explicitly when references do not prove scheduled execution.

### Task 2: Perform line-by-line security and correctness review

**Files:**
- Read: all 30 assigned `scripts/*.py` files
- Read as needed: imported production modules and existing tests needed to validate APIs and claimed checks

- [ ] **Step 1: Audit trust boundaries**

Check caller-controlled paths for confinement, subprocess operands for option injection and secret exposure, comparison operations for timing safety, and imports for same-name-tree ambiguity.

- [ ] **Step 2: Audit persistence and failure behavior**

Check persistent writes for atomic replacement, UTF-8 encoding, interrupted-write corruption, overwrite confirmation, and truthful error propagation.

- [ ] **Step 3: Audit verification claims**

Trace every PASS/success result in smoke, integration, audit, and evaluation scripts to evidence that the named behavior was actually exercised; identify skipped or swallowed failures that create phantom success.

- [ ] **Step 4: Audit recurring regression shapes**

Check for intentional concrete no-ops replaced by `NotImplementedError`, falsy-zero defaulting, banned production libraries, incorrect loguru exception usage, hardcoded secrets, and missing session hydration before LLM calls.

### Task 3: Fix each proven defect with TDD

**Files:**
- Modify only: affected files from the assigned `scripts/` list
- Create or modify: focused `tests/test_regression_scripts_*.py` files

- [ ] **Step 1: Write one focused failing regression test per defect**

Use real script functions and temporary directories/databases. Patch only external processes, hardware, network services, or environment boundaries when unavoidable; do not mock VECTOR permission, hydration, HP, or episodic-memory internals.

- [ ] **Step 2: Verify the test fails for the intended reason**

Run the exact pytest node and retain the failure reason in the audit evidence.

- [ ] **Step 3: Implement the smallest safe correction**

Keep public signatures stable unless reference tracing proves no callers and the correction requires a change. Use confined resolved paths, atomic temp-file writes with flush/fsync/replace, explicit UTF-8, `--` where supported, and non-falsy default checks according to the proven defect.

- [ ] **Step 4: Verify green and regressions**

Run each exact pytest node, then the complete new regression file and any existing directly related test module.

### Task 4: Record audit outcome and verify completion

**Files:**
- Modify: `docs/OPEN_ISSUES.md`
- Read: repository diff and all assigned files

- [ ] **Step 1: Re-read every assigned file and review the diff**

Confirm every line was covered, no unrelated file was changed, and each implementation change maps to a demonstrated defect and regression test.

- [ ] **Step 2: Run syntax and focused test verification**

Compile all assigned scripts, run all newly added regression tests, and run directly relevant pre-existing tests. Report dependency or environment skips separately from passes.

- [ ] **Step 3: Append the audit entry safely**

Immediately before editing, re-read the tail of `docs/OPEN_ISSUES.md`, derive the next available issue number, and append a dated entry containing fixed defects, proof tests, unresolved policy questions, and a 30-file live-versus-one-off table.

- [ ] **Step 4: Leave changes uncommitted**

Do not stage or commit. Report changed files, reasons, risks, exact verification output, and any files that remain deletion candidates.
