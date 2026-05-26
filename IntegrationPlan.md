# VECTOR Integration Plan — Phase 2

**Scope:** Close every closable gap to JARVIS. Physical actuators are out of scope (hard cap).
**Current state:** ~58% local / ~68% with cloud LLM (per audit Tue 2026-05-26)
**Target after this plan:** ~85% local / ~92% with cloud LLM
**Estimated:** 22 focused execution sessions, ~3–5 days marathon
**Owner:** Arghyadeep Deb
**Started:** 2026-05-26
**Predecessor:** `ProductionFix.md` (1,363 tests passing baseline, v1.0-production tagged)

---

## The core problem this plan fixes

> **"The VECTOR Brain knows everything. It just forgot to tell the Avatar."**

The brain modules (PersonModel, CounterfactualMemory, MetaCognition, HypothesisEngine, SynthesisBridge, EpistemicTracker, CouncilBrain, SelfEvolve) all run and produce data, but their outputs are **observability-only** — they get logged in `_reflect_tick`, not consumed at decision time. The avatar speaks generically; the decision engine doesn't consult counterfactuals; the personality middleware doesn't query communication style; the permission gateway doesn't invoke Council for RED actions.

This plan wires brain → behavior so the system *acts* like one mind, not a stack of disconnected modules.

---

## Phase A — Brain×Avatar Wiring (8 sessions) — BIGGEST IMPACT

### Session A1: PersonModel → Personality middleware
**Goal:** Voice and LLM responses adapt to the addressed person's communication style.
- In `core/personality/middleware.py` `PersonalityLayer.inject()`, accept optional `person_id` parameter
- Call `PersonModel().infer_communication_style(person_id)` to get formality/verbosity/technicality/directness
- Translate style values into system-prompt phrasing rules (e.g. high formality → "Use professional register; avoid contractions")
- In `ProviderClient.chat(person_id=...)` thread the parameter through to `inject()`
- Update `autonomous_loop._handle_user_input()` to determine person_id from context (default = "owner")
- **Test:** `tests/integration/test_phase_a1_personmodel_voice.py` — given Alice with formal/technical style, response uses formal register; given Bob with casual style, response uses casual register.
- **Acceptance:** A/B test shows measurable difference in response style for two contrasting persons.

### Session A2: PersonModel → Context engine deepening
**Goal:** Session hydration includes per-person context, not just summary stats.
- In `core/loop/context_engine.py` `session_hydration_prompt()`, when `person_id` is in context, call:
  - `pm.get_model(person_id)` for full belief/preference/trust dump
  - `pm.predict_response(person_id, current_topic)` for anticipated stance
  - `pm.get_interaction_history(person_id, limit=5)` for recent thread
- Inject as structured block: "About Alice: trust=0.85, communication_style={formal,technical}, recent_topics=[..], expected_stance=receptive"
- Wrap with `core/engine/token_juice.compressor.reduce_text()` to keep prompt budget
- **Test:** `tests/integration/test_phase_a2_context_personmodel.py` — verifies prompt contains person-specific block when person_id set; absent when not.
- **Acceptance:** Hydration prompt for known person is meaningfully longer and contains beliefs/preferences from PersonModel.

### Session A3: CounterfactualMemory.should_avoid() → autonomous_loop._act_on
**Goal:** Stop repeating decisions that previously failed.
- In `core/loop/autonomous_loop._act_on(action)`, BEFORE governor dispatch:
  - Build proposal string: `f"{action.action_type} {action.params}"`
  - Call `CounterfactualMemory().should_avoid(proposal, threshold=0.7)`
  - If `(should_avoid, score, reason)` returns True with score > 0.7: log warning, store rejection event, return early with `{"status": "skipped", "reason": "counterfactual_avoid"}`
  - If 0.4 < score < 0.7: continue but inject the rejection-reason as additional context for the LLM to consider
- Plumb the avoid-decision back into reflect tick for `record_outcome()`
- **Test:** `tests/integration/test_phase_a3_counterfactual_act_on.py` — record a rejected proposal "delete logs", attempt similar action, verify it's blocked.
- **Acceptance:** Two repeated mistakes within similarity threshold are blocked from execution.

