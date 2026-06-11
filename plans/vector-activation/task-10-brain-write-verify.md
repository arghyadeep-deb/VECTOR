# Task 10 — Verify autonomous brain writes

- **Depends on:** Task 08 (needs ~24h of always-on)
- **Who:** me
- **Effort:** ~15 min after the first full day

## Objective

Proof that the running loop writes to the brain vault and memory without help:
2AM reflect journal, nightly 04:00 self-check, episodic growth.

## Implementation

After the first overnight run, check:
- vault: new note under Reflections/Journals dated today
- `data/` self-check log clean (or loud nudge fired)
- `sqlite episodic_memory` row count grew vs yesterday
- governor log shows zero "no_agents" dispatches

## Demo

Open the vault in Obsidian; today's auto-journal is there.

## Acceptance

- [ ] DailyReviewer note written at ~02:00
- [ ] Nightly self-check ran (syntax+smoke) and reported clean
- [ ] Episodic count increased; no no_agents in governor log
