"""Regression test: text_to_speech must not overwrite prior output in the
same output_dir.

TextToSpeechTool.execute() always wrote the synthesized audio to a literal
``digest.<ext>`` filename inside output_dir. A caller synthesizing more than
one piece of text into the same output_dir (a legitimate use of the public
``output_dir`` parameter) would have each call silently overwrite the
previous call's audio file, while every call still reported success=True.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from vectorcode.src.vc_core.registry import TTSRegistry
from vectorcode.src.vc_tools.text_to_speech import TextToSpeechTool


class _FakeSynthResult:
    def __init__(self, text: str) -> None:
        self.format = "mp3"
        self.duration_seconds = 1.0
        self.voice_id = "test-voice"
        self._text = text

    def save(self, path: Path) -> None:
        Path(path).write_text(self._text, encoding="utf-8")


class _FakeTTSBackend:
    def synthesize(self, text: str, *, voice_id: str = "", speed: float = 1.0) -> Any:
        return _FakeSynthResult(text)


@pytest.fixture
def fake_backend_registered():
    key = "test-fake-tts-backend"
    TTSRegistry.register_value(key, _FakeTTSBackend)
    yield key
    TTSRegistry._entries().pop(key, None)


def test_repeated_calls_into_same_dir_do_not_overwrite(fake_backend_registered, tmp_path: Path) -> None:
    tool = TextToSpeechTool()

    result1 = tool.execute(text="first message", backend=fake_backend_registered, output_dir=str(tmp_path))
    result2 = tool.execute(text="second message", backend=fake_backend_registered, output_dir=str(tmp_path))

    assert result1.success and result2.success
    path1 = Path(result1.metadata["audio_path"])
    path2 = Path(result2.metadata["audio_path"])

    assert path1 != path2
    assert path1.exists()
    assert path2.exists()
    assert path1.read_text(encoding="utf-8") == "first message"
    assert path2.read_text(encoding="utf-8") == "second message"
