# VECTOR Realtime Conversation Loop — Design

**Status:** ✅ Implemented (verified 2026-06-20 — `core/voice/realtime.py`,
`RealtimeConversation`, all 5 phases present: streaming response, VAD/FSM
conversation loop, barge-in, action handoff, proactive nudge speech; wired
into `core/api/routers/voice_ws.py`) · **Author:** designed with Claude · **Date:** 2026-06-10
**Goal:** Make talking to VECTOR feel like JARVIS — sub-1.2s voice-to-voice, interruptible, able to speak up on its own.

Kept as architecture reference — explains the design rationale behind
`realtime.py`'s structure. Not verified end-to-end live (needs a microphone
session to confirm actual latency numbers match §3's targets).

---

## 1. Problem

Voice today is a **batch pipeline** with three full-stop waits:

```
mic ──(record FULL utterance)──► WhisperSTT (whole clip)
        ──► Ollama /api/generate  stream:False  (whole response)
        ──► Kokoro TTS (whole response → WAV)
        ──► WS base64 chunks, 0.1s sleep each
```

Measured from code (`core/api/routers/voice_ws.py`):
- STT waits for the complete utterance (`_transcribe(chunks)` after WS loop ends)
- LLM call is `stream: False` (line ~217) — nothing is emitted until the last token
- TTS synthesizes the entire response before the first audio byte leaves
- The wake-word path is worse: `core/api/tasks.py` sets `loop._pending_voice`, which waits
  for the next `think_loop` tick — **up to 10 seconds** before anything happens
- `ConversationManager` (a correct FSM with `INTERRUPTED` state and barge-in semantics)
  exists but **is not used** by `voice_ws.py` at all
- Default `whisper_model` is `large-v3` — a transcription-quality choice, not a latency choice

Result: total latency = STT(full) + LLM(full) + TTS(full) ≈ 4–10s. No interruption possible.

## 2. Goals / Non-goals

**Goals**
- G1: voice-to-first-audio ≤ **1.2s** for conversational turns
- G2: **barge-in** — user speaks over VECTOR → VECTOR stops within 250ms and listens
- G3: continuous conversation after wake word (no re-wake per turn, session timeout 30s — already in `ConversationManager`)
- G4: **proactive speech** — high-priority nudges are spoken, not just stored
- G5: actions still go through Governor + PermissionGateway — the fast path must NOT bypass RULE 3
- G6: zero new external services — reuse Ollama, Kokoro, faster-whisper, existing event bus

**Non-goals**
- Telephony, multi-user sessions, cloud ASR (single owner, local-first)
- Replacing the think_loop — the fast path handles *conversation*; autonomy stays where it is

## 3. Latency budget (the contract)

| Stage | Today | Target | How |
|---|---|---|---|
| Endpoint detection | n/a (client decides) | 250–300 ms | server-side VAD silence threshold (`core/voice/vad.py`) |
| STT final | 1–3 s (large-v3, full clip) | 150–300 ms | faster-whisper `distil-small.en`/`base`, incremental decode on rolling buffer |
| LLM first token | full response (2–6 s) | 200–400 ms | Ollama `stream:true`, short voice-system-prompt, small `vector-focus` |
| First TTS audio | full response synth | 150–250 ms | synthesize per sentence (Kokoro `_chunk_sentences` already does overlap) |
| **Total to first audio** | **4–10 s** | **≤ 1.2 s** | |
| Barge-in stop | impossible | ≤ 250 ms | VAD on inbound frames during `VECTOR_SPEAKING` → cancel + flush |
| Rules-engine bypass | 10 s (think tick) | ≤ 300 ms | run `rules_engine.match()` directly in fast path (no LLM) |

## 4. Architecture

One new module orchestrates existing pieces; almost everything else is rewiring.

