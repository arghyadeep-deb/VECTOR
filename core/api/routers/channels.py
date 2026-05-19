"""Channels router — /channels/status."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter
from loguru import logger

from core.api.schemas import ChannelsStatusResponse

router = APIRouter(prefix="/channels", tags=["channels"])

@router.get("/status", response_model=ChannelsStatusResponse)
async def channels_status():
    try:
        active = []
        recent_count = 0
        try:
            from vectorcode.src.channels.channel_directory import ChannelDirectory
            directory = ChannelDirectory()
            active = [ch for ch in directory.list_active() if ch]
        except Exception:
            pass
        if not active:
            try:
                from core.engine.channels.runtime import ChannelRuntime
                runtime = ChannelRuntime()
                active = [ch.name for ch in runtime.active_channels()] if hasattr(runtime, 'active_channels') else []
            except Exception:
                pass
        try:
            from core.memory.episodic import EpisodicMemory
            recent = EpisodicMemory().recall("channel message", limit=1, event_type="channel_message")
            recent_count = len(recent)
        except Exception:
            recent_count = 0
        return ChannelsStatusResponse(
            active_channels=active,
            recent_messages=recent_count,
            status="active" if active else "inactive",
        )
    except Exception as e:
        logger.warning(f"[VECTOR][api][channels] status failed: {e}")
        return ChannelsStatusResponse(
            active_channels=[], recent_messages=0, status=str(e),
        )

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ channels.py OK")
