import time
import numpy as np
from core.voice.streamer import AudioStreamer, RingBuffer


def test_ring_buffer_write_read():
    buf = RingBuffer(2.0, 16000)
    data = np.ones(16000, dtype=np.float32) * 0.5
    buf.write(data)
    assert buf.duration_sec == 1.0
    readback = buf.read_all()
    assert len(readback) == 16000


def test_ring_buffer_wraparound():
    buf = RingBuffer(1.0, 16000)
    data = np.ones(32000, dtype=np.float32) * 0.5
    buf.write(data)
    assert buf.duration_sec <= 1.0


def test_ring_buffer_clear():
    buf = RingBuffer(2.0, 16000)
    data = np.ones(16000, dtype=np.float32) * 0.5
    buf.write(data)
    buf.clear()
    assert buf.duration_sec == 0.0


def test_audio_streamer_start_stop():
    streamer = AudioStreamer()
    streamer.start_capture()
    assert streamer.is_running
    time.sleep(0.1)
    streamer.stop_capture()
    assert not streamer.is_running


def test_streamer_read_chunk():
    streamer = AudioStreamer()
    streamer.start_capture()
    time.sleep(0.1)
    chunk = streamer.read_chunk()
    assert isinstance(chunk, np.ndarray)
    assert chunk.dtype == np.float32
    streamer.stop_capture()


def test_streamer_clear_buffer():
    streamer = AudioStreamer()
    streamer.start_capture()
    time.sleep(0.1)
    streamer.clear_buffer()
    assert streamer.buffer_duration() < 0.01
    streamer.stop_capture()
