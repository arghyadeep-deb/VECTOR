# OD-37 LoRA Approval and Rollback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MANUAL LoRA fine-tuning explicitly owner-approvable while retaining a concrete pre-training adapter rollback state and adding no autonomous trigger.

**Architecture:** Add a LoRA-specific Permission Gateway branch to the synchronous distillation edit loop and leave every other MANUAL edit unchanged. Register the action as RED and owner-approval-only, then make the LoRA applier snapshot and restore its confined adapter artifact around real training.

**Tech Stack:** Python 3.12, asyncio bridge, pathlib/shutil/json, Pydantic models, VECTOR Permission Gateway, pytest.

---

### Task 1: Lock in approval behavior

**Files:**
- Create: `tests/test_vectorcode_learning_lora_approval.py`

- [ ] Add a test that records the exact `evaluate_external()` call for a MANUAL `LORA_FINETUNE` edit.
- [ ] Add a denial test whose applier raises if validation or application is reached and assert a blocked outcome.
- [ ] Add an approval test that proves validation and application are reached.
- [ ] Run the new tests and confirm they fail against the pre-fix implementation.

### Task 2: Lock in concrete rollback behavior

**Files:**
- Modify: `tests/test_vectorcode_learning_lora_approval.py`

- [ ] Create a real pre-existing adapter directory and sentinel file.
- [ ] Snapshot it, mutate it as training would, invoke rollback, and assert the original bytes are restored.
- [ ] Assert the rollback manifest describes the prior adapter and remains confined under `vector_home`.

### Task 3: Implement the approval boundary

**Files:**
- Modify: `core/config.py`
- Modify: `core/loop/permission_gateway.py`
- Modify: `vectorcode/src/learning/distillation/models.py`
- Modify: `vectorcode/src/learning/distillation/execute/loop.py`

- [ ] Register `lora_finetune_execute` in the RED list and owner-approval-only set.
- [ ] Add `blocked` to the edit outcome status contract.
- [ ] Inject or construct the shared gateway, fail closed on gateway errors or an active event loop, and return a blocked outcome on denial.
- [ ] Continue to registry lookup, validation, and application only after approval.

### Task 4: Implement snapshot and restoration

**Files:**
- Modify: `vectorcode/src/learning/distillation/execute/appliers/lora_stub.py`

- [ ] Before `_run_lora_finetune()`, create an idempotent confined rollback manifest and copy any pre-existing adapter.
- [ ] Restore the prior adapter automatically if training raises.
- [ ] Make `rollback()` restore the snapshot or remove an adapter that did not exist before training.
- [ ] Retain the snapshot after successful training for later benchmark acceptance/rejection.

### Task 5: Verify the focused surface

**Files:**
- Verify every Python file above and `tests/test_vectorcode_learning_lora_path_confinement.py`.

- [ ] Stash only implementation files while leaving the new tests present, run the new tests to prove pre-fix failure, then restore the implementation; document an index-lock denial if Git cannot stash.
- [ ] Run `python -m py_compile` on every touched Python file.
- [ ] Run the new regression file, the existing LoRA confinement file, and focused execute/applier tests found by exact search.
- [ ] Inspect the diff and status; do not stage or commit anything.

