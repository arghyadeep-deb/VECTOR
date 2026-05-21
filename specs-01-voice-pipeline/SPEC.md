# SPEC-01: Voice Pipeline Overhaul

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform VECTOR's voice pipeline from 40/100 to 90/100 — sub-500ms real-time duplex streaming with speaker identification, barge-in, and natural conversation management.

**Architecture:** Replace the current blocking sequential pipeline (wake→record→transcribe→classify→TTS) with an event-driven streaming architecture. Audio chunks flow through a VAD-gated pipeline that streams ASR results incrementally, feeds a conversation state machine for turn management, and streams TTS output back through the WebSocket — all while tracking speaker identity and modulating voice personality per session.

**Tech Stack:** faster-whisper (streaming ASR), Silero VAD (voice activity detection), speechbrain (speaker embeddings), Kokoro ONNX (TTS — keep existing, add streaming mode), ElevenLabs (optional premium TTS for content), numpy, websockets, asyncio

**Score:** Current 40/100 → Target 90/100

---

## 1. Problem Statement

### 1.1 Current Limitations

The voice pipeline scores 40/100 across six dimensions:

| Dimension | Score | Issue |
|-----------|-------|-------|
| Latency | 25/100 | 2–5 seconds from wake word to response. Blocking `record_and_transcribe()` records up to 5 seconds of audio, then transcribes the whole clip, then classifies, then speaks. No incremental/streaming output. |
| Streaming | 10/100 | The WebSocket endpoint (`voice_ws.py`) is push-to-talk only — collects all chunks, then processes. No half-duplex or full-duplex streaming. No real-time transcription display. |
| Speaker ID | 0/100 | Zero speaker identification. VECTOR cannot distinguish between Arghyadeep and another person in the room. Single-user assumption. |
| Interruption | 30/100 | `stop_speaking()` exists but only works mid-sentence — no true barge-in that captures the interrupting speech, no state cleanup, no graceful interruption recovery. |
| Conversation Flow | 40/100 | Session-based (last 16 messages) but no state machine. No distinction between query, command, follow-up, clarification, chitchat. No turn-taking protocol. |
| Language Detection | 50/100 | Works for en/hi/ja but `langdetect` is slow (~300ms per call) and inaccurate for short utterances. No code-switching support. |

### 1.2 Impact on User Experience

- User says "Hey VECTOR" → waits 2-5 seconds → hears response. Feels sluggish.
- Cannot interrupt VECTOR mid-response to correct course — must wait for silence.
- When multiple people are in the room, VECTOR responds to anyone who says "Hey VECTOR" as if they were Arghyadeep.
- Dashboard orb shows "listening" → "processing" → "speaking" but each transition has visible lags.
- No confidence indicators — VECTOR sometimes acts on hallucinated transcriptions.

### 1.3 Root Causes

1. **Blocking ASR:** `WhisperSTT.record_and_transcribe()` waits for the full recording to complete before transcribing. Whisper large-v3 takes 800ms–2s for a 5s clip.
2. **Single-chunk pipeline:** The entire audio clip is transcribed as one blob, then classified, then TTS'd — no overlap.
3. **No streaming infrastructure:** No audio chunk queue, no VAD gate, no incremental transcription handler.
4. **No speaker model:** No embedding extractor, no diarization, no speaker enrollment.
5. **Stateless conversation handling:** `AmbientListener` manages a message list but has no FSM for conversation states.

---

## 2. Current Architecture

### 2.1 High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AmbientListener                              │
│                                                                     │
│  listen_tick() [0.5s poll from autonomous_loop]                     │
│    └→ _wake_and_handle() [background task]                         │
│         └→ WakeWordDetector.listen_for_wake()                      │
│              ├─ openwakeword (frame-by-frame, ~50ms latency)       │
│              └─ Whisper KWS (2s chunks, ~2s latency)               │
│         └→ handle_voice_input(mode)                                │
│              ├─ [loop] record_and_transcribe(5s)  ◄── BLOCKING     │
│              ├─ detect_language(text)           ◄── BLOCKING       │
│              ├─ _classify_intents(text)          ◄── BLOCKING LLM  │
│              ├─ permission_gateway.execute()     ◄── BLOCKING      │
│              └─ tts.speak(response)              ◄── BLOCKING      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Key Files

| File | Role | Lines |
|------|------|-------|
| `core/voice/ambient_listener.py` | Orchestrator — wake→STT→classify→TTS | 476 |
| `core/voice/stt.py` | Multi-engine STT (whisper, faster-whisper, deepgram) | 239 |
| `core/voice/tts.py` | Kokoro ONNX TTS + pyttsx3/gTTS fallback | 195 |
| `core/voice/wake_word.py` | openwakeword + Whisper KWS | 142 |
| `core/voice/language_detector.py` | langdetect wrapper | 51 |
| `core/voice/elevenlabs_tts.py` | Content-grade TTS (not runtime voice) | 203 |
| `core/api/routers/voice_ws.py` | Push-to-talk WebSocket | 164 |
| `core/config.py` | `VoiceConfig` Pydantic model (lines 106-116) | 555 |

