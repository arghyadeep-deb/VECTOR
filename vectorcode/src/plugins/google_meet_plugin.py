"""Google Meet plugin — audio bridge, bot, process management."""

import asyncio
from loguru import logger
import subprocess
from typing import Optional



class GoogleMeetPlugin:
    def __init__(self):
        self._process = None
        self._running = False

    async def join_meeting(self, meeting_url: str, audio_only: bool = True) -> dict:
        logger.info(f"Joining Google Meet: {meeting_url}")
        return {"status": "joined", "meeting": meeting_url, "audio_only": audio_only}

    async def leave_meeting(self) -> dict:
        if self._process:
            self._process.terminate()
            self._running = False
        return {"status": "left"}

    async def get_audio_feed(self) -> Optional[str]:
        return "audio_feed_placeholder"

    async def status(self) -> dict:
        return {"running": self._running, "meeting": None}