```
                        ┌────────────────────────────────────────────────┐
                        │  core/voice/realtime.py   (NEW ~400 LOC)       │
                        │  RealtimeConversation orchestrator             │
                        │  owns: ConversationManager FSM (existing)      │
                        └────────────────────────────────────────────────┘
 mic PCM frames                 │            │            │
 (WS /voice/stream,   ┌─────────▼──┐  ┌──────▼─────┐  ┌───▼──────────┐
  full duplex)        │ Endpointer │  │ Responder  │  │ Speaker      │
                      │ VAD+STT    │  │ rules →    │  │ sentence-    │
                      │ (existing  │  │ LLM stream │  │ streamed TTS │
                      │ vad.py,    │  │ (ollama    │  │ (existing    │
                      │ stt.py,    │  │ stream:true│  │ tts.py       │
                      │ RingBuffer)│  │ + intent   │  │ Kokoro)      │
                      └────────────┘  │ classifier)│  └──────────────┘
                                      └──────┬─────┘
                          conversation? ◄────┴────► action?
                          answer directly        governor.dispatch()   ← RULE 3 intact
                          (token stream)         async + spoken ack
                                                 completion → nudge → spoken
```

### 4.1 Component mapping (existing → role)

| Existing module | Role in fast path | Change needed |
|---|---|---|
| `core/voice/conversation_manager.py` | turn-taking FSM, session, interrupt | none — finally gets used |
| `core/voice/vad.py` `VoiceActivityDetector` | endpointing + barge-in detection | none |
| `core/voice/streamer.py` `RingBuffer` | rolling audio buffer for incremental STT | none |
| `core/voice/stt.py` | transcription | add `realtime_model` config (small model); keep `large-v3` for ambient notes |
| `core/voice/tts.py` | speech out | expose `speak_sentences(iterator)` — `_chunk_sentences` overlap logic already exists; add `cancel()` |
| `core/security/rules_engine.py` | instant no-LLM answers | none — call first, before LLM |
| `core/personality/` PersonalityEngine | system prompt + tone/speed | cache instance (today it's re-constructed per request) |
| `core/city/governor.py` | action execution | none — fast path calls `dispatch()` for action intents |
| `core/loop/nudge_engine.py` | proactive speech source | add `subscribe(callback)` (today: push/queue only) |
| `core/event_bus/` | wake think_loop on voice events | publish `VOICE_INTENT`; think_loop subscribes instead of polling `_pending_voice` |
| `core/api/routers/voice_ws.py` | transport | becomes thin: WS frames in/out, delegates to `RealtimeConversation` |
| frontend `js/audio.js` / `speech.js` | mic + playback | stream PCM frames continuously; handle `stop_audio` event |

## 5. WebSocket protocol (`/voice/stream` v2)

Client → server (continuous, no "end of recording" needed):
```json
{"type": "pcm", "data": "<base64 16kHz mono int16 frame, 20–30ms>"}
{"type": "control", "action": "end_session" | "mute"}
```

Server → client (events, in order of a typical turn):
```json
{"type": "state",            "value": "LISTENING|USER_SPEAKING|PROCESSING|VECTOR_SPEAKING"}
{"type": "partial_transcript","text": "what's my atten"}
{"type": "final_transcript", "text": "what's my attendance"}
{"type": "token",            "text": "Your"}                       // optional HUD display
{"type": "sentence_audio",   "data": "<b64 wav>", "seq": 0}
{"type": "stop_audio"}                                             // barge-in: client flushes player
{"type": "action_ack",       "task_id": "task_...", "text": "On it."}
{"type": "done"}
```

The `state` events drive the HUD orb (existing `_orb()` broadcast keeps working).

## 6. Turn lifecycle

1. **LISTENING** — frames accumulate in `RingBuffer`; VAD watches.
2. VAD speech-start → **USER_SPEAKING**; every ~500ms run incremental faster-whisper decode
   over the buffered utterance → emit `partial_transcript`.
3. VAD silence > 280ms → endpoint. Final decode → `final_transcript` → **PROCESSING**.
4. **Responder** resolves, in order:
   a. `rules_engine.match(text)` → instant canned answer (no LLM, ~ms);
   b. intent classification (one cheap LLM call OR keyword map reused from
      `_TAG_TO_ACTION` in `autonomous_loop.py`):
      - **chat** → Ollama `stream:true` with personality system prompt; tokens flow to Speaker;
      - **action** → speak ack immediately ("On it"), `asyncio.create_task(governor.dispatch(task))`,
        publish `VOICE_INTENT` to event bus. Completion lands in nudge engine → spoken (see §8).
5. **VECTOR_SPEAKING** — Speaker pulls tokens, cuts at sentence boundaries
   (reuse `_chunk_sentences`), Kokoro-synthesizes sentence N+1 while N plays client-side,
   emits `sentence_audio` frames.
6. Last sentence flushed → `done` → **LISTENING** (session stays open; `has_timed_out()`
   → `IDLE` and require wake word again).

## 7. Barge-in

While **VECTOR_SPEAKING**, inbound frames still run through VAD:

- speech detected for >120ms (debounce against echo/noise) →
  `conversation_manager.interrupt()` (FSM already validates this transition) →
  cancel the LLM token task + TTS synth task → send `stop_audio` → **LISTENING**,
  and the frames that triggered the interrupt seed the next utterance buffer.
- Echo guard: client mutes/attenuates mic-loopback while playing, or sends
  `playing:true` flag; server raises VAD threshold during playback. Start simple
  (threshold bump); add proper AEC only if false triggers are annoying.

## 8. Proactive speech (JARVIS speaks first)

- `nudge_engine` gets `subscribe(cb)`; `RealtimeConversation` registers.
- A nudge with priority ≥ threshold is spoken IF: presence says owner is active
  (`core/loop/presence.py`), conversation state is `IDLE`/`LISTENING`, and quiet-hours
  config allows it. Otherwise it stays in the queue (today's behavior).
- Spoken form: short one-liner via TTS + HUD toast. Action completions from §6
  flow through this same path: "That research digest you asked for is ready."

## 9. Config additions (`core/config.py` → `voice`)

```yaml
voice:
  realtime_enabled: true
  realtime_stt_model: "distil-small.en"   # large-v3 stays for ambient/notes
  endpoint_silence_ms: 280
  bargein_enabled: true
  bargein_debounce_ms: 120
  proactive_speech: true
  proactive_min_priority: 0.7
  quiet_hours: "00:00-08:00"
```

## 10. Implementation plan (each phase ships value alone)

| Phase | Change | Files | Effort | Latency after |
|---|---|---|---|---|
| **1** | Ollama `stream:true` + sentence-streamed TTS in existing voice_ws | `voice_ws.py`, `tts.py` | ~1 day | ~2–3s, feels alive |
| **2** | Continuous PCM + server VAD endpointing + partial STT; new `realtime.py`; FSM wired | `realtime.py` (new), `voice_ws.py`, frontend `audio.js` | 2–3 days | ≤1.5s |
| **3** | Barge-in (cancel + `stop_audio` + echo guard) | `realtime.py`, `tts.py`, frontend | 1–2 days | adds interruption |
| **4** | Intent split: chat vs action; governor handoff + spoken ack; `VOICE_INTENT` event wakes think_loop (kill the 10s `_pending_voice` poll) | `realtime.py`, `autonomous_loop.py`, `event_bus/wiring.py` | 1–2 days | actions feel instant |
| **5** | Proactive speech: nudge subscribe + presence + quiet hours | `nudge_engine.py`, `realtime.py` | 1 day | JARVIS speaks first |

Suggested order strictly 1→5. Phase 1 is the 80/20.

## 11. Trade-offs & risks

- **Small STT model for realtime** (distil-small vs large-v3): ~2–4% WER increase on
  conversational English for ~10x speed. Mitigation: rules engine and intent map are
  forgiving; keep large-v3 for ambient transcription where accuracy matters.
- **Echo/false barge-in**: cheapest guard is VAD threshold bump during playback; real AEC
  (e.g. speexdsp) only if needed. Risk: clipping VECTOR's own voice triggering interrupt —
  the 120ms debounce handles most of it.
- **Incremental Whisper decode cost**: re-decoding a growing buffer every 500ms is O(n²)-ish
  for long utterances; cap utterance at 30s (RingBuffer already bounded) — fine for speech.
- **Two response paths** (fast conversational vs think_loop autonomy): risk of divergent
  personality. Mitigation: both use PersonalityEngine; fast path stores every turn in
  EpisodicMemory exactly like the bypass path already does.
- **Safety unchanged**: fast path answers *questions* directly but every *action* still
  routes `governor.dispatch()` → PermissionGateway classification. Prompt-injection scan
  (`_scan_incoming`) runs on final transcripts before they reach the LLM.

## 12. Revisit later

- Speaker verification: embed utterances (resemblyzer/ECAPA) and gate YELLOW/RED actions
  on owner-voice match — `voice_profiles.py` is the natural home.
- Whisper streaming variants (whisper-streaming / WhisperLive) if incremental decode
  proves too slow on your GPU.
- Local LLM TTFT tuning: keep `vector-focus` warm with `keep_alive: -1` in Ollama.