### 2.3 Data Flow Details

1. `AutonomousLoop.observe_loop()` calls `listener.listen_tick()` every 0.5s
2. `listen_tick()` starts `_wake_and_handle()` as a background asyncio task (if not already running)
3. `_wake_and_handle()` calls `WakeWordDetector.listen_for_wake()` — blocks until wake word
4. Once wake word detected, `handle_voice_input()` enters a session loop:
   - Stops any ongoing TTS (barge-in)
   - Calls `stt.record_and_transcribe(5.0)` — records up to 5s with VAD, then transcribes full clip
   - Detects language
   - Calls `_classify_intents()` — Ollama LLM call with VECTOR_PERSONALITY
   - Executes intents through `PermissionGateway`
   - Speaks response via `tts.speak()`
   - Stores in episodic memory
   - Loops until end phrase or 45s silence

### 2.4 Bottlenecks

- **Audio capture:** `record_until_silence()` in `WhisperSTT` uses 100ms frames, silence threshold 600ms — but still blocks until recording ends.
- **Whisper inference:** `transcribe()` on the full recording — no partial results streamed.
- **Classification:** LLM call takes 1-3s for `_classify_intents()`. No cached responses, no fast-path for simple queries.
- **TTS:** `_speak_kokoro()` splits into sentences but generates each sentence sequentially before playback.
- **Sequential pipeline:** No overlapping ASR/classification/TTS — each step waits for the previous.

---

## 3. Target Architecture

### 3.1 High-Level Flow (Target)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        VoicePipeline (new orchestrator)                   │
│                                                                          │
│  AudioStream [mic/websocket]                                             │
│    → VAD gate (Silero, 30ms frames)                                     │
│    → AudioRingBuffer (last 3s sliding window)                           │
│    → StreamingASR (faster-whisper, 200ms partials)                       │
│    → ConversationManager (turn FSM)                                      │
│         ├→ SpeakerIdentifier (embedding extractor, per-utterance)        │
│         ├→ IntentClassifier (fast-path + LLM fallback)                   │
│         └→ ResponseGenerator → StreamingTTS (Kokoro streaming mode)      │
│                                                                          │
│  Latency budget: 100ms VAD + 200ms ASR partial + 50ms classify + 150ms   │
│  TTS = 500ms total.                                                      │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Streaming Audio Data Flow

```
User speaks:  "Hey VECTOR what's the weather"
                │
                ▼
WakeWordDetector ──→ "hey_vector" detected (~200ms)
                │
                ▼
AudioStream.start_capture()
    │
    ▼  (every 30ms: 480 samples @ 16kHz)
SileroVAD.is_speech(frame) ──→ No → discard
    │ Yes
    ▼
AudioRingBuffer.append(frame)  ← sliding window, emits 200ms chunks
    │
    ▼  (every 200ms)
StreamingASR(segment) ──→ partial transcript: "Hey" → "Hey VECTOR" → "Hey VECTOR what's" → "...weather"
    │
    ▼  (on utterance_end from VAD)
ConversationManager.on_transcript_final("Hey VECTOR what's the weather")
    │
    ├→ SpeakerIdentifier.identify(audio_segment) → "Arghyadeep" (0.94)
    ├→ IntentClassifier("what's the weather") → {"action_type":"check_weather","confidence":0.92}
    │
    ▼
ResponseGenerator.generate(intent) → "It's 22°C and clear, sir."
    │
    ▼
StreamingTTS(response) → audio chunks → WebSocket
```

### 3.3 Conversation State Machine

```
                  ┌──────────────┐
                  │    IDLE      │
                  └──────┬───────┘
                         │ wake word detected
                  ┌──────▼───────┐
                  │   LISTENING  │◄─────────────────────────┐
                  └──────┬───────┘                          │
                         │ VAD: speech_start                │
                  ┌──────▼───────┐                          │
                  │  SPEAKING    │                          │
                  │  (user)      │                          │
                  └──────┬───────┘                          │
                         │ VAD: speech_end (utterance done) │
                  ┌──────▼───────┐                          │
                  │  PROCESSING  │                          │
                  │  (ASR+classify)│                        │
                  └──────┬───────┘                          │
                         │ response ready                   │
                  ┌──────▼───────┐                          │
             ┌───►│  RESPONDING  │── VECTOR speaking ────────┘
             │    │  (TTS)       │
             │    └──────┬───────┘
             │           │ VAD: user interrupts (barge-in)
             │    ┌──────▼───────┐
             └────│  INTERRUPTED │──→ capture interrupting speech → LISTENING
                  └──────────────┘
```

### 3.4 Key Metrics (Target)

