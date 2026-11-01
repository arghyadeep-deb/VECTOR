"""Run Task J's fixed native-vs-ONNX experiment; results remain experimental."""

import json
import os
import socket
import statistics
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import soundfile as sf
from loguru import logger

from core.config import CONFIG
from core.voice.kokoro_native import NativeKokoro, verify_sha256

SENTENCES = [
    "Hello, welcome back.", "I can help now.", "The meeting starts soon.",
    "Please check the forecast.", "That sounds good to me.",
    "Your calendar has two appointments scheduled for tomorrow morning.",
    "I found the document you requested in your project folder.",
    "The next train leaves at six thirty from platform four.",
    "I will summarize the latest messages after this response finishes.",
    "The package should arrive on Thursday if the courier stays on schedule.",
    "Arghyadeep asked George to review the notes before lunch.",
    "Priya and Daniel will meet at the library this afternoon.",
    "The report lists 27 items and a total of 1,250 dollars.",
    "Your appointment is on October 21 at 3:45 in the afternoon.",
    "The GPU has 12 gigabytes of memory available for inference.",
    "The CUDA kernel completed while the CPU prepared the next batch.",
    "Please verify the SHA-256 checksum before loading the PyTorch checkpoint.",
    "The database migration uses SQLCipher and preserves existing records.",
    "The websocket connection closed after the authentication token expired.",
    "I can compare the latency distribution across both synthesis runtimes.",
    "The dashboard shows the current weather, upcoming meetings, and a reminder to call your colleague before you leave for the office today.",
    "After the backup completes, review the newly created archive and confirm that every important document can be restored without errors or missing files.",
    "The assistant read the first sentence aloud while another process decoded tokens on the graphics card and updated the conversation history in memory.",
    "Although the network connection was unavailable, the local model continued generating speech from the cached checkpoint and the selected George voice tensor.",
    "Aisha wants the weekly summary delivered before nine, so gather the finished tasks, open issues, and decisions from each active project first.",
    "Set a timer for 15 minutes.",
    "Dr. Morgan called from London.",
    "The API returned a 503 error.",
    "Could you explain the transformer attention mask used during inference?",
    "There are 42 unread messages waiting in your inbox.",
]


@contextmanager
def block_network():
    """Fail loudly on any Python socket connection during inference."""
    original_connect = socket.socket.connect
    original_create = socket.create_connection

    def blocked(*args, **kwargs):
        raise RuntimeError("Network connection attempted during inference")

    socket.socket.connect = blocked
    socket.create_connection = blocked
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.create_connection = original_create


def summarize(times):
    ordered = sorted(times)
    return {"count": len(times), "median_ms": statistics.median(times),
            "p95_ms": float(np.percentile(ordered, 95))}


def main():
    import torch
    import onnxruntime as ort
    from kokoro_onnx import Kokoro
    from core.voice.tts import _KokoroIOBindingSession, _add_cuda_dll_dirs

    assert torch.cuda.is_available(), "CUDA is required"
    assert len(SENTENCES) == 30
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    root = Path(CONFIG["voice"]["kokoro_model_dir"])
    verify_sha256(root / "native" / "kokoro-v1_0.pth")
    native = NativeKokoro(root / "native")
    _add_cuda_dll_dirs()
    onnx = Kokoro(str(root / "kokoro-v1.0.fp16-gpu.onnx"), str(root / "voices-v1.0.bin"))
    assert "CUDAExecutionProvider" in onnx.sess.get_providers()
    options = onnx.sess.get_provider_options()["CUDAExecutionProvider"]
    onnx.sess = _KokoroIOBindingSession(onnx.sess, ort, int(options.get("device_id", 0)))
    voice = CONFIG["voice"]["kokoro_voice"]
    speed = CONFIG["voice"]["kokoro_speed"]
    assert voice == "bm_george"
    result_dir = root / "native" / "benchmark_results"
    result_dir.mkdir(parents=True, exist_ok=True)
    sample_dir = Path(os.environ["KOKORO_SAMPLE_DIR"])
    sample_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for backend, adapter in (("onnx", onnx), ("native", native)):
        adapter.create("Hello from Vector.", voice=voice, speed=speed)
        for repeat in range(5):
            for index, sentence in enumerate(SENTENCES, 1):
                with block_network():
                    started = time.perf_counter()
                    audio, rate = adapter.create(sentence, voice=voice, speed=speed)
                    elapsed_ms = (time.perf_counter() - started) * 1000
                assert rate == 24000 and len(audio) > 0
                records.append({"backend": backend, "repeat": repeat + 1,
                                "sentence": index, "wall_ms": elapsed_ms,
                                "samples": len(audio)})
                if repeat == 0 and index in (3, 12, 17, 24, 29):
                    sf.write(sample_dir / f"sentence{index:02d}_{backend}.wav", audio, rate)
                logger.info("[VECTOR][kokoro_benchmark] {} {} {} {:.2f} ms",
                            backend, repeat + 1, index, elapsed_ms)
    summary = {backend: summarize([r["wall_ms"] for r in records if r["backend"] == backend])
               for backend in ("onnx", "native")}
    (result_dir / "results.json").write_text(json.dumps({"sentences": SENTENCES,
        "records": records, "summary": summary, "voice": voice, "speed": speed}, indent=2), encoding="utf-8")
    logger.info("[VECTOR][kokoro_benchmark] {}", summary)


if __name__ == "__main__":
    main()
