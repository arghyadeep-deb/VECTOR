---
name: vector-failure-archaeology
description: Load before investigating a problem in VECTOR that might already be settled, or before proposing a fix that might have already been tried and rejected. The chronicle of major investigations, dead ends, and reverts so no one re-fights a settled battle. Triggers: "has this been tried", "why was this done", "history of", "was this already fixed", "don't reinvent".
---

# VECTOR Failure Archaeology

The settled battles. Before you investigate or "fix" something, check whether
it's here. Each entry: symptom → root cause → status. Sourced from the project
memory index (`~/.claude/projects/.../memory/MEMORY.md` — each dated file is a
full investigation). Ground truth 2026-07-07.

## When NOT to use this skill
For live triage of a NEW break use `vector-debugging-playbook`. This skill is
the historical record; the playbook is the fast lookup.

## The chronicle (most recent first)

- **Wake-word recall wall (2026-07-04→07):** synthetic piper-TTS voices (even
  904-speaker libritts) don't transfer to the OWNER's real voice/mic. Best
  recall ~13% (2/15 real clips fire). Voice diversity DID fix false-triggering
  (silence 0.97→0.01). ROOT: need owner's real recordings; synthetic-only is
  insufficient. STATUS: pipeline done + reusable, blocked on owner voice data.
  Full 17GB ACAV negatives would NOT help (problem is recall, not false-pos).

- **Local-only video (2026-07-04):** deleted paid MuAPI (Kling/200+ cloud) +
  RunwayML/Pika stubs; rewrote generative_studio to Wan2GP+sd.cpp local; catalog
  200+ cloud→8 free local. STATUS: done; needs Wan2GP/ComfyUI servers running.

- **Gemini zero free quota (2026-07-03):** owner key has `free_tier limit=0` on
  gemini-2.0-flash / 2.5-pro. STATUS: catalog repointed to 2.5-flash/flash-lite.

- **Multi-model routing 4 bugs (2026-07-02):** (1) .env keys invisible (key_pool
  only read os.environ); (2) local model names sent to cloud (404); (3) empty
  thinking-model responses counted as success; (4) complete() dropped kwargs.
  STATUS: all fixed; cloud-primary live.

- **vector-ambient is JSON-only:** its modelfile forces JSON output (empty
  content on plain prompts) → governor LLM classify always failed → everything
  routed to "research". STATUS: switched governor + voice gate to vector-focus
  with think=False. Do NOT use ambient for plain-text classification.

- **DB 2.3GB→131MB (2026-06-29):** context_budget dumped 56KB prompt offloads
  into FTS-indexed episodic (write-only dead weight); FTS DELETE only tombstones
  → had to DROP+CREATE. STATUS: fixed. git history also rewritten (>100MB blobs).

- **Windows cp1252 crash (2026-06-29):** emoji/non-ASCII prints crashed 246
  sites. STATUS: fixed at core/__init__ + bootstrap + 41-file codemod.

- **SQLCipher driver-class family (2026-06-11):** SQLCipher exceptions aren't
  sqlite3 subclasses; 5 modules opened encrypted DB with plain sqlite3; one
  playbook renamed the live DB. STATUS: all routed through get_db_connection().

- **Loop mode empty registry (2026-06-10):** bootstrap_agents only ran in API
  mode → loop dispatched to no agents. STATUS: run_loop() now bootstraps.

- **Absorbed OSS not proactive (2026-06-20):** 9 Hands wired+routable but 0 refs
  outside hands/ — cataloged but dormant. STATUS: plan exists; partial.

## Rejected / don't-retry
- Deleting absorbed OSS on "provenance" grounds — it's wired and routable; trace
  removal FAILED (853 fincept hits). Don't delete on reachability alone.
- Full 17GB ACAV negatives for wake word — hurts recall, won't help.
- vector-ambient for classification — structurally can't return plain text.

## Provenance and maintenance
The authoritative record is the memory index: read
`~/.claude/projects/C--Users-Arghyadeep-Desktop-V-E-C-T-O-R-V-E-C-T-O-R--Codebase/memory/MEMORY.md`
and the dated files it links. This skill summarizes; the memory files are the
detail. When you close a new investigation, add a memory file AND a row here.