### Session A4: MetaCognition bias detection → decision_engine scoring
**Goal:** Detected biases reduce the score weight of biased candidates.
- In `core/loop/decision_engine.score_candidate()`, add a `bias_penalty` factor:
  - Call `MetaCognition().detect_bias(recent_reasoning_samples)` (cached 5 min)
  - For each detected bias type (overconfidence, recency, confirmation):
    - If candidate's reasoning matches bias profile (e.g. confidence > 0.85 with thin evidence → overconfidence)
    - Subtract `bias_penalty * weight` from score
- Add `bias_factor: -0.05` to the existing scoring formula (goal+conf+policy+urgency+timing-cost-bias)
- Persist bias detection results to SQLite for dashboard surfacing
- **Test:** `tests/integration/test_phase_a4_metacognition_decision.py` — synthetic sequence of overconfident decisions; verify next candidate with same profile is penalized.
- **Acceptance:** Decision engine score for a bias-matching candidate is 5–15% lower than baseline.

### Session A5: HypothesisEngine → proactive suggestion queue
**Goal:** Insights generated every 4h surface to the user, not just logs.
- Create `core/brain/suggestion_queue.py` (SQLite-backed: id, hypothesis, confidence, status, surfaced_at)
- Modify `core/brain/hypothesis_engine.HypothesisEngine.generate()` to enqueue every hypothesis with status="pending"
- In `autonomous_loop._reflect_tick`, drain top-3 confident pending hypotheses → publish `EventType.HYPOTHESIS_SURFACED` event
- Subscribe `districts/reflection/daily_reviewer.py` to that event → include in morning briefing
- Subscribe `core/api/routers/notifications.py` (create) → push to dashboard via WebSocket
- **Test:** `tests/integration/test_phase_a5_hypothesis_consumer.py` — generate 5 hypotheses, verify queue has 5 pending, verify event fires for top 3.
- **Acceptance:** Daily briefing contains "I noticed: X" lines from HypothesisEngine.

### Session A6: SynthesisBridge → morning narrative
**Goal:** Cross-domain pattern detection becomes part of the daily reflection narrative.
- In `districts/reflection/daily_reviewer.py.generate_briefing()`, add a "Cross-domain patterns" section
- Call `SynthesisBridge().get_recent_patterns(days=1)` to fetch last day's synthesis output
- Format each pattern as a one-line narrative ("Spending in Coding district correlates with energy drops on Mondays")
- Add to Obsidian sync output
- **Test:** `tests/integration/test_phase_a6_synthesis_briefing.py` — seed patterns, run briefing, verify text contains pattern descriptions.
- **Acceptance:** Morning briefing includes ≥1 cross-domain pattern when data available.

### Session A7: CouncilBrain → permission_gateway RED tier
**Goal:** Multi-model deliberation fires for high-stakes decisions instead of being dead code.
- Read `core/brain/council.py` to confirm API surface
- In `core/loop/permission_gateway._handle_red_tier()`, before HumanLayer/Queen consensus:
  - Call `CouncilBrain().deliberate(action_type, action.params, context=session_hydration)`
  - Council returns `{verdict: proceed|reject|defer, votes: [...], rationale: str}`
  - If `verdict == "proceed"` and confidence > 0.75 → continue without HumanLayer (auto-approve)
  - If `verdict == "reject"` → block with rationale logged
  - If `verdict == "defer"` → fall through to HumanLayer/Queen
- Persist all council deliberations to `data/council_log.jsonl`
- **Test:** `tests/integration/test_phase_a7_council_red_tier.py` — synthetic RED action, verify Council called, verifies all 3 verdict paths.
- **Acceptance:** RED-tier decisions log a Council deliberation entry every time.

### Session A8: EpistemicTracker SQLite persist + decision integration
**Goal:** Confidence decay survives restart and influences scoring.
- In `core/brain/epistemic_tracker.py`, add SQLite backend (`data/epistemic.db`):
  - Tables: `claims (id, claim, confidence, last_seen_at, decay_rate, source)`, `staleness_events`
  - `record_claim()`, `decay_all()`, `get_confidence(claim_id)`, `get_stale_claims(age_hours)`
