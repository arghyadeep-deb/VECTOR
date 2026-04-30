# 02 — Functional Requirements

## Classification
- **M** = Must Have (Phase 1)
- **S** = Should Have (Phase 2)
- **C** = Could Have (Phase 3)
- **W** = Won't Have (this version)

## Core Requirements

| ID | Pri | Requirement | Success Metric | Phase |
|----|-----|-------------|---------------|-------|
| FR-01 | M | Start from single command, run indefinitely without manual restart | `python run_vector.py` runs 72h+ without crash | 1 |
| FR-02 | M | Respond to voice within 3 seconds of wake word | Whisper→Claude→Kokoro latency < 3s on 50 tests | 1 |
| FR-03 | M | Persistent memory across sessions, restarts, hardware failures | All 3 shipped questions pass after laptop restart | 1 |
| FR-04 | M | Detect and alert attendance risk without being asked | Attendance < 75% → Pushover alert within 24h | 1 |
| FR-05 | M | Auto-commit code to GitHub with generated messages | git log shows VECTOR commits daily on active repos | 1 |
| FR-06 | M | All decisions route through permission gateway (GREEN/YELLOW/RED) | Zero direct LLM actions in audit log | 1 |
| FR-07 | M | Learn from outcomes — same mistake not repeated in same context | policy_memory shows reward updating after each action | 1 |
| FR-08 | M | All voice audio processed locally — never sent externally | Network monitor shows zero audio leaving localhost | 1 |
| FR-09 | M | Detect fatigue from camera, reduce task load when score > 7 | fatigue_score stored in context, visible in /status | 1 |
| FR-10 | M | Store all thought chains as training data for custom LLM | reasoning_chains shows is_training_data=1 on reward > 0.7 | 1 |
| FR-11 | S | Reply to WhatsApp/Telegram in Arghyadeep's voice | Hermes connected, style profiles active, reply matches | 2 |
| FR-12 | S | Ingest any video and update skill graph | Video URL → concepts in skill_memory within 5 min | 2 |
| FR-13 | S | Generate 50-100 page interview prep report | 10 sections + 34 Q&As in < 10 minutes | 2 |
| FR-14 | S | Scan nightly for SaaS opportunities | Reddit/HN at 3AM, Pushover brief by 7AM | 2 |
| FR-15 | C | Produce Instagram Reel from idea in < 10 minutes | Idea → SadTalker video → captions → upload-ready | 3 |
| FR-16 | C | NSE/BSE analysis on request | Stock query → fundamentals + technicals report | 3 |
| FR-17 | W | NEVER execute financial transactions autonomously | Hard-coded RED, no override possible, ever | all |

## Agent HP System Requirements

| ID | Requirement | Validation |
|----|-------------|------------|
| FR-18 | Every agent starts at 500 HP, max 1000 HP | `assert agent.health_points == 500` on init |
| FR-19 | Agent death at 0 HP preserves ghost memory before removal | Ghost memory readable from agent_history after death |
| FR-20 | New agent inherits ghost memory from previous generation | Generation N+1 has ghost_memory from generation N |
| FR-21 | Model allocation upgrades automatically when HP crosses 800 | `get_upgraded_model()` returns claude-sonnet above 800 |
| FR-22 | Only agents above 700 HP may vote in LLM Council | council.py rejects vote from agent HP < 700 |
| FR-23 | HP changes logged with reason, timestamp, agent ID | point_system.py writes to agent_history on every change |