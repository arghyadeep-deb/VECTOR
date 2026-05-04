# VECTOR — Build Progress Tracker

**Owner:** Arghyadeep Deb | KIIT CSE 2023-27  
**Hardware:** Legion Pro 5 | RTX 5070 Ti 12GB | 32GB RAM  
**Repo:** https://github.com/arghyadeep-deb/VECTOR  
**Last updated:** 2026-05-05

---

## Overall Status

| Phase | Description | Status | Gate |
|-------|-------------|--------|------|
| T1 | Foundation — config, memory, API server | ✅ DONE | ✅ PASS |
| T2 | Intelligence Stack — loop, goals, decisions | ✅ DONE | ✅ PASS |
| T3 | Voice Pipeline — STT, TTS, wake word | ❌ TODO | ❌ PENDING |
| T4 | Sensing & Control — camera, ADB, screen | ❌ TODO | ❌ PENDING |
| T5 | Phase 1 Districts — coding, calendar, security | ❌ TODO | ❌ PENDING |
| T6 | Memory + Research + Cloud | ❌ TODO | ❌ PENDING |
| T7 | Final Integration | ❌ TODO | ❌ PENDING |

---

## T1 — Day 1: Foundation ✅ COMPLETE

| Module | File | Smoke Test |
|--------|------|------------|
| Config | `core/config.py` | ✅ |
| Episodic Memory | `core/memory/episodic.py` | ✅ (FTS5 + 6 tables) |
| FastAPI Server | `core/main.py` | ✅ (6 routes) |
| Agent Base | `core/city/agent_base.py` | ✅ (HP + ghost) |
| Permission Gateway | `core/loop/permission_gateway.py` | ✅ (GREEN/YELLOW/RED) |
| Multi-DB Manager | `core/memory/multi_db_manager.py` | ⚠️ stub |
| run_vector.py | `run_vector.py` | ⚠️ stub |

**Day 1 Gate:** `python run_vector.py` → JSON response + SQLite row ✅

---

## T2 — Day 2: Intelligence Stack ✅ COMPLETE

| Module | File | Smoke Test | Key Capability |
|--------|------|------------|----------------|
| Context Engine | `core/loop/context_engine.py` | ✅ (11 domains, 520 chars) | RULE 1 — session_hydration_prompt() |
| Goal System | `core/brain/goal_system.py` | ✅ (6 goals, 5 actions) | RULE 6 — 3-horizon goal management |
| Decision Engine | `core/loop/decision_engine.py` | ✅ (winner score=0.79) | 5-factor scoring (30/25/20/15/10) |
| Policy Memory | `core/memory/policy.py` | ✅ (default=0.5, 3 updates=0.8) | RULE 7 — get_score() + update_from_outcome() |
| Reasoning Memory | `core/memory/reasoning_memory.py` | ✅ (chains=7, avg=0.771) | RULE 8 — reasoning chains → training data |
| Agent Registry | `core/city/agent_registry.py` | ✅ (3 registered, 1 ghost) | RULE 9 — Darwinism + ghost memory |
| Governor | `core/city/governor.py` | ✅ (route=coding, dispatch=stub) | Task routing + HP wiring |
| Autonomous Loop | `core/loop/autonomous_loop.py` | ✅ (4 ticks in 2s) | RULE 2 — never stops, chunked sleeps |

**Day 2 Gate:** debug mode → 4 candidates + scores + policy table rows ✅

---

## T3 — Day 3: Voice Pipeline ❌ PENDING

| Module | File | Status | Notes |
|--------|------|--------|-------|
| STT | `core/voice/stt.py` | ❌ stub | Whisper local, audio never leaves device (RULE 5) |
| TTS | `core/voice/tts.py` | ❌ stub | Kokoro primary, pyttsx3 fallback |
| Wake Word | `core/voice/wake_word.py` | ❌ stub | openwakeword, "Hey VECTOR" trigger |
| Ambient Listener | `core/voice/ambient_listener.py` | ❌ stub | Always-on background thread |

**Day 3 Gate:** "Hey VECTOR" → WAKE → TRANSCRIBE → THINK → SPEAK ❌

---

## T4 — Day 4: Sensing & Control ❌ PENDING

| Module | File | Status |
|--------|------|--------|
| Camera / Face ID | `core/sensing/camera.py` | ❌ stub |
| Screen Capture | `core/sensing/screen.py` | ❌ stub |
| Health Monitor | `core/sensing/health.py` | ❌ stub (fatigue, eye aspect ratio) |
| PC Control | `core/control/pc.py` | ❌ stub (pyautogui) |
| ADB (Android) | `core/control/adb.py` | ❌ stub |

**Day 4 Gate:** Face ID + cursor control + ADB screenshot ❌

