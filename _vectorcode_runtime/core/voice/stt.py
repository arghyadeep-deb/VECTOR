"""VECTOR Speech-to-Text — multi-engine adapter.

Selects an STT engine based on CONFIG['voice']['stt_engine']:
  • "whisper"        — OpenAI Whisper (default, local, no API key)
  • "faster_whisper" — faster-whisper (local, ~4x faster than whisper)
  • "deepgram"       — Deepgram Nova (cloud, low-latency, requires API key)
  • "openai"         — OpenAI Whisper API (cloud)

All engines expose:
  - transcribe(audio_np, sample_rate=16000) -> str
  - record_and_transcribe(duration_sec=None) -> str

Backwards compatible: WhisperSTT class is preserved for any existing imports.
The new STT() factory picks the engine; if the chosen one fails to load, falls
back to Whisper local.
"""

__all__ = [
    "DeepgramSTT",
    "FasterWhisperSTT",
    "STT",
    "WhisperSTT",
]


import re

import numpy as np
from loguru import logger

from core.config import CONFIG

# Cap for quiet-mic normalization. Uncapped `0.9/peak` turned a ~0.001 noise
# floor into full-scale hiss and fed it to Whisper (2026-07-17).
_MAX_NORMALIZE_GAIN = 8.0

# Whisper's well-known silence/noise artifacts — it emits these when handed
# near-silence (they come from its YouTube-subtitle training data). Real speech
# is protected: only unmistakable artifacts are listed, so a genuine "thanks"
# from the owner still gets through as part of a longer utterance.
_HALLUCINATION_EXACT = {
    "thanks for watching", "thanks for watching!", "thank you for watching",
    "thank you for watching!", "please subscribe", "like and subscribe",
    "subtitles by the amara.org community", "amara.org", "www.mooji.org",
    "subtitles by", "transcription by castingwords", "bye", "you",
    # 2026-07-21 browser dogfood: these leaked through and were injected into
    # the HUD chat as phantom owner messages ("I'll see you in the next
    # video.", "Thanks for watching. Have a great week.", "Thank you.").
    "thank you", "thanks", "i'll see you in the next video",
    "see you in the next video", "see you in the next one",
    "i'll see you in the next one", "have a great week", "have a great day",
    "thanks for listening", "thank you for listening",
    "don't forget to subscribe", "the end", "so", "okay", "oh",
}


def _is_hallucination(text: str, lang_pinned: str = "") -> bool:
    """True when a transcript is a Whisper silence artifact rather than speech."""
    t = (text or "").strip()
    if not t:
        return True
    low = t.lower().strip(" .!?,-—…")
    if not low or low in _HALLUCINATION_EXACT:
        return True
    # Multi-sentence artifacts ("Thanks for watching. Have a great week.") —
    # if EVERY sentence is individually a known artifact, the whole thing is
    # one. Real speech is protected: any single non-artifact sentence passes.
    parts = [p.strip(" .!?,-—…") for p in re.split(r"[.!?]+", low) if p.strip(" .!?,-—…")]
    if parts and all(p in _HALLUCINATION_EXACT for p in parts):
        return True
    # Pure punctuation / symbol soup.
    if not re.search(r"[a-z0-9ऀ-ॿঀ-৿぀-ヿ一-鿿]", low):
        return True
    # Language is pinned to English but Whisper produced no Latin letters at all
    # (e.g. 'ぷいっ', 'ᶅᶁᶇᶅ ᶠᶅᶜᶦᶉ') — that is invented, not the owner speaking.
    if lang_pinned.startswith("en") and not re.search(r"[a-z]", low):
        return True
    return False


# ── Whisper (local, default) ─────────────────────────────────────────────────


