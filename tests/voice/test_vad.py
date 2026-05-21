import numpy as np
from core.voice.vad import VoiceActivityDetector


def test_initial_state():
    vad = VoiceActivityDetector()
    assert vad.state == "SILENCE"


def test_silence_detection():
    vad = VoiceActivityDetector()
    sr = 16000
    silence = np.zeros(int(sr * 0.3), dtype=np.float32)
    assert not vad.is_speech(silence, sr)
    assert vad.state == "SILENCE"


def test_speech_detection():
    vad = VoiceActivityDetector()
    sr = 16000
    speech = np.random.rand(int(sr * 0.3)).astype(np.float32) * 0.1
    result = vad.is_speech(speech, sr)
    assert result


def test_state_transition():
    vad = VoiceActivityDetector()
    sr = 16000
    silence = np.zeros(int(sr * 0.6), dtype=np.float32)
    speech = np.random.rand(int(sr * 0.3)).astype(np.float32) * 0.1

    for _ in range(5):
        vad.is_speech(silence, sr)
    assert vad.state == "SILENCE"

    for _ in range(5):
        vad.is_speech(speech, sr)
    assert vad.state == "SPEECH"


def test_speech_to_silence():
    vad = VoiceActivityDetector()
    sr = 16000
    speech = np.random.rand(int(sr * 0.3)).astype(np.float32) * 0.1
    silence = np.zeros(int(sr * 0.6), dtype=np.float32)

    for _ in range(5):
        vad.is_speech(speech, sr)
    assert vad.state == "SPEECH"

    for _ in range(10):
        vad.is_speech(silence, sr)
    assert vad.state == "SILENCE"


def test_reset():
    vad = VoiceActivityDetector()
    sr = 16000
    speech = np.random.rand(int(sr * 0.3)).astype(np.float32) * 0.1
    for _ in range(5):
        vad.is_speech(speech, sr)
    assert vad.speech_duration() > 0
    vad.reset()
    assert vad.state == "SILENCE"
    assert vad.speech_duration() == 0.0
    assert vad.silence_duration() == 0.0