- Replace in-memory dicts with DB-backed ops (keep API stable)
- In `core/loop/decision_engine.score_candidate()`, when scoring confidence, weight by epistemic confidence of supporting facts:
  - For each supporting claim, fetch `tracker.get_confidence(claim_id)`
  - Multiply candidate confidence by mean of supporting claim confidences
- **Test:** `tests/integration/test_phase_a8_epistemic_persist.py` — record claims, restart simulator (re-instantiate), verify confidence persists; verify decay over simulated time.
- **Acceptance:** Restart preserves confidence values; decision scoring drops for stale-fact candidates.

---

## Phase B — Sensory Activation (4 sessions)

### Session B1: Custom wake word "Hey Vector" training
**Goal:** Replace Whisper KWS fallback with custom openWakeWord model for sub-200ms latency.
- Create `scripts/train_wake_word.py`:
  - Records 15 voice samples ("Hey Vector", "Hey VECTOR", "Vector wake up", etc.)
  - Calls `openwakeword.train()` with positive samples + library negatives
  - Outputs `models/wake/hey_vector.onnx`
- In `core/voice/wake_word.py`, when `models/wake/hey_vector.onnx` exists, prefer it over Whisper KWS
- **Test:** `tests/voice/test_wake_word_custom.py` — feed test WAV containing "hey vector", verify detection within 300ms of phrase end.
- **Acceptance:** Custom model loaded; latency < 300ms; false-positive rate < 1% on 60s of background audio.

### Session B2: Ambient listener activation
**Goal:** `core/voice/ambient_listener.py` runs continuously when user grants permission.
- Verify ambient_listener.py current state (already 25 KB)
- Wire into `run_vector.py` startup: `if CONFIG.voice.ambient_enabled: AmbientListener().start()`
- Permission gate: first-time prompt asks owner; persists consent in `data/consent.json`
- Output stream: detected speech → STT → posts `EventType.USER_INTERACTION` event
- **Test:** `tests/integration/test_phase_b2_ambient.py` — synthetic audio frames, verify event fires when speech detected, doesn't fire on silence.
- **Acceptance:** Saying "Hey Vector, what time is it?" while VECTOR is running produces a logged interaction event end-to-end.

### Session B3: Multi-modal context — camera + screen
**Goal:** `core/sensing/camera.py` and `screen_observer.py` feed context_engine periodically.
- Both modules already exist; check if they're called in autonomous_loop
- If not, add a `_sense_tick()` coroutine that runs every 30s:
  - `screen_observer.capture()` → OCR/region descriptions → write to `current_context.screen_summary`
  - `camera.detect_presence()` → owner present/absent/multiple → `current_context.presence`
- Inject `screen_summary` and `presence` into `session_hydration_prompt()` when relevant
- Add user toggle in `core/config.py`: `sensing.screen_enabled`, `sensing.camera_enabled` (default OFF)
- **Test:** `tests/integration/test_phase_b3_multimodal.py` — fake screen capture path, verify context engine includes summary; fake "no presence", verify autonomous loop reduces verbosity.
- **Acceptance:** When `sensing.screen_enabled=true`, every LLM call has access to current screen summary.

### Session B4: Whisper large-v3 upgrade
**Goal:** STT quality from base → large-v3 (better accents, jargon, code).
- In `core/voice/stt.py.STT()` factory, add config option `whisper_model_size: large-v3` (default base for fallback)
- Document GPU memory cost (large-v3 needs ~10 GB VRAM); fall back to medium if insufficient
- Add quality test: WAV with technical jargon, expected text → assert WER < 0.05 on large-v3, < 0.20 on base
- **Test:** `tests/voice/test_stt_quality.py` — uses fixed WAV, asserts text quality threshold.
- **Acceptance:** large-v3 transcribes domain-specific WAV with WER < 5%.

---

## Phase C — Cloud LLM Smart Routing (4 sessions)

### Session C1: Cloud LLM router with cost-aware fallback
**Goal:** Use LLM API keys in .env for complex reasoning when local Ollama is insufficient; preserve local-first default.
- Create `core/inference/cloud_router.py`:
  - `route(prompt, complexity_hint, cost_budget)` returns provider+model
  - Complexity heuristic: token count > 8K, contains "explain why", multi-step plan, code generation > 200 lines → route to cloud
  - Cost ceiling per session via `core/metering/budget_meter.py`