| Metric | Current | Target | Method |
|--------|---------|--------|--------|
| End-to-end latency | 2-5s | <500ms | Streaming ASR + incremental TTS |
| Speaker identification | None | >90% accuracy | speechbrain ECAPA-TDNN embeddings |
| Interruption recovery | Manual stop | <1s auto | State machine + VAD barge-in |
| Concurrent sessions | 1 | 3 | Session-per-speaker routing |
| Streaming transcription | No | Yes, <300ms partials | faster-whisper live mode |
| Language detection latency | ~300ms | <50ms | FastText or embedded detector |

---

## 4. Component Breakdown

### 4.1 SpeechStreamer

**File:** `core/voice/streamer.py` (new, ~300 lines)

**Responsibility:** Real-time audio capture + VAD + streaming ASR. Produces `AudioChunk` events on an async queue.

```python
@dataclass
class AudioChunk:
    frames: np.ndarray        # float32, 16kHz mono
    sample_rate: int = 16000
    timestamp: float          # time.perf_counter()
    is_speech: bool = False
    is_utterance_start: bool = False
    is_utterance_end: bool = False
    speaker_embedding: np.ndarray | None = None


class SpeechStreamer:
    """
    Captures audio from mic (or WebSocket bytes), runs Silero VAD on 30ms frames,
    emits AudioChunk events via an async callback/queue.
    Uses a background thread for audio I/O + asyncio queue for event delivery.

    VAD state machine:
        silence → speech_start → speech → speech_end → silence
    Emits utterance_end when silence > 600ms (configurable).

    Configuration:
        CONFIG["voice"]["vad_threshold"]  (default 0.5)
        CONFIG["voice"]["vad_frame_ms"]   (default 30)
        CONFIG["voice"]["silence_sec"]    (default 0.6)
        CONFIG["voice"]["sample_rate"]    (default 16000)
    """
```

**Implementation approach:**
1. Launch a daemon thread running `sounddevice.InputStream` with 30ms blocksize
2. Each frame pushed into an `asyncio.Queue` via a thread-safe bridge
3. Async consumer runs Silero VAD on each frame, maintains speech state
4. When speech is detected, accumulate frames into a buffer
5. Every 200ms during speech, emit `AudioChunk` with partial audio for streaming ASR
6. On utterance_end, emit final chunk with `is_utterance_end=True`

**Silero VAD integration:**
- Load `silero_vad.onnx` model (ONNX runtime, ~10MB, runs on GPU if available)
- Frame size: 480 samples (30ms @ 16kHz)
- Threshold: configurable 0.5
- Trigger speech_start when probability > threshold for 3 consecutive frames
- Trigger speech_end when probability < threshold for 10 consecutive frames (200ms of silence)

**Streaming ASR:**
- Use `faster-whisper` in streaming mode via `VadFreeAudioProcessor` or incremental decoding
- Alternative: use `whisper-timestamped` for word-level timestamps
- Emit partial results every 200ms during speech
- Emit final result when `utterance_end` fires

### 4.2 SpeakerIdentifier

**File:** `core/voice/speaker_id.py` (new, ~200 lines)

**Responsibility:** Extract speaker embeddings from audio and match against enrolled profiles.

```python
@dataclass
class SpeakerProfile:
    name: str
    embedding: np.ndarray      # 192-dim ECAPA-TDNN embedding
    enrolled_at: str
    utterances_count: int = 0


class SpeakerIdentifier:
    """
    Identifies who is speaking by extracting speaker embeddings and matching
    against a registry of known profiles.

    Uses speechbrain ECAPA-TDNN (small, ~20MB, runs on GPU).
    Embeddings are 192-dimensional L2-normalized vectors.
    Matching: cosine similarity with threshold 0.7.

    Enrollment: User says "VECTOR this is me" → capture 3s audio → extract
    embedding → store in profiles/{name}.npy + profiles registry.

    Registry: SQLite table `speaker_profiles` in vector_memory.db:
        CREATE TABLE IF NOT EXISTS speaker_profiles (
            name TEXT PRIMARY KEY,
            embedding BLOB,        -- np.ndarray serialized via .tobytes()
            enrolled_at TEXT,
            utterances_count INTEGER DEFAULT 0
        );

    Simplified fallback: single-user mode returns "Arghyadeep" with
    confidence 1.0 if only one speaker has been enrolled.
    """
```

**Implementation approach:**
1. Load speechbrain ECAPA-TDNN ONNX model at startup (~2s cold start, then cached)
2. Extract embedding from each utterance (full audio segment between VAD start/end)
3. Compare against enrolled profiles using cosine similarity
4. Best match >0.7 threshold → identified speaker
5. Below 0.7 → "unknown" with best confidence score
6. Unknown speakers that appear >3 times in a session → prompt user to enroll

**Simplified fallback (no dependencies):**
- Extract MFCC features using librosa, train a simple GMM per speaker
- Lower accuracy (~70%) but zero additional model download
- Selected via `CONFIG["voice"]["speaker_id_method"] = "simple" | "speechbrain"`

### 4.3 ConversationManager

