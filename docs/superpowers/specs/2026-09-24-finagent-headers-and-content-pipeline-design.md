# vector_finagent headers (C) and content pipeline (D) — design (2026-09-24)

Owner direction (2026-09-24): this build is for personal use; keep vendored code and make it a proper,
working part of VECTOR. Guardrails unchanged: no deletions, no push/deploy, Permission Gateway tiers and
OWNER_APPROVAL_ONLY untouched, `.env` and live databases untouched.

## C. vector_finagent headers

**Problem.** 419 files carry
`# Copyright (c) 2024-2026 VECTOR. All rights reserved.` / `# Licensed under the MIT License.` /
`# https://github.com/Fincept-Corporation/VectorFinancialTerminal` (a rebranded upstream URL). The claim is
inaccurate for code derived from Fincept Terminal.

**Design.** Comment-only, mechanical, idempotent script (`scripts/normalize_finagent_headers.py`) replacing exactly
those three consecutive lines with:
```
# Derived from Fincept Terminal (Fincept Corporation) — see THIRD_PARTY_NOTICES.md.
# Adapted for VECTOR (owner's personal-use build).
```
Nothing else in any file changes; files are compiled (`py_compile`) before and after and the script aborts on any
syntax difference. Preserves each file's line endings. Re-running is a no-op.
**Test.** `tests/test_finagent_headers.py`: no file under `vector_finagent/` still contains the old three-line
block; a sample of files still compiles; running the script twice changes nothing.

## D. Content pipeline as a first-class feature

**Findings (verified 2026-09-24).**
1. `core/runtime/plans.py::build_wedge_content_plan()` (script → `schedule_post`) has **no production caller** —
   only tests. That is why the real `post_jobs.db` never received a real job.
2. `districts/growth/content_arm.py::_script()` calls `sg.generate(topic)` if it exists; `ScriptGenerator` has no
   `generate` (its methods are `generate_script`, now async), so ARM A narrates the bare topic string
   ("what VECTOR did today") instead of a script.
3. `recover_interrupted_jobs()` marks every stale render as `error` even when the finished MP4 was persisted
   to `renders/`.

**Design.**
1. **Planner job.** New cron job `job_content_plan` (daily, before the 09:00 publish job) in `core/loop/cron_jobs.py`:
   picks a topic (ContentArm's `_pick_well` topics — "what VECTOR did today" when real work exists, else a capability
   showcase — never invented claims), creates a plan with `build_wedge_content_plan()` and adds it to the `PlanStore`.
   The autonomous loop already picks up active plans; the `schedule_post` step creates a local `pending` post job
   (GREEN, already classified); the existing 09:00 `job_content_scheduler` publishes only after the owner approves
   (RED `content_publish`) — unchanged. A per-topic cooldown reuses the script cache (1 h) and
   `PostJobTracker.create()`'s own dedup, and the job skips when an active content plan already exists (no pile-up).
2. **ContentArm fix.** `_script` becomes `async` and awaits `ScriptGenerator().generate_script(topic)`, using its
   `content`; falls back to the brand line (not the bare topic) on failure.
3. **Resumable renders.** `recover_interrupted_jobs()` keeps status `error` but records
   `error='interrupted ... (render saved: <path>)'` when `video_path` exists on disk, and a new
   `list_resumable_jobs()` exposes them. **No automatic upload** — resuming stays an owner action through the
   existing gated upload path (publishing is owner-approved).
**Errors.** Every new job catches all exceptions and returns a status dict (the loop must never die).
**Tests.** Planner creates exactly one plan and a second call is a no-op while it is active; plan step 2 produces a
`pending` job in an isolated tracker; ContentArm narrates generated content; resumable-job listing; no code path
calls a publisher without the gateway (asserted by patching the gateway to deny and checking nothing publishes).

## Out of scope
Publishing credentials/account setup (owner), auto-resume of uploads, changes to gateway tiers.