class WhisperSTT:
    """OpenAI Whisper, local — no API key.

    VRAM requirements: large-v3 ~10 GB fp32 (falls back to medium when insufficient).
    """

    name = "whisper"

    # VRAM floor (GB) required to load each model size at fp32.
    _VRAM_REQUIREMENTS: dict = {"large-v3": 10.0, "large": 10.0, "medium": 5.0, "small": 2.0}

    def __init__(self):
        self._model = None
        self._model_name = CONFIG.get("voice", {}).get("whisper_model", "large-v3")

    def _select_model(self) -> str:
        """Return model name, downgrading to 'medium' when GPU VRAM is insufficient."""
        name = self._model_name
        required_gb = self._VRAM_REQUIREMENTS.get(name, 0.0)
        if required_gb > 0.0:
            try:
                import torch
                if torch.cuda.is_available():
                    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
                    if vram_gb < required_gb:
                        logger.warning(
                            "[VECTOR][stt:whisper] '{}' needs ~{:.0f} GB VRAM; "
                            "{:.1f} GB available — falling back to 'medium'",
                            name, required_gb, vram_gb,
                        )
                        return "medium"
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass
        return name

    def _load(self):
        if self._model is None:
            try:
                import whisper
                effective = self._select_model()
                logger.info(f"[VECTOR][stt:whisper] Loading model '{effective}'")
                self._model = whisper.load_model(effective)
                logger.info("[VECTOR][stt:whisper] ready")
            except Exception as e:
                logger.error(f"[VECTOR][stt:whisper] Failed to load: {e}")
                self._model = None

    def transcribe(self, audio_np: np.ndarray, sample_rate: int = 16000) -> str:
        try:
            self._load()
            if self._model is None:
                return ""
            if audio_np.dtype != np.float32:
                audio_np = audio_np.astype(np.float32) / 32768.0
            lang = (CONFIG.get("voice", {}).get("stt_language") or "").strip()
            result = self._model.transcribe(audio_np, fp16=False,
                                            language=lang or None,
                                            condition_on_previous_text=False)
            text = result.get("text", "").strip()
            if _is_hallucination(text, lang):
                logger.debug(f"[VECTOR][stt:whisper] discarded artifact: {text!r}")
                return ""
            logger.info(f"[VECTOR][stt:whisper] '{text}'")
            return text
        except Exception as e:
            logger.error(f"[VECTOR][stt:whisper] Transcription failed: {e}")
            return ""

    def record_until_silence(
        self,
        sample_rate: int | None = None,
        # 0.0012 (was 0.01): laptop mic arrays at default Windows input levels
        # produce speech at rms ~0.003 — the old gate never detected speech.
        silence_rms: float = 0.0012,
        post_silence_s: float = 0.6,
        max_s: float = 8.0,
    ) -> "np.ndarray":
        """VAD recording: stream 100ms chunks, stop 600ms after speech ends. Max 8s."""
        import queue as _q
        import numpy as np
        import sounddevice as sd
        sr = sample_rate or CONFIG.get("voice", {}).get("sample_rate", 16000)
        chunk = int(sr * 0.1)
        q: _q.Queue = _q.Queue()
        frames: list = []
        speech_started = False
        silence_frames = 0
        max_frames = int(max_s / 0.1)
        silence_threshold = int(post_silence_s / 0.1)

        def _cb(indata, *_):
            q.put(indata.copy())

        logger.info("[VECTOR][stt:whisper] VAD recording (max {}s)...", max_s)
        with sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                            blocksize=chunk, callback=_cb):
            while len(frames) < max_frames:
                frame = q.get().flatten()
                frames.append(frame)
                rms = float(np.sqrt(np.mean(frame ** 2)))
                if rms > silence_rms:
                    speech_started = True
                    silence_frames = 0
                elif speech_started:
                    silence_frames += 1
                    if silence_frames >= silence_threshold:
                        break

        # No speech at all ⇒ return EMPTY, never a block of silence. Handing
        # Whisper 8s of silence is what made it hallucinate ("Thank you.",
        # Japanese, gibberish) — those phantom utterances then hit the speaker
        # gate and made VECTOR announce "I only talk with Arghyadeep" at nobody
        # (2026-07-17 fix).
        if not speech_started:
            logger.debug("[VECTOR][stt] VAD: no speech in {}s — no transcription", max_s)
            return np.zeros(0, dtype="float32")

        audio = np.concatenate(frames) if frames else np.zeros(0, dtype="float32")
        logger.info("[VECTOR][stt:whisper] VAD captured {}s", round(len(audio) / sr, 1))
        return audio

    def record_and_transcribe(self, duration_sec: float | None = None) -> str:
        """Record with VAD (dynamic end-of-speech), falling back to fixed duration."""
        try:
            import numpy as np
            sample_rate = CONFIG.get("voice", {}).get("sample_rate", 16000)
            audio = self.record_until_silence(sample_rate=sample_rate)
            if audio is None or audio.size == 0:
                return ""  # silence — do not feed Whisper
            # Normalize quiet-mic audio so Whisper gets a usable signal level.
            # Gain is CAPPED: the old `0.9 / peak` multiplied a ~0.001 noise floor
            # by ~900x, boosting room hiss to full scale — which is exactly what
            # Whisper then "transcribed" into phantom speech (2026-07-17 fix).
            peak = float(np.max(np.abs(audio)))
            if 0 < peak < 0.3:
                audio = audio * min(0.9 / peak, _MAX_NORMALIZE_GAIN)
            return self.transcribe(audio, sample_rate)
        except Exception as e:
            logger.error(f"[VECTOR][stt:whisper] Record failed: {e}")
            return ""


