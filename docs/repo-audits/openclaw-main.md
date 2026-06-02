# openclaw-main Audit

**Repo:** OpenClaw — TypeScript personal AI assistant (MIT)
**Audited:** 2026-06-02

---

## 1. Repo Reality

OpenClaw is a deep TypeScript personal assistant with:
- 22+ platform channels (Telegram, WhatsApp, Discord, Slack, email, SMS, etc.)
- Voice pipeline (STT + TTS)
- Image generation via provider registry (ComfyUI, Stable Diffusion, DALL-E, Midjourney, Replicate)
- Video generation via provider registry (RunwayML, Pika, Kling)
- Canvas/WebView bridge to iOS/macOS/Android native apps
- 50+ Claude Code skills
- Daemon mode (autonomous 24/7)
- Per-channel DM security policy (pairing codes, allowlists)
- `ImageGenProviderRegistry` + `VideoGenProviderRegistry` — unified provider routing with fallbacks

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Verified output | Status |
|---------|------------------|-----------------|--------|
| 30+ channel adapters | `vectorcode/src/channels/` (40+ adapters) | ✅ | ✅ |
| Voice pipeline (STT+TTS) | `core/voice/` (Whisper + Kokoro) | ✅ | ✅ |
| Image gen | `districts/content/comfyui_adapter.py` | ComfyUIAdapter OK | ⚠️ hardcoded ComfyUI only |
| Video gen | `districts/content/video_generator.py` | ✅ | ⚠️ hardcoded SadTalker |
| Image provider registry | ❌ No provider registry (hardcoded) | image_providers.py: False | ❌ |
| Video provider registry | ❌ No provider registry (hardcoded) | video_providers.py: False | ❌ |
| Per-channel security policy | ❌ No pairing codes / allowlists | N/A | ❌ |
| Canvas WebView bridge | ❌ Windows-only VECTOR (not mobile) | N/A | N/A |

---

## 3. Frontend: TypeScript app — not absorbable as HUD

---

## 4. Verdict

**PATCH VECTOR** — Two gaps worth porting to Python:
1. `ImageGenProviderRegistry` — unified image gen with cloud fallbacks (Replicate → Stability → DALL-E)
2. Per-channel DM security policy (pairing codes, allowlist) — for vectorcode channel security

**Delete-readiness:** DELETE-AFTER porting the 2 registries.

---

## 5. Gaps

| ID | Issue | File:line | Severity |
|----|-------|-----------|----------|
| G1 | No image gen provider registry — hardcoded ComfyUI only, no cloud fallback | `districts/content/comfyui_adapter.py` | MED |
| G2 | No video gen provider registry — hardcoded SadTalker only | `districts/content/video_generator.py` | MED |
| G3 | No per-channel DM security policy (pairing codes, allowlists) | `vectorcode/src/channels/` | LOW |