**File:** `core/voice/conversation_manager.py` (new, ~350 lines)

**Responsibility:** Turn-taking state machine, interruption handling, session lifecycle, multi-session routing.

```python
class ConversationState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    USER_SPEAKING = "user_speaking"
    PROCESSING = "processing"
    VECTOR_SPEAKING = "vector_speaking"
    INTERRUPTED = "interrupted"
    SESSION_END = "session_end"


@dataclass
class ConversationSession:
    session_id: str
    speaker_name: str
    state: ConversationState
    created_at: float
    last_activity: float
    history: list[dict]       # message history
    pending_interrupt: bool = False
    interrupt_audio: np.ndarray | None = None


class ConversationManager:
    """
    Manages multiple conversation sessions (one per active speaker).
    Each session has a turn-taking FSM that handles:
      - Normal turn: LISTENING → USER_SPEAKING → PROCESSING → VECTOR_SPEAKING → LISTENING
      - Interruption: VECTOR_SPEAKING → INTERRUPTED → LISTENING (captures interrupting speech)
      - Timeout: idle 60s → SESSION_END
      - End phrase: "that's all VECTOR" → SESSION_END

    Session routing: SpeechStreamer emits audio chunks tagged by speaker embedding.
    ConversationManager routes to the correct session. If no session for speaker,
    creates a new one. Max 3 concurrent sessions.

    Events emitted (consumed by VoicePipeline):
      - session_start(session_id, speaker)
      - transcript_partial(session_id, text)
      - transcript_final(session_id, text)
      - intent(session_id, intent)
      - response_ready(session_id, text)
      - session_end(session_id)
      - interruption(session_id, interrupting_text)
    """
```

**State transition rules:**
1. **IDLE → LISTENING:** Wake word detected (any speaker)
2. **LISTENING → USER_SPEAKING:** VAD speech_start
3. **USER_SPEAKING → PROCESSING:** VAD speech_end (utterance complete)
4. **PROCESSING → VECTOR_SPEAKING:** Response generated
5. **VECTOR_SPEAKING → LISTENING:** TTS complete, continue listening
6. **VECTOR_SPEAKING → INTERRUPTED:** VAD speech_start during TTS (barge-in)
7. **INTERRUPTED → LISTENING:** Interrupting utterance complete, route to intent
8. **Any → SESSION_END:** End phrase or 60s inactivity

**Interruption handling:**
1. While VECTOR is speaking, VAD continues running
2. If speech_start detected during TTS → enter INTERRUPTED
3. Stop TTS immediately (`sd.stop()` + clear buffer)
4. Capture the interrupting audio in `interrupt_audio`
5. When VAD speech_end on interruption → route interrupting text through ASR → classify
6. The interrupted response is discarded (or logged for context)
7. New response replaces the interrupted one

### 4.4 VoicePersonality

**File:** `core/voice/voice_personality.py` (new, ~150 lines)

**Responsibility:** Tone modulation, response pacing, filler word handling, personality watermark.

```python
class VoicePersonality:
    """
    Modulates VECTOR's spoken delivery based on context:
      - Response pacing: insert natural pauses based on response length
      - Filler handling: strip "um", "uh", "like" from LLM output
      - Tone markers: adjust speed/pitch based on user sentiment
      - Personality watermark: slightly dry, precise, minimal words
      - Pacing rules:
          <20 words: speak at 0.85 speed (default)
          20-50 words: 0.90 speed (slightly faster)
          >50 words: break into paragraphs with 300ms gaps
      - Emotion detection in text: exclamation → slight pitch rise

    Uses Kokoro's speed parameter (0.1-3.0) for pacing.
    Does NOT modify the LLM output text — only delivery characteristics.
    """
```

**Implementation approach:**
1. Post-process LLM response text before TTS
2. Strip filler words and phrases
3. Measure word count, apply pacing rules
4. If response contains instructions → use deliberate pace (0.80 speed)
5. If response is acknowledgment → use normal pace (0.85 speed)
6. If response is urgent → use faster pace (0.95 speed)
7. Insert SSML-like prosody markers if Kokoro supports them

### 4.5 TTSEngine Upgrade

**File:** `core/voice/tts.py` (modify, add streaming mode)

**Current:** Kokoro generates full audio before playback, sentence-by-sentence.

**Target:** Add streaming mode where audio is played as each sentence is generated:

```python
class StreamingTTS:
    """
    Wraps VoiceTTS with streaming playback.

    stream_speak(text, chunk_callback):
      - Splits text into sentences (existing logic)
      - Generates each sentence via Kokoro
      - Calls chunk_callback(wav_bytes) after each sentence
      - chunk_callback sends via WebSocket or plays locally
      - Supports early termination on barge-in
      - Returns immediately (non-blocking)

    The local playback case uses sd.play() with overlapping streams
    to eliminate gaps between sentences (cross-fade 50ms).

    For WebSocket delivery, each chunk is base64-encoded and sent as
    {"type": "audio_chunk", "data": "...", "sample_rate": 24000}.
    """
```

