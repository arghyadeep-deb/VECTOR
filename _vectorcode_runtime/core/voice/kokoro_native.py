"""Local-file-only native Kokoro adapter for the Phase 1 latency experiment."""

from hashlib import sha256
from pathlib import Path

import numpy as np
from loguru import logger

CHECKPOINT_SHA256 = "496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4"
SAMPLE_RATE = 24_000


def verify_sha256(path: Path, expected: str = CHECKPOINT_SHA256) -> str:
    """Reject a checkpoint before any model deserialization if its hash differs."""
    digest = sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual.lower() != expected.lower():
        raise ValueError(f"SHA-256 mismatch for {path}: {actual} != {expected}")
    return actual


class NativeKokoro:
    """Experimental `create(text, voice, speed)` interface, never used by production."""

    def __init__(self, model_dir: Path | None = None, pipeline=None):
        if pipeline is not None:
            self._pipeline = pipeline
            return
        if model_dir is None:
            raise ValueError("model_dir is required when no pipeline is supplied")
        import torch
        from kokoro import KModel, KPipeline

        if not torch.cuda.is_available():
            raise RuntimeError("Native Kokoro experiment requires CUDA")
        root = Path(model_dir)
        checkpoint = root / "kokoro-v1_0.pth"
        verify_sha256(checkpoint)
        config = root / "config.json"
        voice_path = root / "voices" / "bm_george.pt"
        if not config.is_file() or not voice_path.is_file():
            raise FileNotFoundError("Native Kokoro config or bm_george voice is missing")
        model = KModel(repo_id="hexgrad/Kokoro-82M", config=str(config), model=str(checkpoint)).to("cuda").eval()
        pipeline = KPipeline(lang_code="b", repo_id="hexgrad/Kokoro-82M", model=model, device="cuda")
        pipeline.voices["bm_george"] = torch.load(voice_path, map_location="cpu", weights_only=True)
        self._pipeline = pipeline
        logger.info("[VECTOR][kokoro_native] Local CUDA checkpoint and voice loaded")

    def create(self, text: str, voice: str = "bm_george", speed: float = 1.0) -> tuple[np.ndarray, int]:
        if voice != "bm_george":
            raise ValueError("Only the locally loaded bm_george voice is supported")
        chunks = []
        for result in self._pipeline(text, voice=voice, speed=speed):
            audio = result[2]
            if audio is None:
                raise RuntimeError("Kokoro returned no audio")
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))
        if not chunks or any(chunk.size == 0 for chunk in chunks):
            raise RuntimeError("Kokoro returned empty audio")
        return np.concatenate(chunks), SAMPLE_RATE


if __name__ == "__main__":
    from core.config import CONFIG

    root = Path(CONFIG["voice"]["kokoro_model_dir"]) / "native"
    adapter = NativeKokoro(root)
    waveform, sample_rate = adapter.create("Hello from Vector.", speed=CONFIG["voice"]["kokoro_speed"])
    assert waveform.size and sample_rate == SAMPLE_RATE
    logger.info("[VECTOR][kokoro_native] Smoke test passed: {} samples", waveform.size)