---

## T5 — Day 5: Phase 1 Districts ❌ PENDING

| District | Agents | Status |
|----------|--------|--------|
| `coding/` | GitBot, CodeReviewer, BugHunter, ArchitectBot | ❌ stub |
| `time_calendar/` | KIITScraper, DeadlineManager | ❌ stub |
| `security/` | ThreatScout, MalwareHunter, NodeGuard | ❌ stub |
| `communications/` | Hermes + Kimi K2.6 adapter | ❌ stub |

**Day 5 Gate:** GmailAgent reads + KIIT schedule + auto-commit ❌

---

## T6 — Day 6: Memory + Research + Cloud ❌ PENDING

| Module | Status |
|--------|--------|
| `agents/districts/memory_curator/` | ❌ stub (LightRAG, ConsolidationBot) |
| `agents/districts/research/` | ❌ stub (OpenCLI, PaperReader) |
| `cloud/` | ❌ stub (Fly.io, Cloudflare Workers) |
| `api/` | ❌ stub |
| `dashboard/` | ❌ stub |

**Day 6 Gate:** fly.dev/status 200 + ambient running + Obsidian note ❌

---

## T7 — Day 7: Final Integration ❌ PENDING

| Module | Status |
|--------|--------|
| `core/memory/obsidian_sync.py` | ❌ stub |
| `agents/districts/governance/llm_council.py` | ❌ stub |
| `phone_node/` | ❌ stub |

**Day 7 Gate:** all 4 end-to-end scenarios pass ❌

---

## Infrastructure ✅ COMPLETE

| Item | Status | Notes |
|------|--------|-------|
| `.claude/settings.json` | ✅ | Syntax-check hook on every file save |
| `.claude/skills/` (5 VECTOR skills) | ✅ | vector-test, commit, district, modelfile, antigravity |
| `.claude/skills/` (5 dev skills) | ✅ | ai-agents-architect, async-python, langgraph, rag-engineer, fastapi-pro |
| `.claude/commands/` | ✅ | feature-dev, code-review |
| `.github/workflows/ci.yml` | ✅ | Python 3.11, smoke tests, pytest |
| `.github/workflows/lint.yml` | ✅ | ruff on core/ and agents/ |
| `.agents/plugins/marketplace.json` | ✅ | Antigravity plugin config |
| Modelfiles (7) | ✅ | num_gpu 99, vector-focus ctx halved |

---

## Models Status

| Model | Base | Context | GPU Params | Rebuilt |
|-------|------|---------|------------|---------|
| vector-ambient | gemma4:e2b | 4096 | ✅ added | ❌ needs rebuild |
| vector-focus | gemma4:e4b | ~~32768~~ → 16384 | ✅ added | ❌ needs rebuild |
| vector-coder | qwen3:14b | 32768 | ✅ added | ❌ needs rebuild |
| vector-multilingual | qwen3:14b | 32768 | ✅ added | ❌ needs rebuild |
| vector-reasoning | qwen3:14b | 32768 | ✅ added | ❌ needs rebuild |
| vector-deep | gemma4:26b | 65536 | ✅ added | ❌ needs rebuild |
| vector-chairman | gemma4:31b | 32768 | ✅ added | ❌ needs rebuild |

**To rebuild all:**
```bash
ollama create vector-ambient -f modelfiles\vector-ambient.modelfile
ollama create vector-focus -f modelfiles\vector-focus.modelfile
ollama create vector-coder -f modelfiles\vector-coder.modelfile
ollama create vector-multilingual -f modelfiles\vector-multilingual.modelfile
ollama create vector-reasoning -f modelfiles\vector-reasoning.modelfile
ollama create vector-deep -f modelfiles\vector-deep.modelfile
ollama create vector-chairman -f modelfiles\vector-chairman.modelfile
```

---

## Immediate Next Steps (T3)

1. `core/voice/stt.py` — Whisper `base` model, local only
2. `core/voice/tts.py` — Kokoro (`bf_emma`, 0.85x speed = VECTOR voice)
3. `core/voice/wake_word.py` — openwakeword, trigger phrase "Hey VECTOR"
4. `core/voice/ambient_listener.py` — asyncio loop that bridges wake → STT → think
5. Rebuild modelfiles after completing voice
6. Test Day 3 gate: "Hey VECTOR" → full round-trip

---

## Commit Log (this project)

| Commit | Message | What |
|--------|---------|------|
| `2a2b034` | clean: remove venv and add gitignore | setup |
| `85b19c9` | Update architecture.md | docs |
| `cb6241c` | update | misc |
| `057c580` | [T2] complete intelligence stack + Claude Code infrastructure | **T1+T2 done** |