**ElevenLabs integration (optional upgrade):**
- Detect `ELEVENLABS_KEY` in config
- If available and `CONFIG["voice"]["premium_tts"]` is True, use ElevenLabs streaming API
- ElevenLabs streaming returns audio chunks in real-time (100ms latency to first audio)
- Fall back to Kokoro if ElevenLabs unavailable or rate-limited
- Price-aware: ElevenLabs costs ~$0.30/char — only use for content, not runtime

---

## 5. Agent Dispatch Plan

### 5.1 Agent A: SpeechStreamer + VAD Integration

**Scope:**
- `core/voice/streamer.py` — Audio capture, Silero VAD, audio ring buffer, streaming ASR
- Modify `core/voice/stt.py` — add streaming ASR mode to FasterWhisperSTT
- `core/api/routers/voice_ws.py` — add streaming WebSocket handlers
- Tests in `tests/voice/test_streamer.py`, `tests/voice/test_vad.py`

**Deliverables:**
1. `core/voice/streamer.py` — complete SpeechStreamer class with Silero VAD
2. Modified `core/voice/stt.py` — FasterWhisperSTT gets `transcribe_stream()` method
3. Modified `core/api/routers/voice_ws.py` — `/ws/voice/stream` endpoint (streaming duplex)
4. Silero VAD model download script at `scripts/download_vad_model.py`
5. Unit tests for VAD state machine, audio capture, streaming ASR
6. Integration test: mic → VAD → ASR → transcript callback

### 5.2 Agent B: Speaker ID + Conversation Manager

**Scope:**
- `core/voice/speaker_id.py` — Speaker embedding extraction and matching
- `core/voice/conversation_manager.py` — Turn-taking FSM, session lifecycle, interruption handling
- Modify `core/voice/ambient_listener.py` — wire into new architecture (keep backward compat)
- Tests in `tests/voice/test_speaker_id.py`, `tests/voice/test_conversation_manager.py`

**Deliverables:**
1. `core/voice/speaker_id.py` — SpeakerIdentifier class with speechbrain ECAPA-TDNN
2. Speaker enrollment flow: user says "VECTOR this is me" → extract → store
3. `core/voice/conversation_manager.py` — ConversationManager with full FSM
4. Interruption handling: capture, cleanup, re-route interrupted speech
5. Barge-in test suite: TTS interruption at various points
6. Modified ambient_listener.py that delegates to new components
7. SQLite schema migration for `speaker_profiles` table

### 5.3 Agent C: TTS Upgrade + Voice Personality

**Scope:**
- Modify `core/voice/tts.py` — add streaming mode, sentence-level callbacks
- `core/voice/voice_personality.py` — response pacing, filler handling, tone modulation
- Modify `core/config.py` — add voice personality config fields
- Tests in `tests/voice/test_streaming_tts.py`, `tests/voice/test_voice_personality.py`

