# Task 05 — Train "Hey Vector" wake word

- **Depends on:** Task 03
- **Who:** OWNER (needs your mic)
- **Effort:** ~15 min

## Objective

A custom openWakeWord ONNX at `models/wake/hey_vector.onnx` replaces both the
hey_jarvis placeholder and the STT-burst fallback for IDLE wake.

## Implementation

```
python -c "import asyncio; from core.voice.wake_word import WakeWordDetector; print(asyncio.run(WakeWordDetector().train_wake_word(10)))"
```

Records 10 samples of "Hey Vector" → runs `openwakeword.train` → saves model →
hot-reloads. If training output lands in `models/wake_word/`, move the .onnx to
`models/wake/hey_vector.onnx` (the path `_init_model()` loads).

## Tests

`python core/voice/wake_word.py` → method=openwakeword(hey_vector).

## Demo

In an idle duplex session (30s silent → IDLE), saying "Hey Vector" resumes
LISTENING via the openwakeword path (check log: no STT KWS fallback).

## Acceptance

- [ ] `models/wake/hey_vector.onnx` exists and loads
- [ ] Wake from IDLE works by voice without the Whisper fallback
