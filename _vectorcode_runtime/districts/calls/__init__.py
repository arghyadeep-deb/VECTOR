"""
Module: agents/calls/__init__.py
V.E.C.T.O.R. Calls District - Voice interaction and call management agents
"""

import sys

from loguru import logger

from .transcription_bot import TranscriptionBot
from .voice_responder import VoiceResponder
from .call_screener import CallScreener

__all__ = [
    "TranscriptionBot",
    "VoiceResponder",
    "CallScreener",
]

logger.info("[VECTOR][calls] Calls district loaded")


def get_agent(name: str):
    """Factory function to get calls district agents."""
    agents = {
        "TranscriptionBot": TranscriptionBot,
        "VoiceResponder": VoiceResponder,
        "CallScreener": CallScreener,
    }
    return agents.get(name)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    transcriber = TranscriptionBot()
    print(f"TranscriptionBot: {transcriber.name}")

    responder = VoiceResponder()
    print(f"VoiceResponder: {responder.name}")

    screener = CallScreener()
    print(f"CallScreener: {screener.name}")

    print("✅ calls/__init__.py OK")