# ── faster-whisper (local, faster) ───────────────────────────────────────────


class FasterWhisperSTT:
    """faster-whisper — ~4x throughput vs vanilla Whisper, same accuracy.

    VRAM requirements: large-v3 ~6 GB fp16 (falls back to medium when insufficient).
    """

    name = "faster_whisper"

    # VRAM floor (GB) at fp16 for each model size.
    _VRAM_REQUIREMENTS: dict = {"large-v3": 6.0, "large": 6.0, "medium": 3.0, "small": 1.5}

    def __init__(self):
        self._model = None
        self._model_name = CONFIG.get("voice", {}).get("whisper_model", "large-v3")

    def _select_model(self) -> str:
        """Return model name, downgrading to 'medium' when GPU VRAM is insufficient."""
        name = self._model_name
        required_gb = self._VRAM_REQUIREMENTS.get(name, 0.0)
        if required_gb > 0.0:
            try:
                import torch
                if torch.cuda.is_available():
                    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
                    if vram_gb < required_gb:
                        logger.warning(
                            "[VECTOR][stt:faster_whisper] '{}' needs ~{:.0f} GB VRAM (fp16); "
                            "{:.1f} GB available — falling back to 'medium'",
                            name, required_gb, vram_gb,
                        )
                        return "medium"
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass
        return name

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel  # type: ignore[import]
                device = CONFIG.get("voice", {}).get("device", "cuda")
                compute = CONFIG.get("voice", {}).get("compute_type", "float16")
                effective = self._select_model()
                logger.info(
                    f"[VECTOR][stt:faster_whisper] Loading '{effective}' "
                    f"on {device} ({compute})"
                )
                self._model = WhisperModel(effective, device=device, compute_type=compute)
                logger.info("[VECTOR][stt:faster_whisper] ready")
            except Exception as e:
                logger.error(f"[VECTOR][stt:faster_whisper] Failed to load: {e}")
                self._model = None

    def transcribe(self, audio_np: np.ndarray, sample_rate: int = 16000) -> str:
        try:
            self._load()
            if self._model is None:
                return ""
            if audio_np.dtype != np.float32:
                audio_np = audio_np.astype(np.float32) / 32768.0
            lang = (CONFIG.get("voice", {}).get("stt_language") or "").strip()
            segments, _info = self._model.transcribe(
                audio_np,
                beam_size=5,
                language=lang or None,          # pinned (default en) — stops
                                                # random-script transcripts
                vad_filter=True,                # drop non-speech before decoding
                condition_on_previous_text=False,  # stops hallucination loops
            )
            # 2026-10-25 (background-noise hallucination): _is_hallucination()
            # below only catches a fixed list of KNOWN Whisper silence
            # artifacts ("thanks for watching", etc) -- it can't catch a novel
            # but grammatically plausible sentence invented from ambient noise
            # (observed live: "for all of us that have sought to talk to you"
            # from room noise, no one speaking). faster-whisper scores every
            # segment's own confidence that it's real speech; keep only
            # segments where BOTH signals agree it's probably not noise.
            # Thresholds follow faster-whisper's own documented guidance for
            # distinguishing speech from noise/silence segments.
            all_segs = list(segments)  # materialize once -- faster-whisper yields a generator
            kept = [
                s for s in all_segs
                if not (s.no_speech_prob > 0.6 and s.avg_logprob < -0.8)
            ]
            dropped = bool(all_segs) and not kept
            text = " ".join(s.text.strip() for s in kept).strip()
            if dropped:
                logger.debug(
                    "[VECTOR][stt:faster_whisper] discarded low-confidence segment(s) "
                    "(likely background noise, not speech)"
                )
                return ""
            if _is_hallucination(text, lang):
                logger.debug(f"[VECTOR][stt:faster_whisper] discarded artifact: {text!r}")
                return ""
            logger.info(f"[VECTOR][stt:faster_whisper] '{text}'")
            return text
        except Exception as e:
            logger.error(f"[VECTOR][stt:faster_whisper] failed: {e}")
            return ""

    def record_until_silence(self, *args, **kwargs) -> "np.ndarray":
        # Mic capture is backend-independent — reuse Whisper's VAD recorder.
        return WhisperSTT.record_until_silence(self, *args, **kwargs)  # type: ignore[arg-type]

    def record_and_transcribe(self, duration_sec: float | None = None) -> str:
        return WhisperSTT.record_and_transcribe(self, duration_sec)  # type: ignore[arg-type]

    async def transcribe_stream(self, audio_stream, callback: callable) -> str:
        try:
            self._load()
            if self._model is None:
                return ""
            all_chunks = []
            async for chunk in audio_stream:
                all_chunks.append(chunk)
                if chunk.dtype != np.float32:
                    chunk = chunk.astype(np.float32) / 32768.0
                segments, _info = self._model.transcribe(chunk, beam_size=5)
                partial = " ".join(s.text.strip() for s in segments)
                if partial:
                    callback(partial)
            if not all_chunks:
                return ""
            full_audio = np.concatenate(all_chunks)
            if full_audio.dtype != np.float32:
                full_audio = full_audio.astype(np.float32) / 32768.0
            segments, _info = self._model.transcribe(full_audio, beam_size=5)
            final = " ".join(s.text.strip() for s in segments)
            logger.info(f"[VECTOR][stt:faster_whisper] stream final: '{final}'")
            return final
        except Exception as e:
            logger.error(f"[VECTOR][stt:faster_whisper] stream failed: {e}")
            return ""