**Deliverables:**
1. `StreamingTTS` class in `core/voice/tts.py` (or new file, architect's choice)
2. Cross-fade between Kokoro sentences (50ms overlap to eliminate gaps)
3. `core/voice/voice_personality.py` — VoicePersonality class
4. Filler word dictionary (50+ common fillers)
5. Pacing rules engine
6. WebSocket streaming TTS integration
7. ElevenLabs premium TTS path (optional, config-gated)

---

## 6. Implementation Steps

### 6.1 Phase 1: Foundation (Agent A)

**Step 1.1: Create Silero VAD module**

- [ ] Create `core/voice/vad.py` with SileroVAD class
- [ ] Model: download `silero_vad.onnx` from GitHub releases (or bake auto-download)
- [ ] Frame size: 480 samples (30ms @ 16kHz), threshold: 0.5
- [ ] State machine: silence → speech_start → speech → speech_end → silence
- [ ] Emit callbacks: `on_speech_start()`, `on_speech_end()`, `on_frame(speech_prob)`

**Step 1.2: Create SpeechStreamer**

- [ ] Create `core/voice/streamer.py` with SpeechStreamer class
- [ ] Background thread with `sounddevice.InputStream` (30ms blocksize)
- [ ] Thread-safe `asyncio.Queue` bridge for event delivery
- [ ] Ring buffer: last 3 seconds of audio, 200ms chunk emission during speech
- [ ] `AudioChunk` dataclass with all metadata fields

**Step 1.3: Add streaming ASR to FasterWhisperSTT**

- [ ] Add `transcribe_stream(audio_chunks: AsyncIterator[np.ndarray]) -> AsyncIterator[str]` method
- [ ] Use faster-whisper's built-in VAD-free audio processor for incremental decoding
- [ ] Emit partial results every 200ms during speech
- [ ] Fall back to standard `transcribe()` for final utterance

**Step 1.4: Update voice_ws.py WebSocket**

- [ ] Add `/ws/voice/stream` endpoint (streaming full-duplex)
- [ ] Protocol: binary chunks in, JSON messages out (partial transcript, final transcript, audio chunks)
- [ ] Wire SpeechStreamer to WebSocket lifecycle
- [ ] Keep existing push-to-talk endpoint for backward compatibility

**Step 1.5: Test**

- [ ] `tests/voice/test_vad.py` — unit tests for VAD state machine
- [ ] `tests/voice/test_streamer.py` — test audio capture + chunk emission
- [ ] `tests/voice/test_stt_streaming.py` — test streaming ASR with synthetic audio
- [ ] Manual test: run `python core/voice/streamer.py` and verify real-time transcription

### 6.2 Phase 2: Conversation Intelligence (Agent B)

**Step 2.1: Create SpeakerIdentifier**

- [ ] Create `core/voice/speaker_id.py`
- [ ] SpeechBrain ECAPA-TDNN model loader (ONNX, auto-download)
- [ ] `extract_embedding(audio: np.ndarray) -> np.ndarray`
- [ ] `identify(embedding) -> (name, confidence)`
- [ ] `enroll(name, audio) -> None`
- [ ] SQLite table `speaker_profiles` for persistent storage
- [ ] Simple fallback (MFCC + GMM) when speechbrain unavailable

**Step 2.2: Create ConversationManager**

- [ ] Create `core/voice/conversation_manager.py`
- [ ] `ConversationState` enum with 7 states
- [ ] `ConversationSession` dataclass with full state
- [ ] `ConversationManager` class with session routing, state machine, interruption
- [ ] Session timeout: 60s inactivity
- [ ] Max concurrent sessions: 3
- [ ] Event emitter pattern (callbacks for pipeline integration)

**Step 2.3: Wire interruption handling**

- [ ] SpeechStreamer continues running during TTS
- [ ] If VAD speech_start during VECTOR_SPEAKING → enter INTERRUPTED
- [ ] Capture interrupting audio, route through ASR
- [ ] TTS streaming receives stop signal, clears buffer
- [ ] New response replaces interrupted one

**Step 2.4: Update ambient_listener.py**

- [ ] Keep `AmbientListener` class but delegate to new components
- [ ] `listen_tick()` → checks ConversationManager for pending results
- [ ] Backward compatible: same return dict format for autonomous loop

**Step 2.5: Test**

- [ ] `tests/voice/test_speaker_id.py` — test enrollment + identification
- [ ] `tests/voice/test_conversation_manager.py` — FSM transition tests
- [ ] `tests/voice/test_interruption.py` — barge-in timing tests
- [ ] Manual test: two speakers, verify correct identification

### 6.3 Phase 3: Voice Personality + Streaming TTS (Agent C)

**Step 3.1: Add streaming mode to TTS**

- [ ] Create `StreamingTTS` class in `core/voice/tts.py`
- [ ] Sentence splitting (existing logic) + per-sentence generation callback
- [ ] Cross-fade between sentences (50ms overlap, linear ramp)
- [ ] Early termination signal for barge-in
- [ ] WebSocket chunk delivery integration

**Step 3.2: Create VoicePersonality**

- [ ] Create `core/voice/voice_personality.py`
- [ ] Filler word stripping (regex-based, 50+ filler dictionary)
- [ ] Pacing rules: response length → Kokoro speed parameter
- [ ] Tone markers: exclamation detection → delivery adjust
- [ ] Config fields: `pacing_base`, `pacing_excited`, `pacing_instructional`

**Step 3.3: Add config fields**

- [ ] Add to `VoiceConfig` in `core/config.py`:
  - `vad_threshold: float = 0.5`
  - `vad_frame_ms: int = 30`
  - `silence_sec: float = 0.6`
  - `speaker_id_method: str = "simple"`  # "simple" | "speechbrain"
  - `speaker_id_threshold: float = 0.7`
  - `premium_tts: bool = False`  # ElevenLabs for content
  - `pacing_base: float = 0.85`
  - `conversation_timeout_sec: float = 60.0`
  - `max_concurrent_sessions: int = 3`

**Step 3.4: Test**

- [ ] `tests/voice/test_streaming_tts.py` — test streaming callback, cross-fade, termination
- [ ] `tests/voice/test_voice_personality.py` — test filler removal, pacing
- [ ] E2E test: wake word → stream ASR → classify → stream TTS (measure latency)

### 6.4 Phase 4: Integration & Commissioning

**Step 4.1: Pipeline integration**
- [ ] Create `core/voice/pipeline.py` — VoicePipeline orchestrator class
- [ ] Wires: SpeechStreamer → ConversationManager → SpeakerIdentifier → IntentClassifier → ResponseGenerator → StreamingTTS
- [ ] Autonomous loop integration: `listen_tick()` → `pipeline.tick()`

**Step 4.2: Dashboard orb integration**
- [ ] Update WebSocket events to include FSM state transitions
- [ ] Dashboard orb responds to: idle, listening, user_speaking, processing, vector_speaking

**Step 4.3: Performance benchmarks**
- [ ] Measure: end-to-end latency, streaming ASR latency, speaker ID accuracy, TTS first-word latency

---

## 7. Files to Create/Modify

### Create:

| File | Lines | Purpose |
|------|-------|---------|
| `core/voice/vad.py` | ~150 | Silero VAD wrapper with state machine |
| `core/voice/streamer.py` | ~300 | Audio capture + chunk emission + ring buffer |
| `core/voice/speaker_id.py` | ~200 | Speaker embedding extraction and matching |
| `core/voice/conversation_manager.py` | ~350 | Turn-taking FSM + session lifecycle |
| `core/voice/voice_personality.py` | ~150 | Tone modulation, pacing, filler handling |
| `core/voice/pipeline.py` | ~200 | Orchestrator for all voice components |
| `tests/voice/test_vad.py` | ~100 | VAD unit tests |
| `tests/voice/test_streamer.py` | ~100 | Streamer unit tests |
| `tests/voice/test_speaker_id.py` | ~100 | Speaker ID tests |
| `tests/voice/test_conversation_manager.py` | ~150 | FSM transition tests |
| `tests/voice/test_streaming_tts.py` | ~100 | Streaming TTS tests |
| `tests/voice/test_voice_personality.py` | ~80 | Personality tests |
| `scripts/download_vad_model.py` | ~50 | Auto-download Silero VAD ONNX model |

### Modify:

| File | Change |
|------|--------|
| `core/voice/stt.py` | Add `transcribe_stream()` to FasterWhisperSTT |
| `core/voice/tts.py` | Add StreamingTTS class with sentence callbacks |
| `core/voice/ambient_listener.py` | Wire ConversationManager, keep backward compat |
| `core/api/routers/voice_ws.py` | Add streaming WebSocket endpoint |
| `core/config.py` | Add 10 new VoiceConfig fields |
| `core/voice/__init__.py` | Export new classes |

---

## 8. Success Criteria

### 8.1 Measurable Metrics

| Criterion | Current | Target | Measurement Method |
|-----------|---------|--------|-------------------|
| End-to-end latency | 2-5s | <500ms (90th percentile) | Synthetic bench: record 3s utterance, measure time to first audio response |
| ASR partial latency | N/A | <300ms (first partial) | Measure time from VAD speech_start to first partial transcript |
| Speaker identification accuracy | 0% | >90% on enrolled speakers | 50 test utterances from 3 enrolled speakers |
| Speaker identification reject rate | N/A | <5% false accept for unknown | 20 utterances from unknown speaker |
| Barge-in recovery | Manual | <1s | Interrupt TTS at random point 20x, measure recovery time |
| Streaming transcript delay | N/A | <500ms behind real-time | Compare transcript timestamps to audio timestamp |
| TTS first-word latency | ~500ms | <150ms | Measure from response ready to first audio sample playing |
| Concurrent session handling | 1 | 3 | Open 3 simultaneous voice WebSocket connections |
| Filler word removal | N/A | 100% of 50+ filler words | Test corpus with known fillers |
| Session timeout accuracy | ~45s | 60s ±1s | Measure idle→session_end timing |
| Memory store success rate | ~100% | >99% | 100 voice interactions, verify all stored |
| Wake word latency (openwakeword) | ~50ms | <30ms | Measure from audio sample to callback |
| Wake word latency (KWS fallback) | ~2s | <500ms | Measure from wake phrase to trigger |

### 8.2 Qualitative Criteria

1. Voice interaction feels "instant" — no noticeable gap between finishing a question and hearing the answer
2. Interrupting VECTOR mid-sentence works naturally — the interruption is processed as a new command
3. Switching between speakers (e.g., Arghyadeep and a friend) routes correctly to separate sessions
4. Dashboard orb shows real-time state transitions without visible lag
5. Response pacing sounds natural — not rushed or artificially slow
6. No filler words ("um", "uh") leak into TTS output
7. End-to-end flow works identically on local mic and WebSocket

### 8.3 Regression Checks

1. Existing push-to-talk WebSocket (`/ws/voice/stream` → old flow) still works
2. `AmbientListener.listen_tick()` still returns correct dict format for autonomous loop
3. Wake word detection accuracy is not degraded
4. Memory storage of voice interactions still works
5. Language detection still works (en, hi, ja)
6. All existing tests pass: `pytest tests/voice/`

---

## 9. Dependencies

### 9.1 External Packages

```txt
# Add to requirements.txt:
silero-vad>=0.3.0            # ONNX-based VAD, 30ms frames
speechbrain>=1.0.0           # Speaker embedding extraction (optional)
onnxruntime-gpu>=1.18.0      # Silero VAD inference on GPU
sounddevice>=0.5.0           # Already present — audio capture
faster-whisper>=1.0.0        # Already in requirements — add streaming mode
```

### 9.2 Internal Dependencies

1. **specs-02 (Parallel Distribution):** The new voice pipeline emits events on an internal event bus. Once specs-02 is implemented, `ConversationManager` should publish events (transcript_ready, intent_ready) via the `EventBus` rather than direct callbacks. The voice pipeline should work in standalone mode until specs-02 is ready.
2. **specs-03 (Personality Engine):** `VoicePersonality` should consume the `ToneAdapter` from specs-03 to modulate delivery based on user sentiment. For now, `VoicePersonality` uses a simple rule-based approach that will be upgraded when specs-03 ships.
3. **Dashboard:** The dashboard orb state events (WebSocket `orb_state` messages) should be enhanced to include fine-grained FSM states from `ConversationManager`.

### 9.3 Model Downloads

```bash
# Silero VAD (required):
python scripts/download_vad_model.py
# Downloads to: ./models/silero_vad/silero_vad.onnx (~10MB)

# SpeechBrain ECAPA-TDNN (optional, for speaker ID):
python scripts/download_speaker_id_model.py
# Downloads to: ./models/speechbrain/ecapa-tdnn.onnx (~20MB)
```

---

## 10. Rollout Plan

### Phase 1 (Week 1): Foundation
- SpeechStreamer + VAD working
- Streaming ASR producing partial transcripts
- WebSocket streaming endpoint ready
- Testing: unit tests pass, manual demo with synthetic audio

### Phase 2 (Week 2): Conversation Intelligence
- Speaker identification working (enrolled profiles)
- ConversationManager FSM handling single session
- Interruption handling working
- Testing: two-speaker scenario, barge-in at various TTS points

### Phase 3 (Week 3): Personality + Streaming TTS
- Streaming TTS eliminates gaps between sentences
- Voice personality modulates pacing
- Filler word removal active
- Testing: latency benchmarks meet targets

### Phase 4 (Week 4): Integration
- Full pipeline wired end-to-end
- Autonomous loop integration
- Dashboard orb integration
- Regression testing: all existing features still work
- Production deployment: swap old pipeline for new

---

## 11. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Silero VAD poor accuracy on noisy audio | Medium | High | Test with fan noise, music; fall back to energy-based VAD |
| SpeechBrain model too large for GPU | Low | Medium | Use MFCC+GMM fallback; ECAPA-TDNN is only 20MB |
| Streaming ASR produces too many partials | Medium | Low | Cooldown period 200ms between partial emissions |
| Speaker ID fails on short utterances | High | Low | Only ID on utterances >1s; unknown speaker fallback |
| Breaking existing voice flow | Low | High | Keep old ambient_listener; feature-flag new pipeline |
| Socket buffer overflow with streaming audio | Low | Medium | Backpressure via asyncio.Queue maxsize |

---

## 12. Appendix: Voice Pipeline Data Schemas

### AudioChunk Event (internal queue)

```python
@dataclass
class AudioChunk:
    frames: np.ndarray          # float32, shape: (N,) or (N, 1)
    sample_rate: int            # typically 16000
    timestamp: float            # time.perf_counter() at capture
    frame_index: int            # monotonic counter
    is_speech: bool             # VAD result
    vad_probability: float      # raw VAD probability 0.0-1.0
    is_utterance_start: bool    # transition from silence to speech
    is_utterance_end: bool      # transition from speech to silence
    utterance_id: str | None    # set on speech_start, cleared on speech_end
```

### WebSocket Streaming Protocol

```json
// Client → Server: binary audio chunks (16kHz mono PCM float32)
// Server → Client (text frames):

// Partial transcript (streaming ASR):
{"type": "transcript_partial", "session_id": "...", "text": "what's the"}

// Final transcript (utterance complete):
{"type": "transcript_final", "session_id": "...", "text": "what's the weather"}

// Speaker identified:
{"type": "speaker", "session_id": "...", "speaker": "Arghyadeep", "confidence": 0.94}

// Response text (before TTS):
{"type": "response_text", "session_id": "...", "text": "It's 22°C and clear, sir."}

// Audio chunk (streaming TTS):
{"type": "audio_chunk", "session_id": "...", "data": "<base64>", "sample_rate": 24000, "sequence": 0}

// Audio stream end:
{"type": "audio_end", "session_id": "..."}

// State transitions:
{"type": "state", "session_id": "...", "state": "listening|user_speaking|processing|vector_speaking"}

// Error:
{"type": "error", "session_id": "...", "text": "error message"}
```

### Speaker Profile Storage (SQLite)

```sql
CREATE TABLE IF NOT EXISTS speaker_profiles (
    name TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,        -- np.ndarray.tobytes() of 192-dim float32
    embedding_shape TEXT NOT NULL,  -- "(192,)" for deserialization
    enrolled_at TEXT NOT NULL,       -- ISO 8601 timestamp
    utterances_count INTEGER DEFAULT 0,
    last_seen TEXT,
    notes TEXT DEFAULT ''
);
```
