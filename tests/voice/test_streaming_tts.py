import numpy as np
from core.voice.tts import StreamingTTS


def test_streaming_tts_init():
    stt = StreamingTTS()
    assert stt is not None


def test_set_voice():
    stt = StreamingTTS()
    stt.set_voice("bf_emma")
    assert stt._current_voice == "bf_emma"


def test_cross_fade_same_length():
    stt = StreamingTTS()
    chunk1 = np.ones(16000, dtype=np.float32) * 0.5
    chunk2 = np.ones(16000, dtype=np.float32) * 0.3
    result = stt.cross_fade(chunk1, chunk2, overlap_ms=50)
    expected_len = len(chunk1) + len(chunk2) - int(16000 * 50 / 1000)
    assert len(result) == expected_len
    assert result.dtype == np.float32


def test_cross_fade_short_chunks():
    stt = StreamingTTS()
    chunk1 = np.ones(100, dtype=np.float32)
    chunk2 = np.ones(100, dtype=np.float32)
    result = stt.cross_fade(chunk1, chunk2, overlap_ms=50)
    assert len(result) == 200


def test_cross_fade_values():
    stt = StreamingTTS()
    chunk1 = np.ones(16000, dtype=np.float32) * 1.0
    chunk2 = np.ones(16000, dtype=np.float32) * 0.0
    result = stt.cross_fade(chunk1, chunk2, overlap_ms=50)
    overlap_samples = int(16000 * 50 / 1000)
    midpoint = len(chunk1) - overlap_samples
    assert result[midpoint - 1] == 1.0
    assert result[len(chunk1)] < 1.0


def test_early_terminate():
    stt = StreamingTTS()
    stt._speaking = True
    stt.early_terminate()
    assert not stt._speaking


def test_generate_stream_callback():
    stt = StreamingTTS()
    received = []
    def cb(samples, sr):
        received.append((samples, sr))
    stt.generate_stream("Hello world.", callback=cb)
    assert len(received) >= 1