# ── Deepgram (cloud, low-latency) ────────────────────────────────────────────


class DeepgramSTT:
    """Deepgram Nova — fastest cloud STT. Requires DEEPGRAM_API_KEY env var."""

    name = "deepgram"

    def __init__(self):
        import os
        self._api_key = os.environ.get("DEEPGRAM_API_KEY", "")

    def transcribe(self, audio_np: np.ndarray, sample_rate: int = 16000) -> str:
        if not self._api_key:
            logger.warning("[VECTOR][stt:deepgram] DEEPGRAM_API_KEY missing — cannot transcribe")
            return ""
        try:
            import io
            import soundfile as sf  # type: ignore[import]
            import httpx
            buf = io.BytesIO()
            sf.write(buf, audio_np, sample_rate, format="WAV")
            buf.seek(0)
            r = httpx.post(
                "https://api.deepgram.com/v1/listen?model=nova-2&punctuate=true",
                headers={"Authorization": f"Token {self._api_key}",
                         "Content-Type": "audio/wav"},
                content=buf.read(),
                timeout=30.0,
            )
            r.raise_for_status()
            data = r.json()
            text = (
                data.get("results", {})
                .get("channels", [{}])[0]
                .get("alternatives", [{}])[0]
                .get("transcript", "")
            )
            logger.info(f"[VECTOR][stt:deepgram] '{text}'")
            return text
        except Exception as e:
            logger.error(f"[VECTOR][stt:deepgram] failed: {e}")
            return ""

    def record_until_silence(self, *args, **kwargs) -> "np.ndarray":
        # Mic capture is backend-independent — reuse Whisper's VAD recorder.
        return WhisperSTT.record_until_silence(self, *args, **kwargs)  # type: ignore[arg-type]

    def record_and_transcribe(self, duration_sec: float | None = None) -> str:
        return WhisperSTT.record_and_transcribe(self, duration_sec)  # type: ignore[arg-type]


# ── Engine selector ──────────────────────────────────────────────────────────


_ENGINES = {
    "whisper": WhisperSTT,
    "faster_whisper": FasterWhisperSTT,
    "deepgram": DeepgramSTT,
}


def STT():
    """Return the configured STT engine. Falls back to Whisper local on failure."""
    engine_name = (CONFIG.get("voice", {}).get("stt_engine") or "whisper").lower()
    cls = _ENGINES.get(engine_name)
    if cls is None:
        logger.warning(f"[VECTOR][stt] Unknown engine '{engine_name}' — using whisper")
        cls = WhisperSTT
    try:
        instance = cls()
        logger.info(f"[VECTOR][stt] engine = {instance.name}")
        return instance
    except Exception as e:
        logger.warning(f"[VECTOR][stt] '{engine_name}' init failed: {e} — falling back to whisper")
        return WhisperSTT()