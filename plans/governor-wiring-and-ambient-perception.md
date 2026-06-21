# Governor Wiring + Ambient Perception — Execution Spec

**Author:** Opus (planning) · **Executor:** Sonnet · **Date:** 2026-06-21
**Goal:** Close the two remaining pre-Phase-4 gaps from the 2026-06-21 audit. Security bypasses (4/4) are already DONE. Phase 4 (dead-code deletion) stays gated until these + the soak are green.

**Rules:** TDD per task (failing test → fix → pass → commit). Don't touch the running soak (edits land on disk, go live at next restart). DB via `core.memory.episodic.get_db_connection()` only. Never delete code (owner rule: wire-the-useful, delete only genuinely-dead, last).

---

## PART A — Governor reachability (the audit's #1 finding)

Audit: ~30 real agent classes exist in district folders but have **zero `config/agent_manifest.yaml` entries**, so the governor can't reach them; worse, it could pick a type-blind agent and fake-succeed (+50 HP). 7 agents were registered earlier (manifest 76→83); ~30 remain (coding 5/24, etc.).

### Task A.1: Enumerate the gap (do first — defines the work)
- [ ] Create `scripts/manifest_gap.py`: for each `districts/*/`, list every `class *(AgentBase)` (or class with a `run`/`async run` method) and diff against entries in `config/agent_manifest.yaml`. Emit `docs/manifest_gap.md`: per district = registered / unregistered-real-agents.
- [ ] Run it. Commit the report. This is the authoritative list (don't trust "~30").

### Task A.2 (repeat per unregistered agent): register + verify
For EACH unregistered real agent class:
- [ ] Confirm it instantiates with **zero required args** (`ManifestLoader.instantiate_all()` calls `cls()`). If `__init__` needs args → adapter or default them.
- [ ] **Verify `run(task)` branches on `task["type"]`** — NOT a `stock_analyst`-style "ignores params, returns one hardcoded thing". If it doesn't branch → that's a second-layer fix (make it dispatch on type) before registering, else it'll fake-succeed.
- [ ] Add a manifest entry: name, class import path, model, description, and **accurate `capabilities`** matching the real governor task types (`core/city/governor.py` route table) that should land there.
- [ ] Test: `governor.dispatch({"type": <route>, ...})` selects THIS agent (capability-aware select, already built at `governor.py:1056`) and its real `run` executes. Commit per district.

### Task A.3: Close the capability-fallback residual
- [ ] At `governor.py:1060` — `max(capable or agents, ...)` still HP-picks a **non-capable** agent when none declare the capability, which can fake-succeed + earn HP. Fix: if `capable` is empty, do NOT award HP for a generic-agent run; return `{"status":"no_capable_agent","district":...}` (honest miss) OR run but tag `capability_match=False` and skip the +50. Decide with owner; default to the honest-miss to protect the HP/Darwinian signal.
- [ ] Test: a task type with no capable agent in the district returns the honest miss, no HP awarded.

### Task A.4: predictive_analytics (genuinely broken)
- [ ] Its only AgentBase class has **no `run()`**; the district has zero dispatchable agents. Design decision (surface to owner): compose its 4 plain helper classes into one dispatchable `PredictiveAnalyticsAgent.run(task)` that branches on type, then register. NOT a YAML-only fix.

---

## PART B — Ambient perception (the "always-on JARVIS" gap)

Audit: screen + camera-presence reach `context_engine`, but wearable, ADB-phone, fatigue, and the wake word do NOT.

### Task B.1: Fatigue score actually reaches context_engine
- [ ] `core/sensing/health_monitor.py` computes real EAR fatigue, but `context_engine` reads a `0.0` default (despite its docstring). Trace where `_sense_tick` / `context_engine` reads fatigue and wire the real `health_monitor` value into the health domain of session hydration.
- [ ] Test: a mocked fatigue score propagates into `ContextEngine` world-state (not 0.0).

### Task B.2: ADB-phone observe source into the loop
- [ ] `core/control/phone_controller.py` (ADB bridge) exists but isn't an observe source. Add a poll in `_observe_tick`/`_sense_tick` (or a `phone_loop` extension) that pulls notifications/state via ADB → `context_engine`. `asyncio.to_thread` (ADB is blocking). Graceful when no device.
- [ ] Test: mocked ADB output lands in context. Commit.

### Task B.3: Wearable observe source
- [ ] Architecture names wearable (HR/sleep/steps) as a core observe source; zero wiring exists. If owner has no wearable integration yet, document it as owner-hardware-dependent and stub the seam (a `wearable_poll_cycle` that no-ops gracefully) rather than leave it absent. Confirm scope with owner.

### Task B.4: Finish "Hey VECTOR" wake word
- [ ] 15 samples were recorded; `core/voice/wake_word.py` still falls back to 2-second Whisper-chunk transcription (not real-time detection). Owner step: train the openWakeWord ONNX from the samples. Code step: load the trained ONNX in `wake_word.py` and switch off the Whisper-chunk fallback when present. Document the owner training command; wire the load path.

---

## Done = these green, then run the soak's final check, then Phase 4 may proceed.
Verification each part: `PYTHONUTF8=1 pytest <new tests>` + `python scripts/integration_check.py` + `python scripts/smoke_test.py`.
