# Task 06 — First HUD duplex conversation + tuning

- **Depends on:** Tasks 03, 04 (05 optional — STT fallback covers wake)
- **Who:** OWNER + me
- **Effort:** ~30 min

## Objective

A real conversation through `/hud/`: you talk, VECTOR answers in the Kokoro
voice, barge-in works, 30s silence → IDLE, "Vector" resumes.

## Implementation

1. `python run_vector.py api` then open `http://127.0.0.1:8000/hud/`.
2. Hold a conversation; exercise: interruption mid-answer, long pause → IDLE,
   wake word resume, an action command ("Vector, search the web for …").
3. Tune `CONFIG["voice"]` per symptom (read by `core/voice/realtime.py`):
   - cuts you off → raise `endpoint_silence_ms` (280 → 400+)
   - misses end of speech → lower it
   - false barge-in → raise `vad_threshold` / `bargein_debounce_ms`
   - slow first audio → keep `vector-focus` warm, check VRAM

## Tests

Manual conversation script above; watch the `state` events in the HUD console.

## Demo

One uninterrupted 2-minute conversation with at least one barge-in and one
IDLE→wake cycle.

## Acceptance

- [ ] STT transcribes you accurately (large-v3 or small per config)
- [ ] Replies speak in Kokoro voice with <2s first-audio latency
- [ ] Barge-in interrupts within ~150ms
- [ ] IDLE after configured timeout; wake word resumes
- [ ] Tuned values committed to `core/config.py` defaults
