# OD-58 Sound Classifier Autonomous Wiring Plan

**Goal:** Run local ambient-sound classification on every autonomous observe tick and emit non-spamming emergency signals without blocking or killing the loop.

**Architecture:** `AutonomousLoop` owns one lazily constructed `SoundClassifier` and calls its existing blocking microphone/classification API through `asyncio.to_thread()`. `SoundClassifier` remains an in-memory classifier, exposes cheap runtime state for future HUD use, rate-limits each alert label, and backs off after capture failures. Configuration makes the owner-approved sensor active by default while retaining explicit override fields.

**Tech Stack:** Python 3.12, asyncio, NumPy, sounddevice, optional ONNX Runtime, pytest, loguru.

---

### Task 1: Add failing OD-58 regressions

**Files:**
- Create: `tests/test_od58_sound_classifier_autonomous_wiring.py`

- [ ] Prove `_observe_tick()` invokes the real `SoundClassifier.sample_and_classify()` path on each enabled tick using a fake external sounddevice only.
- [ ] Prove an alert frame reaches the real `districts.emergency.main._emit()` dispatch path.
- [ ] Prove a second alert inside the configured cooldown is suppressed.
- [ ] Prove missing microphone and missing configured model conditions return safely without raising.
- [ ] Run the new test file before implementation and record the expected failures.

### Task 2: Add owner-visible configuration and resilient classifier behavior

**Files:**
- Modify: `core/config.py`
- Modify: `core/sensing/sound_classifier.py`

- [ ] Add `sound_enabled=True`, a 60-second alert cooldown, and a 30-second capture-failure retry interval to `SensingConfig`, with comments documenting the owner-approved defaults and override rationale.
- [ ] Keep frames memory-only and document that no raw samples are persisted.
- [ ] Add per-label monotonic cooldown state around emergency emission.
- [ ] Add active/last-label state suitable for cheap status inspection, a one-time active microphone log, and warning-once/backoff behavior for unavailable capture.
- [ ] Warn once and retain heuristic fallback when an explicitly configured ONNX model is missing or unavailable.

### Task 3: Wire the classifier into observe ticks

**Files:**
- Modify: `core/loop/autonomous_loop.py`

- [ ] Add a lazy production-owned `SoundClassifier` field.
- [ ] On every eligible observe tick, call `sample_and_classify()` using `await asyncio.to_thread(...)`.
- [ ] Isolate all construction/capture failures so voice handling and the never-die loop continue.
- [ ] Document the independent microphone-stream choice and the existing wake-word contention risk without implementing an unapproved broker.

### Task 4: Establish red/green evidence and verify

**Files:**
- Test: `tests/test_od58_sound_classifier_autonomous_wiring.py`
- Test: `tests/test_sound_classifier_emergency_signal.py`
- Test: `tests/loop/test_autonomous_loop.py`

- [ ] After implementation, stash only modified implementation files while leaving the new test present; run the new tests to confirm pre-fix failure, then restore the implementation. If `.git/index.lock` prevents stashing, report it verbatim.
- [ ] Run `python -m py_compile` for every touched Python file.
- [ ] Run the existing sound-classifier tests, the new OD-58 tests, and the autonomous-loop test file only.
- [ ] Inspect `git diff`, confirm changes remain unstaged, and do not commit.
