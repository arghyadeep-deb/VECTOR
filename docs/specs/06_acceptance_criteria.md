# 06 — Acceptance Criteria

## The Shipped Definition

VECTOR Phase 1 is **shipped** when ALL THREE pass simultaneously:

| # | Question | How to Verify |
|---|----------|---------------|
| **1** | Did VECTOR do something useful today you did NOT ask it to do? | Check Pushover history. At least one proactive alert with no preceding user command. |
| **2** | Last week's mistake — is VECTOR still making it this week? | `SELECT action_type, avg_reward FROM policy_memory WHERE last_updated > 7 days ago`. Corrected actions show lower reward. |
| **3** | Laptop crashes right now — does VECTOR remember the last 3 days? | Kill all processes. Restart. Ask "What happened yesterday?" Response includes actual events. |

## Day-by-Day Gates

> Each gate must pass before proceeding. No exceptions.

| Day | Gate | Acceptance Test | Pass Command |
|-----|------|----------------|--------------|
| 1 | Foundation | FastAPI responds + Ollama text + SQLite row written | `curl -X POST localhost:8000/command -d '{"text":"Hello"}'` returns JSON. SQLite has ≥1 row. |
| 2 | Intelligence | 4 candidates logged + policy rows + chain stored | Debug log shows 4 candidate scores. `COUNT(policy_memory) > 0`. reasoning_chains has entry. |
| 3 | Voice | Full voice round-trip < 3 seconds | "Hey VECTOR what day is it" → terminal: WAKE→TRANSCRIBE→THINK→SPEAK in < 3s. |
| 4 | Sensing | Face ID + cursor moves + ADB screenshot | `identify_person()` = 'arghyadeep'. Cursor moves. `adb screencap > /tmp/t.png` exists. |
| 5 | Integrations | Gmail + KIIT + GitHub all pass | `read_unread()` returns list. `fetch_schedule()` returns classes. git log shows VECTOR commit. |
| 6 | Cloud | Fly.io + old phone + Obsidian | `curl fly.dev/status → 200`. Old phone shows ambient running. New `.md` in vault. |
| 7 | Shipped | All 3 shipped questions pass | Manual walkthrough. All 3 pass without manual intervention. |

## Component Acceptance Criteria

| Component | Acceptance Criteria | Measured By |
|-----------|--------------------|----|
| Autonomous Loop | 72h+ no restart. All 5 coroutines alive. Zero unhandled exceptions. | `/status` uptime_seconds after 72h |
| Session Hydration | Every LLM call has `hydration_injected=true`. No exceptions. | `grep 'hydration_injected=false' vector.log` = zero results |
| Decision Engine | Every decision has exactly 4 candidates logged. | `SELECT COUNT(*) WHERE json_array_length(steps) < 4` = 0 |
| RL Policy | After 7 days, ≥20 action types have updated avg_reward. | `SELECT COUNT(*) FROM policy_memory WHERE avg_reward != 0.5` ≥ 20 |
| Obsidian Sync | Writes daily. Watchdog ingests new files within 30s. | Add test.md → verify in episodic_memory within 30s |
| Hermes Comms | ≥3 platforms connected. Style profile correct. | WhatsApp+Telegram+Discord connected. Test reply matches. |
| Security Gateway | Zero actions without audit log entry. | `COUNT(audit_log)` = total actions executed |
| Memory Persistence | After restart: `recall('yesterday')` returns events. | Kill python. Restart. Test recall. Pass if events present. |

## Non-Functional Acceptance Criteria

| Metric | Target | Fail Condition |
|--------|--------|----------------|
| Voice latency | < 3s | ≥ 3s on 3+ consecutive tests |
| Loop tick | 0.5s ± 100ms | Any tick > 1 second |
| Memory write | < 100ms | Any write > 500ms |
| Policy lookup | < 50ms | Any lookup > 200ms |
| VRAM headroom | ≥ 1GB | Any OOM event |
| Monthly cost | ≤ ₹500 | Dashboard shows > ₹450 |
| Audit completeness | 100% | Any gap detected |
| Uptime | ≥ 95% over 7 days | < 95% = loop not recovering |