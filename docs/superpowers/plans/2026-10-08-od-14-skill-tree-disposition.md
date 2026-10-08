# OD-14 Skill Tree Disposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the obsolete `vectorcode/skills/` marketplace snapshot without breaking curated skill discovery or SPARC exports.

**Architecture:** Keep `vectorcode/src/skills/` as the only repository-shipped skill tree. Redirect the remaining agent discovery helper to that canonical tree, retain user-configured external skill support, and make the SPARC package re-export its real coordinator implementation.

**Tech Stack:** Python 3.12, pathlib, pytest, Git.

---

### Task 1: Preserve canonical shipped-skill discovery

**Files:**
- Modify: `vectorcode/src/agent/skill_utils.py`
- Modify: `tests/test_vectorcode_skills_and_home.py`

- [ ] Change `_shipped_skills_dir()` to resolve `vectorcode/src/skills/` and update its docstrings to describe the curated library.
- [ ] Update the regression fixture and assertions to require a shipped directory ending in `vectorcode/src/skills`, reject `vectorcode/skills`, and confirm the curated library remains non-empty.
- [ ] Run `python -m pytest tests/test_vectorcode_skills_and_home.py -v` and require zero failures.

### Task 2: Correct the SPARC package re-export

**Files:**
- Modify: `vectorcode/src/skills/builtin/sparc/__init__.py`

- [ ] Replace the shadow-tree import with `vectorcode.src.skills.builtin.sparc.coordinator` while preserving the real coordinator's existing async/sync signatures.
- [ ] Confirm no repository caller imports the four symbols from the package level.
- [ ] Run the requested package import checks and require zero failures.

### Task 3: Remove the obsolete marketplace snapshot

**Files:**
- Delete: `vectorcode/skills/` (all 15,576 tracked files)

- [ ] Run `git rm -r -- vectorcode/skills` so every deletion remains recoverable from Git history.
- [ ] Confirm no tracked files remain under `vectorcode/skills/` and no production Python import still targets `vectorcode.skills`.
- [ ] Record before/after tracked and physical file counts for the final report.

### Task 4: Verify the complete change

**Files:**
- Verify every created or modified Python file.

- [ ] Run `python -m py_compile vectorcode/src/agent/skill_utils.py vectorcode/src/skills/builtin/sparc/__init__.py tests/test_vectorcode_skills_and_home.py`.
- [ ] Run `python -c "import vectorcode.src.skills"`.
- [ ] Run `python -c "from vectorcode.src.skills.builtin.sparc import *"`.
- [ ] Run `python -m pytest tests/ -k "skill" -v` and report exact pass/fail/skip/deselect counts.
- [ ] Inspect `git status --short`, `git diff --stat`, and focused diffs; do not commit.
