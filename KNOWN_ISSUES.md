# VECTOR — Known Issues & Remaining Work
> Updated: 2026-05-16 after full production audit + all absorptions complete.
> Status: ✅ Resolved · ⚠️ Needs action · ❌ Not built (Year 2)

---

## 1. DEPLOYMENT (code complete, not yet live)

| Item | Action needed |
|------|--------------|
| ⚠️ Fly.io brain server | `cd cloud/brain_server && fly launch && fly deploy` |
| ⚠️ Cloudflare Worker | `cd api && wrangler deploy` |
| ⚠️ Phone Termux node | Run `phone_node/setup.sh` on Android |
| ⚠️ Supabase cloud DB | Create project, run migrations from `core/memory/` |

---

## 2. VOICE (code complete, assets missing)

| Item | Action needed |
|------|--------------|
| ⚠️ Kokoro TTS model | `pip install kokoro` + download model weights (~300MB) |
| ⚠️ "Hey VECTOR" wake word | Record 10 samples → openWakeWord custom training |
| ⚠️ Whisper large-v3 | Currently using base model — `whisper.load_model("large-v3")` for prod |

---

## 3. OPTIONAL LIBRARIES (graceful fallbacks active)

| Library | Effect without it | Install |
|---------|-------------------|---------|
| ⚠️ `face-recognition` + `mediapipe` | Camera returns neutral values | `pip install face-recognition mediapipe` |
| ⚠️ `pynvml` | GPU energy monitoring returns zeros | `pip install nvidia-ml-py` |
| ⚠️ SQLCipher | SQLite unencrypted (plain sqlite3) | `pip install sqlcipher3` |

---

## 4. UNBUILT COMPONENTS

| Component | Status | Notes |
|-----------|--------|-------|
| ❌ `dashboard/src/` (Next.js) | Not built | Monitoring dashboard — not blocking |
| ❌ `data_analytics/` district | Scaffolded, 0 agents | Low priority |
| ❌ `devops/` district | Scaffolded, 0 agents | Low priority |

---

## 5. VECTOR GAPS (Year 2)

Per `architecture.md` — explicitly planned for after MVP:

| Gap | Module | When |
|----|--------|------|
| Gap 4 | `core/brain/counterfactual.py` | After MVP — learns from rejected decisions |
| Gap 6 | `core/brain/causal_graph.py` | Year 2 — causal reasoning |
| Gap 7 | `core/brain/person_model.py` | Year 2 — theory of mind per person |
| Gap 8 | `core/brain/meta_cognition.py` | Year 2 — monthly bias detection |

---

## 6. CUSTOM LLM (Month 2+)

| Milestone | When |
|-----------|------|
| LoRA fine-tune Qwen3 4B on reasoning chains | Month 2 (RTX 5070 Ti, 1-2h) |
| vector-chairman in Ollama | Month 2 (replaces cloud model as chairman) |
| Pre-train OpenMythos 200M from scratch | Month 4-6 (weekend on Legion) |
| Full custom LLM on VECTOR reasoning chains | Year 2 |

---

## EVERYTHING ELSE IS RESOLVED

| What was fixed | When |
|----------------|------|
| ✅ 7 production bugs (epistemic NameError, _get_gateway, mcp_server methods, swarm agent_types, upi_parser) | 2026-05-16 |
| ✅ 1,199 silent exception swallows → loguru logging | 2026-05-16 |
| ✅ All `asyncio.CancelledError` properly re-raised | 2026-05-16 |
| ✅ 210 broken import paths fixed | 2026-05-15 |
| ✅ Zero hermes/ruflo/openjarvis/Jarvis/NousResearch traces in code | 2026-05-16 |
| ✅ Zero stubs in core/ + agents/ (ABC files excluded) | 2026-05-16 |
| ✅ 38/38 smoke tests passing | 2026-05-16 |
| ✅ 51/51 integration checks passing | 2026-05-16 |
| ✅ ToolCallGuardrails wired into run_agent.py | 2026-05-16 |
| ✅ ReasoningBank wired into decision_engine (Rule 8) | 2026-05-16 |
| ✅ MoERouter wired as Layer 0 in GNNRouter | 2026-05-16 |
| ✅ Kanban tools registered in MCP server | 2026-05-16 |
| ✅ curator.py (1749L) absorbed + wired into vector_cli | 2026-05-16 |
| ✅ LSP client/manager/protocol absorbed | 2026-05-16 |
| ✅ PPO, SARSA, Q-Learning added to neural_training.py | 2026-05-16 |
| ✅ FlashAttention + MoERouter + ReasoningBank absorbed from ruflo | 2026-05-16 |
| ✅ 282 ruflo SKILL.md files in brain/.claude/skills/ | 2026-05-16 |
