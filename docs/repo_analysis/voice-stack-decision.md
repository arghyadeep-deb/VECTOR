# VECTOR Voice Stack Decision

**Status:** Decision note for Sonnet

**Decision:** Do not implement every voice repo. Use **OmniVoice + one fast live engine** as the target stack.

## Why

VECTOR now has too many voice candidates:

- `voicebox`
- `VoxCPM`
- `supertonic`
- `OmniVoice`
- existing Kokoro / pyttsx3 / gTTS paths

Implementing all of them would create duplicate engines, confusing routing, extra VRAM pressure, more tests, more failure modes, and unclear defaults.

## Final Stack

### 1. Live Conversation

Use the current live engine first:

- **Current default:** Kokoro
- **Possible upgrade:** supertonic, only if benchmark proves it is faster/better and truly low-VRAM or CPU-friendly

Live conversation needs low latency more than perfect voice quality.

### 2. High-Quality Voice Studio

Use **OmniVoice** as the main candidate for:

- voice cloning
- voice design
- multilingual TTS
- narration
- content voiceovers
- British VECTOR persona voice
- Hindi/Bengali/Assamese experiments

OmniVoice should be lazy-loaded, optional, and benchmarked before replacing anything.

### 3. Fallbacks

Keep existing fallbacks:

- `pyttsx3` for always-available local fallback
- `gTTS` only for languages/local failures where needed

Do not remove fallbacks until OmniVoice is tested per language.

## What To Skip Or Hold

### voicebox

Skip.

Reason: already absorbed/superseded. No need to revisit unless a very specific missing feature appears.

### VoxCPM

Hold.

Reason: OmniVoice overlaps VoxCPM heavily in cloning and voice design. Revisit VoxCPM only if OmniVoice fails:

- British voice design quality
- cloning similarity
- VRAM usage
- setup reliability
- multilingual quality

### supertonic

Benchmark only as a live-engine candidate.

Reason: if it is genuinely fast and low-resource, it may replace Kokoro for live conversation. It should not compete with OmniVoice for high-quality studio generation.

## Implementation Order

1. Benchmark OmniVoice.
2. Add lazy OmniVoice adapter for Voice Studio only.
3. Keep Kokoro as live default.
4. Benchmark supertonic separately for live conversation.
5. Decide whether supertonic replaces Kokoro.
6. Revisit VoxCPM only if OmniVoice fails the high-quality voice role.

## Acceptance Criteria

- Only one live TTS default exists.
- Only one high-quality cloning/design engine is active by default.
- OmniVoice does not load at VECTOR startup.
- Heavy voice models respect the model-residency lock.
- Existing voice tests continue passing.
- Fallbacks remain available.

## Final Recommendation

The sane VECTOR voice stack is:

- **Live conversation:** Kokoro now, maybe supertonic later
- **High-quality cloning/design/multilingual:** OmniVoice
- **Fallback:** pyttsx3 / gTTS
- **Hold:** VoxCPM
- **Skip:** voicebox