- Wire into `provider_client.chat()`: if `route()` returns cloud, use existing cloud provider; else use Ollama
- Default behavior: 90% local, 10% cloud (configurable)
- **Test:** `tests/integration/test_phase_c1_cloud_router.py` — simple prompt → local; complex multi-step → cloud; budget exhausted → local fallback.
- **Acceptance:** Cost dashboard shows local/cloud split; budget cap enforced.

### Session C2: Vector semantic memory search
**Goal:** Episodic recall by meaning, not just keywords.
- In `core/memory/episodic.py`, add `search_semantic(query, top_k=10)` using sentence-transformers
- Embeddings table: `episodic_embeddings(id, embedding BLOB)` — backfill on first run
- Hybrid search: 70% semantic + 30% FTS5 keyword score
- Wire into `context_engine.session_hydration_prompt()`: replace keyword search with hybrid
- **Test:** `tests/integration/test_phase_c2_semantic_recall.py` — store "I prefer iced coffee", query "what beverage do I like", expect recall.
- **Acceptance:** Semantic queries return relevant episodes that keyword search misses.

### Session C3: Anticipatory action engine
**Goal:** VECTOR acts before being asked, based on patterns.
- Create `core/brain/anticipation.py`:
  - `AnticipationEngine.predict_next_need(window_minutes=30)` returns ranked list of likely needs
  - Sources: GoalSystem active goals, recent_episodes patterns, time-of-day heuristics, calendar
  - Uses cloud LLM (`route()` flagged as complexity_high) for reasoning
- In `autonomous_loop`, every 10 minutes call `predict_next_need()`:
  - For each prediction with confidence > 0.75, propose proactive action through normal `_act_on` flow
  - Action_type prefix `proactive_*` so permission_gateway can have stricter handling
- Surface predictions in dashboard as "Anticipating: ..."
- **Test:** `tests/integration/test_phase_c3_anticipation.py` — simulated 9pm pattern of journal-writing; verify predictor surfaces "journal" at 9:05pm.
- **Acceptance:** Predictor produces ≥1 valid prediction per hour during typical use.

### Session C4: Streaming voice with prosody (cloud TTS)
**Goal:** Emotionally-tuned voice for high-stakes/empathetic moments.
- In `core/voice/tts.py`, add `_init_elevenlabs()` (file already exists at `elevenlabs_tts.py`)
- Selection logic: emotional context (sentiment classifier output) + content type
  - Routine info → Piper (free, fast)
  - Empathetic/significant moments → ElevenLabs (cost cap via budget_meter)
- Streaming: chunk text, stream audio, support barge-in
- **Test:** `tests/voice/test_tts_streaming.py` — verify chunks emit progressively; barge-in cancels mid-stream.
- **Acceptance:** Voice has measurable emotional prosody on empathetic prompts; routine prompts use Piper.

---

## Phase D — Dashboard Live Wiring (3 sessions)

### Session D1: WebSocket bridge from autonomous_loop to dashboard
**Goal:** Real-time agent HP, decision flow, district routing visualizations.
- In `core/api/app.py`, add `/ws/state` WebSocket endpoint
- Subscribe handler to event_bus → forward to all connected clients
- Events forwarded: `EventType.DECISION_MADE`, `AGENT_HP_CHANGED`, `TASK_ROUTED`, `HYPOTHESIS_SURFACED`, `ANOMALY_DETECTED`
- In `dashboard/src/App.tsx`, replace placeholder WebSocket URL with `ws://localhost:8000/ws/state`
- Wire `VectorState` updates to incoming messages
- **Test:** `tests/integration/test_phase_d1_ws_bridge.py` — connect mock WS client, publish event, verify message arrives within 100ms.
- **Acceptance:** Dashboard mascot reacts in real time to autonomous_loop events.

