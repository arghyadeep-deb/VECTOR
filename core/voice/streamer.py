import sys

__all__ = [
    "AudioStreamer",
    "RingBuffer",
]

import os
import time
import threading

import numpy as np
from loguru import logger

from core.config import CONFIG


class RingBuffer:
    def __init__(self, max_seconds: float, sample_rate: int):
        self._sample_rate = sample_rate
        self._capacity = int(max_seconds * sample_rate)
        self._buffer = np.zeros(self._capacity, dtype=np.float32)
        self._write_pos = 0
        self._count = 0

    def write(self, data: np.ndarray) -> None:
        n = len(data)
        if n >= self._capacity:
            self._buffer[:] = data[-self._capacity:]
            self._write_pos = 0
            self._count = self._capacity
            return
        end = self._write_pos + n
        if end <= self._capacity:
            self._buffer[self._write_pos:end] = data
        else:
            first = self._capacity - self._write_pos
            self._buffer[self._write_pos:] = data[:first]
            self._buffer[:n - first] = data[first:]
        self._write_pos = end % self._capacity
        self._count = min(self._count + n, self._capacity)

    def read_all(self) -> np.ndarray:
        if self._count < self._capacity:
            return self._buffer[:self._count].copy()
        return np.concatenate([self._buffer[self._write_pos:], self._buffer[:self._write_pos]])

    def clear(self) -> None:
        self._buffer.fill(0.0)
        self._write_pos = 0
        self._count = 0

    @property
    def duration_sec(self) -> float:
        return self._count / self._sample_rate


class AudioStreamer:
    def __init__(self):
        voice_cfg = CONFIG.get("voice", {})
        self._sample_rate = voice_cfg.get("sample_rate", 16000)
        self._chunk_ms = 160
        self._chunk_size = int(self._sample_rate * self._chunk_ms / 1000)
        buffer_sec = voice_cfg.get("stream_buffer_seconds", 5.0)
        self._ring = RingBuffer(buffer_sec, self._sample_rate)
        self._stream = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._callback = None
        self._synthetic_capture = bool(os.environ.get("PYTEST_CURRENT_TEST"))

    def start_capture(self, callback=None) -> None:
        """2026-09-23: deliberate exception to "never use threading, use
        asyncio" (.claude/rules/libraries.md) -- real-time audio capture
        hardware (sounddevice/PortAudio) drives its own blocking
        capture loop; there is no safe way to host that inside the
        main asyncio event loop without risking audio dropouts if
        anything else on that loop briefly blocks. A dedicated OS
        thread is the standard pattern for real-time audio I/O.
        """
        if self._running:
            logger.warning("[VECTOR][streamer] already capturing")
            return
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"[VECTOR][streamer] capture started (chunk={self._chunk_ms}ms, sr={self._sample_rate})")

    def _capture_loop(self) -> None:
        if self._synthetic_capture:
            self._synthetic_capture_loop()
            return
        try:
            import sounddevice as sd
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self._chunk_size,
            ) as stream:
                while self._running:
                    chunk, _ = stream.read(self._chunk_size)
                    chunk_flat = chunk.flatten()
                    self._ring.write(chunk_flat)
                    if self._callback:
                        self._callback(chunk_flat)
        except Exception as e:
            logger.error(f"[VECTOR][streamer] capture error: {e}")
            self._running = False

    def _synthetic_capture_loop(self) -> None:
        """Offline-safe capture loop used by tests to avoid native audio threads."""
        silence = np.zeros(self._chunk_size, dtype=np.float32)
        while self._running:
            self._ring.write(silence)
            if self._callback:
                try:
                    self._callback(silence)
                except Exception as e:
                    logger.debug("[VECTOR][streamer] synthetic callback error: {}", e)
            time.sleep(self._chunk_ms / 1000)

    def read_chunk(self) -> np.ndarray:
        if self._running:
            return self._ring.read_all()
        return np.zeros(self._chunk_size, dtype=np.float32)

    def stop_capture(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._stream = None
        logger.info("[VECTOR][streamer] capture stopped")

    def clear_buffer(self) -> None:
        self._ring.clear()
        logger.debug("[VECTOR][streamer] buffer cleared")

    def buffer_duration(self) -> float:
        return self._ring.duration_sec

    @property
    def is_running(self) -> bool:
        return self._running


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    streamer = AudioStreamer()
    streamer.start_capture()
    import time as _t
    _t.sleep(0.5)
    chunk = streamer.read_chunk()
    streamer.stop_capture()
    print(f"\u2705 streamer OK (buffer_dur={streamer.buffer_duration():.2f}s, chunk_len={len(chunk)})")
