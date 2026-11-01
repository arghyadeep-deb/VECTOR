
from xml.sax.saxutils import escape as _xml_escape
import sys
import uuid
import tempfile
from pathlib import Path
from typing import Optional

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

class VoiceGenerator(AgentBase):
    """
    Generates AI voice audio from text and supports voice cloning
    from audio samples.
    """

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "VoiceGenerator", "content")
        self.capabilities = ["adjust_voice_speed", "clone_voice", "content", "generate", "generate_batch", "generate_in_my_voice", "generate_voice", "get_voices", "text_to_ssml", "tts", "voice"]
        if ghost:
            self.inherit_ghost(ghost)

        self._voice_config = CONFIG.get("voice", {})
        self._kokoro_dir = Path(self._voice_config.get("kokoro_model_dir", "./models/kokoro"))
        self._available = self._check_tts()
        self._generated_voices: list[dict] = []
        self._omnivoice_config = None  # lazy — resolved from CONFIG on first studio call
        logger.info(f"[VECTOR][voice_generator] VoiceGenerator initialized - TTS: {self._available}")

    def _check_tts(self) -> bool:
        """Check if TTS engine is available."""
        if self._kokoro_dir.exists():
            return True
        try:
            import kokoro_onnx
            return True
        except ImportError:
            logger.warning("[VECTOR][voice_generator] Kokoro TTS not available")
            return False

    def _load_kokoro(self):
        """The installed kokoro_onnx API: Kokoro(model_path, voices_path), created once and cached.

        generate_voice() used to call `kokoro_onnx.load_model(...)` / `model.create_audio(...)` -- functions that do not
        exist in this package -- so it failed on every call with "no attribute 'load_model'" (loop watch, 2026-09-26).
        Mirrors core/voice/tts.py: prefer the GPU fp16 model when CUDA is available, keep the first that loads.
        """
        if getattr(self, "_kokoro", None) is not None:
            return self._kokoro
        from kokoro_onnx import Kokoro

        voices_file = self._kokoro_dir / "voices-v1.0.bin"
        gpu_model = self._kokoro_dir / "kokoro-v1.0.fp16-gpu.onnx"
        cpu_model = self._kokoro_dir / "kokoro-v1.0.onnx"
        candidates = [cpu_model, gpu_model]
        try:
            import onnxruntime as ort
            if "CUDAExecutionProvider" in ort.get_available_providers():
                candidates = [gpu_model, cpu_model]
        except Exception:
            logger.debug("[VECTOR][voice_generator] onnxruntime probe failed; using CPU-first order")
        last_err: Exception | None = None
        for model_file in candidates:
            if not (model_file.exists() and voices_file.exists()):
                continue
            try:
                self._kokoro = Kokoro(str(model_file), str(voices_file))
                return self._kokoro
            except Exception as e:  # a corrupt/truncated model must not hide a working one
                last_err = e
                logger.warning("[VECTOR][voice_generator] Kokoro model {} failed to load: {}", model_file.name, e)
        raise RuntimeError(f"no loadable Kokoro model in {self._kokoro_dir}" + (f": {last_err}" if last_err else ""))

    def generate_voice(self, text: str, voice_name: Optional[str] = None,
                       output_path: Optional[str] = None) -> dict:
        """
        Generate speech from text using Kokoro TTS. `voice_name` defaults to VECTOR's configured voice
        (core.voice.tts._voice_for, owner rule: male voices only).
        """
        if voice_name is None:
            try:
                from core.voice.tts import _voice_for
                voice_name = _voice_for("en")
            except Exception:
                voice_name = "bm_george"
        if not self._available:
            return {"status": "error", "message": "TTS engine not available"}

        if output_path is None:
            from core.runtime_paths import data_path

            output_dir = data_path("voice_output")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"voice_{uuid.uuid4().hex[:8]}.wav")

        try:
            import numpy as np
            import scipy.io.wavfile as wavfile

            model = self._load_kokoro()
            audio_samples, sample_rate = model.create(text, voice=voice_name, speed=self._voice_config.get("kokoro_speed", 1.0))

            audio_int16 = (np.clip(audio_samples, -1.0, 1.0) * 32767).astype(np.int16)
            wavfile.write(output_path, sample_rate, audio_int16)

            result = {
                "status": "success",
                "output_path": output_path,
                "duration_sec": len(audio_samples) / sample_rate,
                "voice": voice_name,
                "text_length": len(text)
            }

            self._generated_voices.append(result)
            self.award_points(10, "voice_generated")

            logger.info(f"[VECTOR][voice_generator] Generated voice: {output_path}")
            return result

        except ImportError:
            return {"status": "error", "message": "kokoro_onnx not installed"}
        except Exception as e:
            logger.error(f"[VECTOR][voice_generator] Voice generation failed: {e}")
            return {"status": "error", "message": str(e)}

    def _get_omnivoice_engine(self):
        """Lazily build the OmniVoice adapter. Separate method so tests can
        monkeypatch it without touching the real config or loading the
        (likely not pip-installed) omnivoice package. Reuses
        OmniVoiceEngine.from_vector_config() — don't re-read CONFIG here."""
        from core.voice.engines.omnivoice_engine import OmniVoiceEngine

        if self._omnivoice_config is None:
            self._omnivoice_config = OmniVoiceEngine.from_vector_config()
        return OmniVoiceEngine(self._omnivoice_config)

    def generate_voice_studio(self, text: str, language: str = "en",
                               output_path: Optional[str] = None) -> dict:
        """High-quality content-generation voice path (docs/repo_analysis/
        omnivoice.md's "Voice Studio" — distinct from the always-on live
        conversation engine, which never touches OmniVoice regardless of
        this config). Tries OmniVoice first when enabled; falls back to
        Kokoro (generate_voice) on any failure or when disabled, never
        raising to the caller.
        """
        if self._omnivoice_config is None:
            from core.voice.engines.omnivoice_engine import OmniVoiceEngine
            self._omnivoice_config = OmniVoiceEngine.from_vector_config()

        if not self._omnivoice_config.enabled:
            result = self.generate_voice(text, output_path=output_path)
            result["engine"] = "kokoro"
            return result

        try:
            engine = self._get_omnivoice_engine()
            path = engine.synthesize_to_file(text, language=language, output_path=output_path)
            return {"status": "success", "engine": "omnivoice", "output_path": path}
        except Exception as exc:
            logger.warning("[VECTOR][voice_generator] OmniVoice failed, falling back to Kokoro: {}", exc)
            result = self.generate_voice(text, output_path=output_path)
            result["engine"] = "kokoro"
            result["fallback_reason"] = f"omnivoice failed: {exc}"
            return result

    def generate_in_my_voice(self, text: str, profile_name: str = "owner",
                             output_path: Optional[str] = None) -> dict:
        """
        Render a content script to audio in the owner's cloned voice — LOCAL, free,
        private. Uses VoiceTTS.synthesize_to_file → VoiceCloner (chatterbox-tts) with
        the named voice profile's reference sample. Falls back to Kokoro if cloning
        is unavailable. This is the primary path for 'content script → my voice'.

        Args:
            text:         the script text (any length — chunked + crossfaded)
            profile_name: voice profile holding your reference sample (default "owner")
            output_path:  where to write the .wav (auto-generated under data/voice_output if None)
        """
        if output_path is None:
            from core.runtime_paths import data_path

            output_dir = data_path("voice_output")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"myvoice_{uuid.uuid4().hex[:8]}.wav")
        try:
            from core.voice.tts import VoiceTTS
            result = VoiceTTS().synthesize_to_file(text, output_path, profile_name=profile_name)
            if result.get("status") == "ok":
                result["text_length"] = len(text)
                self._generated_voices.append(result)
                self.award_points(25, "voice_generated_local")
            return result
        except Exception as e:
            logger.error(f"[VECTOR][voice_generator] generate_in_my_voice failed: {e}")
            return {"status": "error", "message": str(e)}

    def clone_voice(self, audio_samples: list[str], text: str,
                   output_path: Optional[str] = None) -> dict:
        """
        Clone voice from audio samples and generate speech.
        Note: Voice cloning requires compatible audio samples and may
        need external services like ElevenLabs or Coqui.
        """
        valid_samples = [Path(s) for s in audio_samples if Path(s).exists()]
        if not valid_samples:
            return {"status": "error", "message": "No valid audio samples provided"}

        if output_path is None:
            from core.runtime_paths import data_path

            output_dir = data_path("voice_output")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"cloned_{uuid.uuid4().hex[:8]}.wav")

        try:
            import elevenlabs

            api_key = CONFIG.get("api_keys", {}).get("elevenlabs_key", "")
            if not api_key:
                return self._simulate_voice_clone(audio_samples, text, output_path)

            elevenlabs.api_key = api_key

            voice = elevenlabs.clone(
                name=f"cloned_voice_{uuid.uuid4().hex[:8]}",
                files=audio_samples,
                description="Cloned voice from samples"
            )

            audio = elevenlabs.generate(
                text=text,
                voice=voice
            )

            elevenlabs.save(audio, output_path)

            result = {
                "status": "success",
                "output_path": output_path,
                "source_samples": len(valid_samples),
                "text_length": len(text)
            }

            self._generated_voices.append(result)
            self.award_points(25, "voice_cloned")

            return result

        except ImportError:
            return self._simulate_voice_clone(audio_samples, text, output_path)
        except Exception as e:
            logger.error(f"[VECTOR][voice_generator] Voice cloning failed: {e}")
            return {"status": "error", "message": str(e)}

    def _simulate_voice_clone(self, audio_samples: list[str], text: str,
                             output_path: str) -> dict:
        """Simulate voice cloning when APIs are not available."""
        logger.info("[VECTOR][voice_generator] Simulating voice clone")

        try:
            import numpy as np
            import scipy.io.wavfile as wavfile

            sample_rate = 22050
            duration = min(len(text) / 10, 30)
            samples = int(sample_rate * duration)
            audio = np.random.uniform(-0.1, 0.1, samples).astype(np.float32)

            wavfile.write(output_path, sample_rate, (audio * 32767).astype(np.int16))

            return {
                "status": "success",
                "output_path": output_path,
                "simulated": True,
                "source_samples": len(audio_samples),
                "note": "Simulated - configure ElevenLabs for real cloning"
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_available_voices(self) -> list[dict]:
        """
        Get list of available pre-built voices.
        """
        if not self._available:
            return []

        voices = [
            {"id": "af_heart", "name": "Heart (Female)", "gender": "female", "lang": "en"},
            {"id": "af_bella", "name": "Bella (Female)", "gender": "female", "lang": "en"},
            {"id": "af_nicole", "name": "Nicole (Female)", "gender": "female", "lang": "en"},
            {"id": "af_sarah", "name": "Sarah (Female)", "gender": "female", "lang": "en"},
            {"id": "af_sky", "name": "Sky (Female)", "gender": "female", "lang": "en"},
            {"id": "am_adam", "name": "Adam (Male)", "gender": "male", "lang": "en"},
            {"id": "am_michael", "name": "Michael (Male)", "gender": "male", "lang": "en"},
            {"id": "bf_emma", "name": "Emma (British Female)", "gender": "female", "lang": "en-GB"},
            {"id": "bm_george", "name": "George (British Male)", "gender": "male", "lang": "en-GB"},
        ]

        return voices

    def adjust_voice_speed(self, audio_path: str, speed: float = 1.0,
                          output_path: Optional[str] = None) -> dict:
        """
        Adjust the speed of generated voice audio.
        Speed: 0.5 (slow) to 2.0 (fast), 1.0 is normal.
        """
        audio = Path(audio_path)
        if not audio.exists():
            return {"status": "error", "message": "Audio file not found"}

        if output_path is None:
            output_path = str(audio.parent / f"{audio.stem}_speed{speed}{audio.suffix}")

        try:
            import subprocess

            cmd = [
                "ffmpeg", "-y",
                "-i", str(audio),
                "-filter:a", f"atempo={speed}",
                "-q:a", "0",
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                self.award_points(5, "voice_speed_adjusted")
                return {
                    "status": "success",
                    "output_path": output_path,
                    "speed": speed
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def generate_batch(self, texts: list[str], voice: str = "af_heart",
                       output_dir: Optional[str] = None) -> list[dict]:
        """
        Generate voice audio for multiple texts in batch.
        """
        if output_dir is None:
            from core.runtime_paths import data_path

            output_dir = data_path("voice_output")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for i, text in enumerate(texts):
            output_path = str(output_dir / f"batch_{i}_{uuid.uuid4().hex[:8]}.wav")
            result = self.generate_voice(text, voice, output_path)
            results.append(result)

        self.award_points(len(texts) * 5, "batch_voice_generated")
        return results

    def text_to_ssml(self, text: str, breaks: list[dict] = None) -> str:
        """
        Convert text to SSML (Speech Synthesis Markup Language) for
        better control over TTS output.
        """
        ssml = ['<speak>']

        for sentence in text.split('. '):
            sentence = sentence.strip()
            if not sentence:
                continue

            ssml.append(f'<s>{_xml_escape(sentence)}.</s>')   # 2026-09-27: & < > in a sentence made the SSML invalid XML

        if breaks:
            for b in breaks:
                ssml.append(f'<break time="{b.get("time", "500ms")}"/>')

        ssml.append('</speak>')
        return '\n'.join(ssml)

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = [
            "generate_voice", "generate_in_my_voice", "clone_voice",
            "get_voices", "adjust_voice_speed", "generate_batch", "text_to_ssml",
        ]

        if task_type == "generate_voice":
            return self.generate_voice(p.get("text", ""), p.get("voice_name", "af_heart"), p.get("output_path"))
        if task_type == "generate_in_my_voice":
            return self.generate_in_my_voice(p.get("text", ""), p.get("profile_name", "owner"), p.get("output_path"))
        if task_type == "clone_voice":
            return self.clone_voice(p.get("audio_samples", []), p.get("text", ""), p.get("output_path"))
        if task_type == "get_voices":
            return {"status": "ok", "voices": self.get_available_voices()}
        if task_type == "adjust_voice_speed":
            return self.adjust_voice_speed(p.get("audio_path", ""), p.get("speed", 1.0), p.get("output_path"))
        if task_type == "generate_batch":
            return {"status": "ok", "results": self.generate_batch(p.get("texts", []), p.get("voice", "af_heart"), p.get("output_dir"))}
        if task_type == "text_to_ssml":
            return {"status": "ok", "ssml": self.text_to_ssml(p.get("text", ""), p.get("breaks"))}

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "what voices are available for narrating my video?" previously hit
        # the bare "unhandled type" error stub. Route it to the READ-ONLY,
        # no-required-argument get_available_voices() — never trigger a
        # real TTS render, voice cloning (paid ElevenLabs API), or an
        # ffmpeg subprocess (adjust_voice_speed) from unmatched free text.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            return {"status": "ok", "voices": self.get_available_voices()}

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    generator = VoiceGenerator()

    voices = generator.get_available_voices()
    print(f"Available voices: {len(voices)}")

    result = generator.generate_voice("Hello, this is a test of the voice generator.", "af_heart")
    print(f"Generated: {result.get('status', 'N/A')}")

    print("✅ voice_generator.py OK")