### Session D2: Decision trace timeline
**Goal:** "Why did VECTOR do X?" visible as a trace.
- New dashboard panel `dashboard/src/components/panels/DecisionTrace.tsx`
- Subscribes to `DECISION_MADE` events, displays a vertical timeline:
  - Goal in scope → 4 candidates scored → winning candidate → policy approval → permission tier → execution
- Click on any decision → full reasoning chain from `core/memory/reasoning_memory`
- Color-coded by tier (GREEN/YELLOW/RED) and outcome
- **Acceptance:** Last 20 decisions visible with full reasoning chain on click.

### Session D3: Person knowledge graph view
**Goal:** Visualize who VECTOR knows + what it believes about them.
- New panel `dashboard/src/components/panels/PersonGraph.tsx`
- Force-directed graph: nodes = persons, edges = relationships, node size = trust × interaction_count
- Click person → side panel with beliefs/preferences/interaction_history (from PersonModel)
- Inline edit: change trust, add belief
- **Acceptance:** Graph shows all known persons; editing a belief updates SQLite + reflects on next session.

---

## Phase E — Cloud Deployment (2 sessions)

### Session E1: Fly.io brain server deployment
**Goal:** Cloud brain server live at `vector-brain.fly.dev`.
- Verify `cloud/brain_server/main.py` is current
- Add `core/inference` lite SDK for the cloud server (no full vectorcode dep)
- `fly launch` (one-time) → reads `cloud/brain_server/fly.toml`
- `fly secrets set VECTOR_API_KEY=<...>`
- `fly deploy`
- Health check: `curl https://vector-brain.fly.dev/status` returns 200
- Wire local `run_vector.py` to optionally use cloud brain for redundancy: `CONFIG.cloud.brain_url`
- **Acceptance:** Cloud brain reachable; local can route to cloud as fallback.

### Session E2: Cloudflare API gateway + email worker
**Goal:** External API gateway live at `api.vector.your-domain.com`.
- Verify `api/src/index.ts` (TypeScript Workers)
- `wrangler login`, `wrangler deploy` from `api/`
- Wire `cloud/email/` similarly
- Set DNS CNAME if you have a domain
- **Acceptance:** External `https://<workers-url>/v1/status` returns 200.

---

## Phase F — Final Integration & Verification (1 session)

### Session F1: End-to-end smoke + STATUS-v2.md
**Goal:** Validate the integrated system with a real conversational test.
- Manual test scenario:
  1. Add Alice to PersonModel with formal/technical style, trust=0.85
  2. Add Bob with casual/non-technical style, trust=0.40
  3. Send identical query as Alice and as Bob
  4. Verify response differs in register and tone
  5. Verify dashboard shows the events
  6. Verify decision trace contains person-style adaptation
- Run full pytest suite, target: `1,500+ tests passing`
- Run 30-min boot smoke + cloud reachability + dashboard render
- Generate `STATUS-v2.md` updating capability matrix
- Tag git release `v2.0-integrated`

---

## Stop Conditions

- Tests fail catastrophically (< 1300 passing) → diagnose, fix, don't proceed
- Brain×Avatar wiring breaks personality middleware → revert specific session
- Cloud cost spike > 10× baseline → disable cloud routing, debug
- Dashboard WebSocket flooding → throttle event forwarding

## Out of Scope (hard caps)

- **Physical actuators** (Dummy, U, Butler robotic arms) — requires hardware
- **Iron Man suit** — requires hardware
- **3D holographic interfaces** — requires AR glasses (Quest 3 / Vision Pro setup is your separate physical-world step)
- **Drone control** — requires hardware

These remain ~12% gap to JARVIS regardless of software work.

---

## Handoff Notes for Claude Code (Sonnet 4.6)

### Environment

- **Python:** `C:\Users\Arghyadeep\AppData\Local\Programs\Python\Python313\python.exe` (system Python; venv broken)
- **Test command:** `python -m pytest tests/ --timeout=15 --tb=short`
- **Baseline:** 1,363 tests passing (969 integration + 394 unit). Must stay ≥ this number.
- **Coverage gate:** 80% on `core/` (already enforced via `pyproject.toml fail_under=80`)

### Project conventions (must follow — same as ProductionFix.md)

