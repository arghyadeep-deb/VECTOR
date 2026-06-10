# Task 03 — Install voice/vision dependencies

- **Depends on:** none
- **Who:** me
- **Effort:** ~20 min (downloads)

## Objective

The five missing sense packages are importable. Kokoro model files are already
at `models/kokoro/` so TTS switches from pyttsx3 to the real VECTOR voice the
moment `kokoro-onnx` lands.

## Implementation

```
pip install kokoro-onnx openai-whisper openwakeword mediapipe face-recognition
```

Gotchas: `face-recognition` needs dlib — if its wheel fails on Python 3.13,
try `pip install dlib-bin` first. `openai-whisper` pulls torch (already
installed, 2.11.0). Confirm CUDA still detected after.

## Tests

```
python -c "import whisper, kokoro_onnx, openwakeword, mediapipe, face_recognition; print('senses OK')"
python core/voice/tts.py        # should report Kokoro engine, not pyttsx3
python core/voice/wake_word.py  # should report openwakeword path
```

## Demo

`python core/voice/tts.py` speaks a line in the Kokoro voice.

## Acceptance

- [ ] All five imports succeed
- [ ] TTS self-test uses Kokoro (bf_emma)
- [ ] Wake-word self-test reports method=openwakeword
- [ ] `nvidia-smi` still shows torch CUDA context works
