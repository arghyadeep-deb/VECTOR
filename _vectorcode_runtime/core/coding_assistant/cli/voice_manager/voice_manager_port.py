from __future__ import annotations

__all__ = [
    "RecordingStartError",
    "TranscribeState",
    "VoiceManagerListener",
    "VoiceManagerPort",
    "VoiceToggleResult",
]


from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Protocol

from core.coding_assistant.core.audio_recorder.audio_recorder_port import RecordingMode


class TranscribeState(StrEnum):
    IDLE = auto()
    RECORDING = auto()
    FLUSHING = auto()


@dataclass(frozen=True, slots=True)
class VoiceToggleResult:
    enabled: bool


class RecordingStartError(Exception):
    pass


class VoiceManagerListener:
    def on_transcribe_state_change(self, state: TranscribeState) -> None:
        from loguru import logger
        logger.debug("[VECTOR][voice_manager_port] on_transcribe_state_change called (no-op)")

    def on_voice_mode_change(self, enabled: bool) -> None:
        from loguru import logger
        logger.debug("[VECTOR][voice_manager_port] on_voice_mode_change called (no-op)")

    def on_transcribe_text(self, text: str) -> None:
        from loguru import logger
        logger.debug("[VECTOR][voice_manager_port] on_transcribe_text called (no-op)")


class VoiceManagerPort(Protocol):
    @property
    def is_enabled(self) -> bool: ...

    @property
    def transcribe_state(self) -> TranscribeState: ...

    @property
    def peak(self) -> float: ...

    def toggle_voice_mode(self) -> VoiceToggleResult: ...

    def start_recording(self, mode: RecordingMode = RecordingMode.STREAM) -> None: ...

    async def stop_recording(self) -> None: ...

    def cancel_recording(self) -> None: ...

    def add_listener(self, listener: VoiceManagerListener) -> None: ...

    def remove_listener(self, listener: VoiceManagerListener) -> None: ...

    async def close(self) -> None: ...
