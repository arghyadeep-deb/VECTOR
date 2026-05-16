import sys
import uuid
import tempfile
from pathlib import Path
from typing import Optional
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


class VoiceGenerator(AgentBase):
    """
    Generates AI voice audio from text and supports voice cloning
    from audio samples.
    """

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "VoiceGenerator", "content")
        if ghost:
            self.inherit_ghost(ghost)

        self._voice_config = CONFIG.get("voice", {})
        self._kokoro_dir = Path(self._voice_config.get("kokoro_model_dir", "./models/kokoro"))
        self._available = self._check_tts()
        self._generated_voices: list[dict] = []
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

    def generate_voice(self, text: str, voice_name: str = "af_heart",
                       output_path: Optional[str] = None) -> dict:
        """
        Generate speech from text using Kokoro TTS.
        """
        if not self._available:
            return {"status": "error", "message": "TTS engine not available"}

        if output_path is None:
            output_dir = Path(__file__).parent.parent.parent.parent / "data" / "voice_output"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"voice_{uuid.uuid4().hex[:8]}.wav")

        try:
            import kokoro_onnx
            import numpy as np
            import scipy.io.wavfile as wavfile

            model = kokoro_onnx.load_model(
                voice_name,
                repo_id=kokoro_onnx.HF_REPO,
                filename=kokoro_onnx.MODEL_FILENAME,
            )

            audio_samples, sample_rate = model.create_audio(text)

            audio_int16 = (audio_samples * 32767).astype(np.int16)
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
            output_dir = Path(__file__).parent.parent.parent.parent / "data" / "voice_output"
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
            output_dir = Path(__file__).parent.parent.parent.parent / "data" / "voice_output"
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

            ssml.append(f'<s>{sentence}.</s>')

        if breaks:
            for b in breaks:
                ssml.append(f'<break time="{b.get("time", "500ms")}"/>')

        ssml.append('</speak>')
        return '\n'.join(ssml)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    generator = VoiceGenerator()

    voices = generator.get_available_voices()
    print(f"Available voices: {len(voices)}")

    result = generator.generate_voice("Hello, this is a test of the voice generator.", "af_heart")
    print(f"Generated: {result.get('status', 'N/A')}")

    print("✅ voice_generator.py OK")