- `from __future__ import annotations` at top of every module
- `from loguru import logger` (never stdlib `logging`)
- Log prefix `[VECTOR][<subsystem>] <message>`
- PEP 604 type hints (`int | None`, not `Optional[int]`)
- `pathlib.Path`, not `os.path`
- Explicit `__all__` in every `__init__.py`
- No `print()` outside `if __name__ == "__main__":`

### Architecture invariants (do not break)

- All actions through `core/loop/permission_gateway.py` (GREEN/YELLOW/RED)
- All LLM calls preceded by `core/loop/context_engine.session_hydration_prompt()`
- `core/loop/autonomous_loop.py` is the single async loop
- `core/event_bus/bus.py` for all inter-component events (never raw asyncio.Queue)
- `vectorcode/src/queen.py` (consensus) and `vectorcode/src/claims/` (work-stealing) are separate

### Key wiring points (memorize these)

| Brain module | Where it must wire | Existing entry point |
|---|---|---|
| `PersonModel.infer_communication_style()` | `core/personality/middleware.py` `inject()` | Wire NEW |
| `PersonModel.predict_response()` | `core/loop/context_engine.session_hydration_prompt()` | Already partial — extend |
| `CounterfactualMemory.should_avoid()` | `core/loop/autonomous_loop._act_on()` | Wire NEW (before governor dispatch) |
| `MetaCognition.detect_bias()` | `core/loop/decision_engine.score_candidate()` | Wire NEW (bias_factor) |
| `HypothesisEngine.generate()` | `core/brain/suggestion_queue.py` (NEW) → events | Wire NEW |
| `SynthesisBridge.get_recent_patterns()` | `districts/reflection/daily_reviewer.py` | Wire NEW |
| `CouncilBrain.deliberate()` | `core/loop/permission_gateway._handle_red_tier()` | Wire NEW |
| `EpistemicTracker` | `core/loop/decision_engine.score_candidate()` confidence weighting | Persist + wire |

### Test file naming convention

Each session creates one test file at:
`tests/integration/test_phase_<letter><number>_<short_name>.py`

Example: `tests/integration/test_phase_a3_counterfactual_act_on.py`

### Acceptance gate per session

A session is complete when:
1. Acceptance criteria met (specified per session)
2. New test file passes (≥ 5 tests typically)
3. No existing test regressed
4. Total test count is ≥ baseline + new tests
5. Progress Log updated in this file

### Stop and ask if

- A wiring change requires deleting an existing public API (rare; ask)
- Cloud session would commit secrets (always ask)
- Test failure is from a flaky test in unrelated module (skip with `pytest.mark.flaky`, document)

---

## Capability target after completion

| Dimension | Pre-plan | Post-plan local | Post-plan + cloud |
|---|---|---|---|
| Singular Identity | 55% | **85%** | **95%** |
| Causal Reasoning | 50% | **80%** | **92%** |
| Emotional Intelligence | 55% | **80%** | **92%** |
| Theory of Mind | 60% | **85%** | **92%** |
| Global Awareness | 55% | **80%** | **92%** |
| Voice & Presence | 55% | **85%** | **92%** |
| Memory & Context | 70% | **90%** | **95%** |
| Autonomy & Proactivity | 65% | **88%** | **95%** |
| Security & Permissions | 65% | **90%** | **90%** |
| Physical Presence | 12% | **12%** | **12%** |
| **OVERALL** | **58%** | **~83%** | **~91%** |

---

## Progress Log

| Session | Date | Status | Notes |
|---|---|---|---|
| C3 — AnticipationEngine | 2026-05-26 | DONE | anticipation_loop + _anticipation_tick in autonomous_loop; 27/27 tests |
| C4 — ElevenLabs streaming TTS | 2026-05-26 | DONE | TextToSpeech alias, _init_elevenlabs, _speak_elevenlabs_stream, prosody; 40/40 + 146/146 voice tests |
| D1 — WebSocket bridge | 2026-05-26 | DONE | /ws/state endpoint, 3 new EventTypes, dashboard wired; 29/29 tests |
| D2 — Decision trace timeline | 2026-05-26 | DONE | DecisionTrace.tsx, reasoning_memory.get_recent, /brain/reasoning/chains; 28/28 tests |
